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
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

from axiongraph_core import GraphEvent, GraphState, reduce_all

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

    async def append(self, events: Sequence[GraphEvent]) -> None:
        """Append events. Idempotent on ``(runId, seq)`` (the component skips a known seq)."""
        if not events:
            return
        # The convex client coerces its args dict; events are dicts at runtime. Type the boundary
        # as ``dict[str, Any]`` rather than fight ``CoercibleToConvexValue`` over a TypedDict.
        args: dict[str, Any] = {"events": list(events)}
        await asyncio.to_thread(self._client.mutation, self._append_ref, args)

    async def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        """Read a run's events in ``seq`` order, only those with ``seq > since_seq``."""
        args: dict[str, Any] = {"runId": run_id, "sinceSeq": since_seq}
        rows = await asyncio.to_thread(self._client.query, self._read_events_ref, args)
        for row in rows:
            yield cast(GraphEvent, row)

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


__all__ = ["ConvexStore"]
