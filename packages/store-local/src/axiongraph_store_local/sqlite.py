"""A durable single-file GraphStore backed by the stdlib ``sqlite3`` (spec D4). One ``events``
table keyed on ``(run_id, seq)``; ``append`` uses ``INSERT OR IGNORE`` so it is idempotent on
``(runId, seq)``. No server, survives restarts. Snapshots live-fold the log."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator, Sequence
from typing import cast

from axiongraph_core import GraphEvent, GraphState, reduce_all


class SqliteStore:
    """A :class:`~axiongraph_core.GraphStore` persisted to a single SQLite database file."""

    def __init__(self, location: str = ":memory:") -> None:
        """``location`` is a file path, or ``":memory:"`` (default) for an ephemeral database."""
        self._db = sqlite3.connect(location)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "  run_id  TEXT    NOT NULL,"
            "  seq     INTEGER NOT NULL,"
            "  payload TEXT    NOT NULL,"
            "  PRIMARY KEY (run_id, seq)"
            ")"
        )

    async def append(self, events: Sequence[GraphEvent]) -> None:
        self._db.executemany(
            "INSERT OR IGNORE INTO events (run_id, seq, payload) VALUES (?, ?, ?)",
            [(event["runId"], event["seq"], json.dumps(event)) for event in events],
        )
        self._db.commit()

    async def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        rows = self._db.execute(
            "SELECT payload FROM events WHERE run_id = ? AND seq > ? ORDER BY seq",
            (run_id, since_seq),
        ).fetchall()
        for (payload,) in rows:
            yield cast(GraphEvent, json.loads(payload))

    async def snapshot(self, run_id: str) -> GraphState:
        rows = self._db.execute(
            "SELECT payload FROM events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        return reduce_all(run_id, [cast(GraphEvent, json.loads(payload)) for (payload,) in rows])

    def close(self) -> None:
        """Release the underlying database handle. Not part of the ``GraphStore`` port."""
        self._db.close()
