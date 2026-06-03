"""Behavioural tests for the reducer, mirroring the TypeScript suite."""

from __future__ import annotations

from axiongraph_core import (
    Anomaly,
    GraphEvent,
    canonicalize,
    empty_state,
    example_vocabulary,
    reduce,
    reduce_all,
    validate,
)

RUN = "run_1"


def node_created(seq: int, node_id: str, label: str) -> GraphEvent:
    return {
        "id": f"e{seq}",
        "runId": RUN,
        "seq": seq,
        "ts": "2026-06-03T00:00:00.000Z",
        "type": "node_created",
        "node": {"id": node_id, "kind": "agent", "label": label},
    }


def test_creates_then_shallow_merges_a_node_update() -> None:
    events: list[GraphEvent] = [
        node_created(1, "a", "Researcher"),
        {
            "id": "e2",
            "runId": RUN,
            "seq": 2,
            "ts": "2026-06-03T00:00:01.000Z",
            "type": "node_updated",
            "node": {"id": "a", "label": "Research Agent"},
        },
    ]
    state = reduce_all(RUN, events)
    assert state.nodes["a"] == {"id": "a", "kind": "agent", "label": "Research Agent"}
    assert state.seq == 2


def test_is_idempotent_on_a_duplicate_seq() -> None:
    event = node_created(1, "a", "A")
    once = reduce(empty_state(RUN), event)
    twice = reduce(once, event)
    assert canonicalize(twice) == canonicalize(once)


def test_ignores_a_stale_seq_and_reports_it() -> None:
    anomalies: list[Anomaly] = []
    state = reduce(empty_state(RUN), node_created(2, "a", "A"))
    state = reduce(state, node_created(1, "b", "B"), anomalies.append)
    assert "b" not in state.nodes
    assert anomalies[0].kind == "stale_seq"


def test_drops_an_update_to_an_unknown_node_advances_seq_and_reports_it() -> None:
    anomalies: list[Anomaly] = []
    event: GraphEvent = {
        "id": "e1",
        "runId": RUN,
        "seq": 1,
        "ts": "2026-06-03T00:00:00.000Z",
        "type": "node_updated",
        "node": {"id": "ghost", "label": "x"},
    }
    state = reduce(empty_state(RUN), event, anomalies.append)
    assert len(state.nodes) == 0
    assert state.seq == 1
    assert anomalies[0].kind == "update_unknown_node"


def test_is_order_independent_in_reduce_all() -> None:
    a = node_created(1, "a", "A")
    b = node_created(2, "b", "B")
    c = node_created(3, "c", "C")
    assert canonicalize(reduce_all(RUN, [c, a, b])) == canonicalize(reduce_all(RUN, [a, b, c]))


def test_validate_accepts_known_and_rejects_unknown_kind() -> None:
    assert validate(node_created(1, "a", "A"), example_vocabulary).ok is True
    bad: GraphEvent = {
        "id": "e1",
        "runId": RUN,
        "seq": 1,
        "ts": "2026-06-03T00:00:00.000Z",
        "type": "node_created",
        "node": {"id": "a", "kind": "wizard", "label": "A"},
    }
    assert validate(bad, example_vocabulary).ok is False
