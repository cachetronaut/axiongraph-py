"""Runs the shared GraphStore contract (``axiongraph_testkit``) against both reference stores,
proving they are interchangeable (spec §Testability "Store contract"), plus a SQLite-specific
durability check.

The store API is async; tests drive it with ``asyncio.run`` to avoid a pytest-asyncio dependency."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from axiongraph_core import GraphStore
from axiongraph_store_local import InMemoryStore, SqliteStore
from axiongraph_testkit import CONTRACT_CHECKS, ContractCheck, node_created

StoreFactory = Callable[[], GraphStore]

STORES: list[tuple[str, StoreFactory]] = [
    ("InMemoryStore", InMemoryStore),
    ("SqliteStore", SqliteStore),
]


@pytest.fixture(params=STORES, ids=[name for name, _ in STORES])
def store(request: pytest.FixtureRequest) -> GraphStore:
    _name, factory = request.param
    return factory()


@pytest.mark.parametrize(
    "check", [check for _, check in CONTRACT_CHECKS], ids=[name for name, _ in CONTRACT_CHECKS]
)
def test_store_contract(store: GraphStore, check: ContractCheck) -> None:
    asyncio.run(check(store))


def test_sqlite_persists_events_across_reopen() -> None:
    event = node_created("run_persist", 1, "a", "Persisted")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "events.db")

        writer = SqliteStore(db_path)
        asyncio.run(writer.append([event]))
        writer.close()

        reader = SqliteStore(db_path)
        state = asyncio.run(reader.snapshot("run_persist"))
        reader.close()

    assert state.nodes["a"]["label"] == "Persisted"
    assert state.seq == 1
