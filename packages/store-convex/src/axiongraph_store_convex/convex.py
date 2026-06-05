"""A client-only GraphStore for a Convex deployment running the axiongraph component (spec D4).

It never touches the database directly: it calls the public ``append`` / ``readEvents`` functions
the host exposed (the TypeScript ``exposeAxiongraph`` factory), which delegate into
``components.axiongraph``. Mirrors the TypeScript ``ConvexStore``; the component itself ships only
in the TypeScript package (Convex bundles it on deploy), so this Python side is the external client.

The ``convex`` Python client is synchronous, so each call is run in a worker thread
(:func:`asyncio.to_thread`) to satisfy the async :class:`~axiongraph_core.GraphStore` protocol
without blocking the event loop. Requires the ``convex`` extra:
``pip install 'axiongraph[convex]'``.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, cast

from axiongraph_core import GraphEvent, GraphState, reduce_all
from store_driver_kit import Row, ScanOptions, Transaction

try:
    from convex import ConvexClient
except ModuleNotFoundError as exc:  # pragma: no cover - surfaced only without the extra
    raise ModuleNotFoundError(
        "ConvexStore requires the 'convex' extra: pip install 'axiongraph[convex]'"
    ) from exc


class ConvexStore:
    """A :class:`~axiongraph_core.GraphStore` backed by a Convex deployment.

    ``client`` is a ``convex.ConvexClient`` pointed at the deployment that has the axiongraph
    component installed and the exposed functions deployed. ``prefix`` names the host file that
    re-exports those functions, used to build the ``{prefix}:append`` / ``{prefix}:readEvents``
    references (default ``axiongraph`` — i.e. the host wrote ``convex/axiongraph.ts``).
    """

    def __init__(self, client: ConvexClient, *, prefix: str = "axiongraph") -> None:
        self._client = client
        self._append_ref = f"{prefix}:append"
        self._read_events_ref = f"{prefix}:readEvents"
        self._driver = _ConvexGraphDriver(client, self._append_ref, self._read_events_ref)

    async def append(self, events: Sequence[GraphEvent]) -> None:
        """Append events. Idempotent on ``(runId, seq)`` (the component skips a known seq)."""
        if not events:
            return

        async def work(txn: Transaction) -> None:
            for event in events:
                await txn.upsert("events", _event_key(event), {"payload": event})

        await self._driver.transaction(work)

    async def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        """Read a run's events in ``seq`` order, only those with ``seq > since_seq``."""

        async def work(txn: Transaction) -> list[GraphEvent]:
            events: list[GraphEvent] = []
            scan_opts = ScanOptions(after={"runId": run_id, "seq": since_seq})
            async for row in txn.scan("events", {"runId": run_id}, scan_opts):
                events.append(cast(GraphEvent, row["payload"]))
            return events

        for event in await self._driver.transaction(work):
            yield event

    async def snapshot(self, run_id: str) -> GraphState:
        """The reduced state for a run — a client-side fold over ``read_events`` (reuses core)."""
        events = [event async for event in self.read_events(run_id)]
        return reduce_all(run_id, events)

    async def subscribe(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        """Realtime tail (spec D4): the reactive seam, mirroring the TypeScript ``subscribe``.

        The ``convex`` client's ``subscribe`` is a *blocking* generator that re-yields the whole
        ``readEvents`` result whenever the run's log changes. We drive it on a worker thread, hand
        events to the event loop through an :class:`asyncio.Queue`, and apply a client-side
        high-water mark so each event past ``since_seq`` is emitted exactly once. Stopping the
        iteration closes the underlying subscription.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[GraphEvent | object] = asyncio.Queue()
        done = object()
        stop = threading.Event()

        def worker() -> None:
            high_water = since_seq
            args: dict[str, Any] = {"runId": run_id, "sinceSeq": since_seq}
            subscription = self._client.subscribe(self._read_events_ref, args)
            try:
                for raw in subscription:
                    # Each refire is the whole ``readEvents`` result — a list of events.
                    for row in cast(list[Any], raw):
                        event = cast(GraphEvent, row)
                        if event["seq"] > high_water:
                            high_water = event["seq"]
                            loop.call_soon_threadsafe(queue.put_nowait, event)
                    if stop.is_set():
                        break
            finally:
                close = getattr(subscription, "close", None)
                if callable(close):
                    close()
                loop.call_soon_threadsafe(queue.put_nowait, done)

        thread = threading.Thread(target=worker, name="axiongraph-convex-subscribe", daemon=True)
        thread.start()
        try:
            while True:
                item = await queue.get()
                if item is done:
                    break
                yield cast(GraphEvent, item)
        finally:
            stop.set()


class _ConvexGraphDriver:
    backend = "convex"

    def __init__(self, client: ConvexClient, append_ref: str, read_events_ref: str) -> None:
        self._client = client
        self._append_ref = append_ref
        self._read_events_ref = read_events_ref

    async def transaction(self, work: Callable[[Transaction], Awaitable[Any]]) -> Any:
        return await work(
            _ConvexGraphTransaction(self._client, self._append_ref, self._read_events_ref)
        )

    async def close(self) -> None:
        return None


class _ConvexGraphTransaction:
    def __init__(self, client: ConvexClient, append_ref: str, read_events_ref: str) -> None:
        self._client = client
        self._append_ref = append_ref
        self._read_events_ref = read_events_ref

    async def upsert(self, table: str, key: Row, row: Row) -> None:
        self._assert_table(table)
        _ = key
        # The Convex client coerces its args dict; events are dicts at runtime. Type the boundary
        # as ``dict[str, Any]`` rather than fight ``CoercibleToConvexValue`` over a TypedDict.
        args: dict[str, Any] = {"events": [row["payload"]]}
        await asyncio.to_thread(self._client.mutation, self._append_ref, args)

    async def get(self, table: str, key: Row) -> Row | None:
        self._assert_table(table)
        args: dict[str, Any] = {"runId": key["runId"], "sinceSeq": int(key["seq"]) - 1}
        rows = await asyncio.to_thread(self._client.query, self._read_events_ref, args)
        for raw in cast(list[Any], rows):
            event = cast(GraphEvent, raw)
            if event["seq"] == key["seq"]:
                return {"payload": event}
        return None

    async def scan(
        self, table: str, prefix: Row, opts: ScanOptions | None = None
    ) -> AsyncIterator[Row]:
        self._assert_table(table)
        options = opts or ScanOptions()
        after_seq = options.after.get("seq", 0) if options.after is not None else 0
        args: dict[str, Any] = {"runId": prefix["runId"], "sinceSeq": after_seq}
        rows = await asyncio.to_thread(self._client.query, self._read_events_ref, args)
        for index, raw in enumerate(cast(list[Any], rows)):
            if options.limit is not None and index >= options.limit:
                break
            yield {"payload": cast(GraphEvent, raw)}

    async def compare_and_apply(self, table: str, key: Row, expect: Any, next_value: Any) -> bool:
        self._assert_table(table)
        _ = (key, expect, next_value)
        raise NotImplementedError(
            "ConvexGraphTransaction.compare_and_apply is not supported by GraphStore"
        )

    def _assert_table(self, table: str) -> None:
        if table != "events":
            raise ValueError(f"Unknown Convex graph table: {table}")


def _event_key(event: GraphEvent) -> Row:
    return {"runId": event["runId"], "seq": event["seq"]}


__all__ = ["ConvexStore"]
