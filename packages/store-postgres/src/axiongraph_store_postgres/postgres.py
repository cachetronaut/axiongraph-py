"""A durable GraphStore backed by PostgreSQL via psycopg (spec D4). One ``jsonb`` event log
keyed on ``(run_id, seq)``; ``append`` uses ``INSERT ... ON CONFLICT DO NOTHING`` so it is
idempotent on ``(runId, seq)``. Snapshots live-fold the log. Mirrors the TypeScript
``PostgresStore``. Requires the ``postgres`` extra: ``pip install 'axiongraph[postgres]'``."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, cast

from axiongraph_core import GraphEvent, GraphState, reduce_all
from store_driver_kit import Row, ScanOptions, Transaction, canonicalize

try:
    from psycopg import AsyncConnection, sql
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
        self._driver = _PostgresGraphDriver(self._pool, table, self._ensure_ready, self._table_sql)

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
        if not events:
            return

        async def work(txn: Transaction) -> None:
            for event in events:
                await txn.upsert(self._table, _event_key(event), {"payload": event})

        await self._driver.transaction(work)

    async def read_events(self, run_id: str, since_seq: int = 0) -> AsyncIterator[GraphEvent]:
        async def work(txn: Transaction) -> list[GraphEvent]:
            events: list[GraphEvent] = []
            scan_opts = ScanOptions(after={"runId": run_id, "seq": since_seq})
            async for row in txn.scan(self._table, {"runId": run_id}, scan_opts):
                events.append(cast(GraphEvent, row["payload"]))
            return events

        for event in await self._driver.transaction(work):
            yield event

    async def snapshot(self, run_id: str) -> GraphState:
        events = [event async for event in self.read_events(run_id)]
        return reduce_all(run_id, events)

    async def close(self) -> None:
        """Close the owned pool. A no-op for a borrowed pool. Not part of the ``GraphStore``."""
        if self._owns_pool and self._ready:
            await self._pool.close()


class _PostgresGraphDriver:
    backend = "postgres"

    def __init__(
        self,
        pool: AsyncConnectionPool,
        table: str,
        ensure_ready: Callable[[], Awaitable[None]],
        table_sql: Callable[[], sql.Identifier],
    ) -> None:
        self._pool = pool
        self._table = table
        self._ensure_ready = ensure_ready
        self._table_sql = table_sql

    async def transaction(self, work: Callable[[Transaction], Awaitable[Any]]) -> Any:
        await self._ensure_ready()
        async with self._pool.connection() as conn, conn.transaction():
            return await work(_PostgresGraphTransaction(conn, self._table, self._table_sql()))

    async def close(self) -> None:
        await self._pool.close()


class _PostgresGraphTransaction:
    def __init__(self, conn: AsyncConnection[Any], table: str, table_sql: sql.Identifier) -> None:
        self._conn = conn
        self._table = table
        self._table_sql = table_sql

    async def upsert(self, table: str, key: Row, row: Row) -> None:
        self._assert_table(table)
        statement = sql.SQL(
            "INSERT INTO {table} (run_id, seq, payload) "
            "VALUES (%s, %s, %s) ON CONFLICT (run_id, seq) DO NOTHING"
        ).format(table=self._table_sql)
        await self._conn.execute(statement, (key["runId"], key["seq"], Jsonb(row["payload"])))

    async def get(self, table: str, key: Row) -> Row | None:
        self._assert_table(table)
        statement = sql.SQL("SELECT payload FROM {table} WHERE run_id = %s AND seq = %s").format(
            table=self._table_sql
        )
        cursor = await self._conn.execute(statement, (key["runId"], key["seq"]))
        row = await cursor.fetchone()
        return None if row is None else {"payload": row[0]}

    async def scan(
        self, table: str, prefix: Row, opts: ScanOptions | None = None
    ) -> AsyncIterator[Row]:
        self._assert_table(table)
        options = opts or ScanOptions()
        after_seq = options.after.get("seq", 0) if options.after is not None else 0
        if options.limit is None:
            statement = sql.SQL(
                "SELECT payload FROM {table} WHERE run_id = %s AND seq > %s ORDER BY seq"
            ).format(table=self._table_sql)
            params: tuple[Any, ...] = (prefix["runId"], after_seq)
        else:
            statement = sql.SQL(
                "SELECT payload FROM {table} WHERE run_id = %s AND seq > %s ORDER BY seq LIMIT %s"
            ).format(table=self._table_sql)
            params = (prefix["runId"], after_seq, options.limit)
        cursor = await self._conn.execute(statement, params)
        rows = await cursor.fetchall()
        for (payload,) in rows:
            yield {"payload": payload}

    async def compare_and_apply(self, table: str, key: Row, expect: Any, next_value: Any) -> bool:
        self._assert_table(table)
        current = await self.get(table, key)
        if canonicalize({"value": None if current is None else current["payload"]}) != canonicalize(
            {"value": expect}
        ):
            return False
        if current is None:
            statement = sql.SQL(
                "INSERT INTO {table} (run_id, seq, payload) "
                "VALUES (%s, %s, %s) ON CONFLICT (run_id, seq) DO NOTHING"
            ).format(table=self._table_sql)
            cursor = await self._conn.execute(
                statement, (key["runId"], key["seq"], Jsonb(next_value))
            )
            return cursor.rowcount == 1
        statement = sql.SQL(
            "UPDATE {table} SET payload = %s WHERE run_id = %s AND seq = %s"
        ).format(table=self._table_sql)
        await self._conn.execute(statement, (Jsonb(next_value), key["runId"], key["seq"]))
        return True

    def _assert_table(self, table: str) -> None:
        if table != self._table:
            raise ValueError(f"Unknown Postgres graph table: {table}")


def _event_key(event: GraphEvent) -> Row:
    return {"runId": event["runId"], "seq": event["seq"]}
