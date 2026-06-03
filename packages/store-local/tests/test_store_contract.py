"""The one shared suite every GraphStore adapter must pass, proving adapters are
interchangeable (spec §Testability "Store contract"). Run against both reference stores.

The store API is async; tests drive it with ``asyncio.run`` to avoid a pytest-asyncio dependency."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path
from typing import Any, TypeVar

import pytest
from axiongraph_core import GraphEvent, GraphStore, canonicalize, reduce_all
from axiongraph_store_local import InMemoryStore, SqliteStore

RUN = "run_contract"
OTHER = "run_other"

T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def collect(events: AsyncIterator[GraphEvent]) -> list[GraphEvent]:
    return [event async for event in events]


def node_created(run_id: str, seq: int, node_id: str, label: str) -> GraphEvent:
    return {
        "id": f"{run_id}-e{seq}",
        "runId": run_id,
        "seq": seq,
        "ts": "2026-06-03T00:00:00.000Z",
        "type": "node_created",
        "node": {"id": node_id, "kind": "agent", "label": label},
    }


StoreFactory = Callable[[], GraphStore]

STORES: list[tuple[str, StoreFactory]] = [
    ("InMemoryStore", InMemoryStore),
    ("SqliteStore", SqliteStore),
]


@pytest.fixture(params=STORES, ids=[name for name, _ in STORES])
def store(request: pytest.FixtureRequest) -> GraphStore:
    _name, factory = request.param
    return factory()


def test_returns_empty_state_for_unknown_run(store: GraphStore) -> None:
    state = run(store.snapshot(RUN))
    assert state.seq == 0
    assert len(state.nodes) == 0
    assert len(state.edges) == 0


def test_folds_appended_events_into_snapshot(store: GraphStore) -> None:
    events = [node_created(RUN, 1, "a", "A"), node_created(RUN, 2, "b", "B")]
    run(store.append(events))
    state = run(store.snapshot(RUN))
    assert canonicalize(state) == canonicalize(reduce_all(RUN, events))


def test_is_idempotent_on_run_id_seq(store: GraphStore) -> None:
    events = [node_created(RUN, 1, "a", "A"), node_created(RUN, 2, "b", "B")]
    run(store.append(events))
    run(store.append(events))
    run(store.append([node_created(RUN, 1, "a", "OVERWRITE ATTEMPT")]))
    stored = run(collect(store.read_events(RUN)))
    assert [event["seq"] for event in stored] == [1, 2]
    assert stored[0]["node"]["label"] == "A"


def test_reads_events_in_seq_order_regardless_of_append_order(store: GraphStore) -> None:
    run(store.append([node_created(RUN, 3, "c", "C")]))
    run(store.append([node_created(RUN, 1, "a", "A")]))
    run(store.append([node_created(RUN, 2, "b", "B")]))
    stored = run(collect(store.read_events(RUN)))
    assert [event["seq"] for event in stored] == [1, 2, 3]


def test_filters_reads_by_since_seq(store: GraphStore) -> None:
    run(
        store.append(
            [
                node_created(RUN, 1, "a", "A"),
                node_created(RUN, 2, "b", "B"),
                node_created(RUN, 3, "c", "C"),
            ]
        )
    )
    stored = run(collect(store.read_events(RUN, 1)))
    assert [event["seq"] for event in stored] == [2, 3]


def test_isolates_events_by_run_id(store: GraphStore) -> None:
    run(store.append([node_created(RUN, 1, "a", "A")]))
    run(store.append([node_created(OTHER, 1, "z", "Z")]))
    here = run(collect(store.read_events(RUN)))
    assert [event["id"] for event in here] == [f"{RUN}-e1"]
    other_state = run(store.snapshot(OTHER))
    assert "z" in other_state.nodes
    assert "a" not in other_state.nodes


def test_snapshot_consistent_with_fold_over_read_events(store: GraphStore) -> None:
    events = [
        node_created(RUN, 1, "a", "A"),
        node_created(RUN, 2, "b", "B"),
        node_created(RUN, 3, "c", "C"),
    ]
    run(store.append(events))
    replayed = run(collect(store.read_events(RUN)))
    assert canonicalize(run(store.snapshot(RUN))) == canonicalize(reduce_all(RUN, replayed))


def test_sqlite_persists_events_across_reopen() -> None:
    event = node_created("run_persist", 1, "a", "Persisted")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "events.db")

        writer = SqliteStore(db_path)
        run(writer.append([event]))
        writer.close()

        reader = SqliteStore(db_path)
        state = run(reader.snapshot("run_persist"))
        reader.close()

    assert state.nodes["a"]["label"] == "Persisted"
    assert state.seq == 1
