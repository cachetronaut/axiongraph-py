"""A dict-backed GraphStore for tests and ephemeral runs (spec D4). Append-only and
idempotent on ``(runId, seq)``. No durability; everything lives in process memory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from axiongraph_core import GraphEvent, GraphState, reduce_all


class InMemoryStore:
    """A :class:`~axiongraph_core.GraphStore` backed by per-run lists kept sorted by ``seq``."""

    def __init__(self) -> None:
        self._logs: dict[str, list[GraphEvent]] = {}

    async def append(self, events: Sequence[GraphEvent]) -> None:
        for event in events:
            log = self._logs.setdefault(event["runId"], [])
            if any(existing["seq"] == event["seq"] for existing in log):
                continue  # idempotent on (runId, seq)
            log.append(event)
            log.sort(key=lambda candidate: candidate["seq"])

    async def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        for event in self._logs.get(run_id, []):
            if event["seq"] > since_seq:
                yield event

    async def snapshot(self, run_id: str) -> GraphState:
        return reduce_all(run_id, self._logs.get(run_id, []))
