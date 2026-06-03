"""The deterministic reducer. Pure and side-effect free (spec D5): no clock, no I/O,
no randomness. Identical event sequences fold to identical state."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

from .types import EdgePayload, GraphEvent, GraphState, NodePayload

AnomalyKind = Literal["wrong_run", "stale_seq", "update_unknown_node", "update_unknown_edge"]


@dataclass(frozen=True)
class Anomaly:
    """Something the reducer noticed but did not apply. Observation only, never raised."""

    kind: AnomalyKind
    event: GraphEvent


OnAnomaly = Callable[[Anomaly], None]


def empty_state(run_id: str) -> GraphState:
    """The fold's seed. ``seq`` starts at 0; the first applied event must have ``seq >= 1``."""
    return GraphState(run_id=run_id, nodes={}, edges={}, seq=0)


def _report(on_anomaly: OnAnomaly | None, kind: AnomalyKind, event: GraphEvent) -> None:
    if on_anomaly is not None:
        on_anomaly(Anomaly(kind=kind, event=event))


def reduce(state: GraphState, event: GraphEvent, on_anomaly: OnAnomaly | None = None) -> GraphState:
    """Apply one event. Events for another run, or with a non-increasing ``seq``, are
    ignored idempotently (spec D3). Updates to unknown ids are dropped (spec D6)."""
    if event["runId"] != state.run_id:
        _report(on_anomaly, "wrong_run", event)
        return state
    if event["seq"] <= state.seq:
        _report(on_anomaly, "stale_seq", event)
        return state

    event_type = event["type"]

    if event_type == "node_created":
        nodes = dict(state.nodes)
        node = cast(NodePayload, event["node"])
        nodes[node["id"]] = node
        return replace(state, nodes=nodes, seq=event["seq"])

    if event_type == "node_updated":
        update = event["node"]
        existing = state.nodes.get(update["id"])
        if existing is None:
            _report(on_anomaly, "update_unknown_node", event)
            return replace(state, seq=event["seq"])
        nodes = dict(state.nodes)
        nodes[update["id"]] = cast(NodePayload, {**existing, **update})
        return replace(state, nodes=nodes, seq=event["seq"])

    if event_type == "edge_created":
        edges = dict(state.edges)
        edge = cast(EdgePayload, event["edge"])
        edges[edge["id"]] = edge
        return replace(state, edges=edges, seq=event["seq"])

    if event_type == "edge_updated":
        update = event["edge"]
        existing = state.edges.get(update["id"])
        if existing is None:
            _report(on_anomaly, "update_unknown_edge", event)
            return replace(state, seq=event["seq"])
        edges = dict(state.edges)
        edges[update["id"]] = cast(EdgePayload, {**existing, **update})
        return replace(state, edges=edges, seq=event["seq"])

    return state


def reduce_all(
    run_id: str, events: Iterable[GraphEvent], on_anomaly: OnAnomaly | None = None
) -> GraphState:
    """Fold an event log into state. Sorted by ``seq`` first, so arrival order does not matter."""
    state = empty_state(run_id)
    for event in sorted(events, key=lambda candidate: candidate["seq"]):
        state = reduce(state, event, on_anomaly)
    return state


def subgraph(state: GraphState, keep_node: Callable[[NodePayload], bool]) -> GraphState:
    """Derive a filtered view: keep matching nodes and any edge whose endpoints both survive."""
    nodes = {node_id: node for node_id, node in state.nodes.items() if keep_node(node)}
    edges: dict[str, EdgePayload] = {}
    for edge_id, edge in state.edges.items():
        endpoints: dict[str, Any] = cast(dict[str, Any], edge)
        if endpoints["from"] in nodes and endpoints["to"] in nodes:
            edges[edge_id] = edge
    return replace(state, nodes=nodes, edges=edges)
