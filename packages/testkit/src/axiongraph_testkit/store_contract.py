"""The one shared GraphStore contract every adapter must pass, proving adapters are
interchangeable (spec §Testability "Store contract"). Dev-only — never shipped in the
published wheel. Mirrors the TypeScript ``@axiongraph/testkit``.

Each check is an async function over an already-constructed store, so consumers own store
construction and teardown. That lets gated/async backends (e.g. Postgres) supply their own
setup while reusing the exact same behavioral assertions as the local stores."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from axiongraph_core import GraphEvent, GraphStore, canonicalize, reduce_all

RUN = "run_contract"
OTHER = "run_other"


def node_created(run_id: str, seq: int, node_id: str, label: str) -> GraphEvent:
    return {
        "id": f"{run_id}-e{seq}",
        "runId": run_id,
        "seq": seq,
        "ts": "2026-06-03T00:00:00.000Z",
        "type": "node_created",
        "node": {"id": node_id, "kind": "agent", "label": label},
    }


async def _collect(events: AsyncIterator[GraphEvent]) -> list[GraphEvent]:
    return [event async for event in events]


async def check_returns_empty_state_for_unknown_run(store: GraphStore) -> None:
    state = await store.snapshot(RUN)
    assert state.seq == 0
    assert len(state.nodes) == 0
    assert len(state.edges) == 0


async def check_folds_appended_events_into_snapshot(store: GraphStore) -> None:
    events = [node_created(RUN, 1, "a", "A"), node_created(RUN, 2, "b", "B")]
    await store.append(events)
    state = await store.snapshot(RUN)
    assert canonicalize(state) == canonicalize(reduce_all(RUN, events))


async def check_is_idempotent_on_run_id_seq(store: GraphStore) -> None:
    events = [node_created(RUN, 1, "a", "A"), node_created(RUN, 2, "b", "B")]
    await store.append(events)
    await store.append(events)
    await store.append([node_created(RUN, 1, "a", "OVERWRITE ATTEMPT")])
    stored = await _collect(store.read_events(RUN))
    assert [event["seq"] for event in stored] == [1, 2]
    assert stored[0]["node"]["label"] == "A"


async def check_reads_events_in_seq_order_regardless_of_append_order(store: GraphStore) -> None:
    await store.append([node_created(RUN, 3, "c", "C")])
    await store.append([node_created(RUN, 1, "a", "A")])
    await store.append([node_created(RUN, 2, "b", "B")])
    stored = await _collect(store.read_events(RUN))
    assert [event["seq"] for event in stored] == [1, 2, 3]


async def check_filters_reads_by_since_seq(store: GraphStore) -> None:
    await store.append(
        [
            node_created(RUN, 1, "a", "A"),
            node_created(RUN, 2, "b", "B"),
            node_created(RUN, 3, "c", "C"),
        ]
    )
    stored = await _collect(store.read_events(RUN, 1))
    assert [event["seq"] for event in stored] == [2, 3]


async def check_isolates_events_by_run_id(store: GraphStore) -> None:
    await store.append([node_created(RUN, 1, "a", "A")])
    await store.append([node_created(OTHER, 1, "z", "Z")])
    here = await _collect(store.read_events(RUN))
    assert [event["id"] for event in here] == [f"{RUN}-e1"]
    other_state = await store.snapshot(OTHER)
    assert "z" in other_state.nodes
    assert "a" not in other_state.nodes


async def check_snapshot_consistent_with_fold_over_read_events(store: GraphStore) -> None:
    events = [
        node_created(RUN, 1, "a", "A"),
        node_created(RUN, 2, "b", "B"),
        node_created(RUN, 3, "c", "C"),
    ]
    await store.append(events)
    replayed = await _collect(store.read_events(RUN))
    assert canonicalize(await store.snapshot(RUN)) == canonicalize(reduce_all(RUN, replayed))


ContractCheck = Callable[[GraphStore], Coroutine[Any, Any, None]]

CONTRACT_CHECKS: list[tuple[str, ContractCheck]] = [
    ("returns_empty_state_for_unknown_run", check_returns_empty_state_for_unknown_run),
    ("folds_appended_events_into_snapshot", check_folds_appended_events_into_snapshot),
    ("is_idempotent_on_run_id_seq", check_is_idempotent_on_run_id_seq),
    (
        "reads_events_in_seq_order_regardless_of_append_order",
        check_reads_events_in_seq_order_regardless_of_append_order,
    ),
    ("filters_reads_by_since_seq", check_filters_reads_by_since_seq),
    ("isolates_events_by_run_id", check_isolates_events_by_run_id),
    (
        "snapshot_consistent_with_fold_over_read_events",
        check_snapshot_consistent_with_fold_over_read_events,
    ),
]
