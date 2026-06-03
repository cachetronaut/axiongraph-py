"""The append-only event model. The event log is the source of truth (spec D1);
live :class:`GraphState` is always a fold over events, never mutated in place.

The wire shapes mirror the TypeScript contracts and use the same camelCase keys
(``runId``, ``from``) so the cross-language parity fixtures are byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict

GraphEventType = Literal["node_created", "node_updated", "edge_created", "edge_updated"]

EdgeStatus = Literal["proposed", "active", "completed", "failed", "blocked"]


class NodePayload(TypedDict):
    """A node. ``metadata`` is present only when supplied (open taxonomy, spec D2)."""

    id: str
    kind: str
    label: str
    metadata: NotRequired[dict[str, Any]]


# ``from`` is a reserved word, so the edge shape needs the functional TypedDict syntax.
EdgePayload = TypedDict(
    "EdgePayload",
    {
        "id": str,
        "kind": str,
        "from": str,
        "to": str,
        "status": EdgeStatus,
        "metadata": NotRequired[dict[str, Any]],
    },
)


class GraphEvent(TypedDict):
    """A single append-only event. ``node`` / ``edge`` carry full payloads for
    ``*_created`` and partial payloads (``id`` plus changed fields) for ``*_updated``."""

    id: str
    runId: str
    seq: int
    ts: str
    type: GraphEventType
    actor: NotRequired[str]
    node: NotRequired[dict[str, Any]]
    edge: NotRequired[dict[str, Any]]


@dataclass(frozen=True)
class GraphState:
    """The reduced live state: two id-keyed maps plus the last applied sequence."""

    run_id: str
    nodes: dict[str, NodePayload] = field(default_factory=dict)
    edges: dict[str, EdgePayload] = field(default_factory=dict)
    seq: int = 0
