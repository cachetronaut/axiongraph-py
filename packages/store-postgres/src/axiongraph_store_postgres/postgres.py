"""A durable GraphStore backed by PostgreSQL via psycopg (spec D4). One ``jsonb`` event log
keyed on ``(run_id, seq)``; ``append`` uses ``INSERT ... ON CONFLICT DO NOTHING`` so it is
idempotent on ``(runId, seq)``. Snapshots live-fold the log. Mirrors the TypeScript
``PostgresStore``. Requires the ``postgres`` extra: ``pip install 'axiongraph[postgres]'``."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import cast

from axiongraph_core import GraphEvent, GraphState, reduce_all

try:
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError as exc:  # pragma: no cover - surfaced only without the extra
    raise ModuleNotFoundError(
        "PostgresStore requires the 'postgres' extra: pip install 'axiongraph[postgres]'"
    ) from exc

# Table names can't be bound parameters; we interpolate them with ``sql.Identifier`` (which
# quotes safely), and reject anything that isn't a plain identifier up front for clear errors
# and parity with the other adapters.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresStore:
    """A :class:`~axiongraph_core.GraphStore` persisted to PostgreSQL via an async pool.

    Pass a connection string (the store owns and opens its own pool) or an existing
    ``psycopg_pool.AsyncConnectionPool`` (the store borrows it and leaves its lifecycle to you).
    """

    def __init__(
        self,
        connection: str | AsyncConnectionPool,
        *,
        table: str = "axiongraph_events",
    ) -> None:
        if not _IDENTIFIER.match(table):
            raise ValueError(f"Invalid Postgres table name: {table}")
        self._table = table
        if isinstance(connection, str):
            self._pool: AsyncConnectionPool = AsyncConnectionPool(connection, open=False)
            self._owns_pool = True
        else:
            self._pool = connection
            self._owns_pool = False
        self._ready = False

    def _table_sql(self) -> sql.Identifier:
        return sql.Identifier(self._table)

    async def _ensure_ready(self) -> None:
        if self._ready:
            return
        if self._owns_pool:
            await self._pool.open()
        async with self._pool.connection() as conn:
            await conn.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {table} ("
                    "  run_id  text   NOT NULL,"
                    "  seq     bigint NOT NULL,"
                    "  payload jsonb  NOT NULL,"
                    "  PRIMARY KEY (run_id, seq)"
                    ")"
                ).format(table=self._table_sql())
            )
        self._ready = True

    async def append(self, events: Sequence[GraphEvent]) -> None:
        await self._ensure_ready()
        if not events:
            return
        statement = sql.SQL(
            "INSERT INTO {table} (run_id, seq, payload) "
            "VALUES (%s, %s, %s) ON CONFLICT (run_id, seq) DO NOTHING"
        ).format(table=self._table_sql())
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.executemany(
                statement,
                [(event["runId"], event["seq"], Jsonb(event)) for event in events],
            )

    async def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        await self._ensure_ready()
        statement = sql.SQL(
            "SELECT payload FROM {table} WHERE run_id = %s AND seq > %s ORDER BY seq"
        ).format(table=self._table_sql())
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(statement, (run_id, since_seq))
            rows = await cur.fetchall()
        for (payload,) in rows:
            yield cast(GraphEvent, payload)  # jsonb is decoded to a dict by psycopg

    async def snapshot(self, run_id: str) -> GraphState:
        events = [event async for event in self.read_events(run_id)]
        return reduce_all(run_id, events)

    async def close(self) -> None:
        """Close the owned pool. A no-op for a borrowed pool. Not part of the ``GraphStore``."""
        if self._owns_pool and self._ready:
            await self._pool.close()
