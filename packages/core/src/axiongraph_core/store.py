"""The :class:`GraphStore` port (spec D4): the seam between the event model and any backend.
Core defines the protocol; adapters (``axiongraph.store_local``, and later convex/neo4j/postgres)
implement it. Writes are append-only and idempotent on ``(runId, seq)`` (ties back to spec D3)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from .types import GraphEvent, GraphState


@runtime_checkable
class GraphStore(Protocol):
    """Append-only event storage. Realtime fan-out (an optional ``subscribe``) is where the
    hosted product lives; the local adapter omits it. Core never assumes a realtime transport."""

    async def append(self, events: Sequence[GraphEvent]) -> None:
        """Append events. Idempotent on ``(runId, seq)``: re-appending a known seq is a no-op."""
        ...

    def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        """Read a run's events in ``seq`` order, optionally only those after ``since_seq``."""
        ...

    async def snapshot(self, run_id: str) -> GraphState:
        """The reduced state for a run. May be a live fold or a materialized cache."""
        ...
