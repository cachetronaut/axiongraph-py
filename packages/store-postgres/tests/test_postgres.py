"""Runs the shared GraphStore contract (plus a durability check) against a real PostgreSQL.

Gated on ``AXIONGRAPH_TEST_POSTGRES_URL`` — the whole module is skipped unless it is set, so
the default test run needs no database. CI points it at a ``postgres`` service. Each case uses
a unique table so cases stay isolated; tables are dropped when the module finishes.

The store API is async; tests drive it with ``asyncio.run`` to avoid a pytest-asyncio dependency."""

from __future__ import annotations

import asyncio
import itertools
import os
from collections.abc import Iterator
from typing import cast

import pytest
from axiongraph_testkit import CONTRACT_CHECKS, ContractCheck, node_created

if not os.environ.get("AXIONGRAPH_TEST_POSTGRES_URL"):
    pytest.skip(
        "set AXIONGRAPH_TEST_POSTGRES_URL to run the Postgres contract suite",
        allow_module_level=True,
    )

# Narrowed to ``str``: the skip above aborts collection when it is unset.
POSTGRES_URL = cast(str, os.environ.get("AXIONGRAPH_TEST_POSTGRES_URL"))

# Imported only once the gate passes, so a default (no-database) run never needs psycopg.
import psycopg  # noqa: E402
from axiongraph_store_postgres import PostgresStore  # noqa: E402
from psycopg import sql  # noqa: E402

_counter = itertools.count()
_created_tables: list[str] = []


def _unique_table() -> str:
    table = f"axiongraph_test_{os.getpid()}_{next(_counter)}"
    _created_tables.append(table)
    return table


@pytest.fixture(scope="module", autouse=True)
def _drop_test_tables() -> Iterator[None]:
    yield

    async def drop() -> None:
        async with await psycopg.AsyncConnection.connect(POSTGRES_URL) as conn:
            for table in _created_tables:
                await conn.execute(
                    sql.SQL("DROP TABLE IF EXISTS {table}").format(table=sql.Identifier(table))
                )
            await conn.commit()

    asyncio.run(drop())


@pytest.mark.parametrize(
    "check", [check for _, check in CONTRACT_CHECKS], ids=[name for name, _ in CONTRACT_CHECKS]
)
def test_store_contract(check: ContractCheck) -> None:
    table = _unique_table()

    async def go() -> None:
        store = PostgresStore(POSTGRES_URL, table=table)
        try:
            await check(store)
        finally:
            await store.close()

    asyncio.run(go())


def test_persists_events_across_new_store() -> None:
    table = _unique_table()
    event = node_created("run_persist", 1, "a", "Persisted")

    async def go() -> None:
        writer = PostgresStore(POSTGRES_URL, table=table)
        try:
            await writer.append([event])
        finally:
            await writer.close()

        reader = PostgresStore(POSTGRES_URL, table=table)
        try:
            state = await reader.snapshot("run_persist")
        finally:
            await reader.close()

        assert state.nodes["a"]["label"] == "Persisted"
        assert state.seq == 1

    asyncio.run(go())
