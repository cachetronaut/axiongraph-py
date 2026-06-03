"""Deterministic, key-sorted JSON for a state. Identical event logs fold to byte-identical
output (spec D5) — this is the contract the cross-language parity fixtures pin.

Mirrors the TypeScript ``canonicalize``: a ``{runId, seq, nodes, edges}`` shape with nodes and
edges sorted by id, then ``json.dumps`` with sorted keys and no whitespace (matching
``JSON.stringify`` over a recursively key-sorted value)."""

from __future__ import annotations

import json
from typing import Any, cast

from .types import GraphState


def canonicalize(state: GraphState) -> str:
    """Return the canonical, byte-stable JSON string for ``state``."""
    nodes = sorted(state.nodes.values(), key=lambda node: node["id"])
    edges = sorted(state.edges.values(), key=lambda edge: cast(dict[str, Any], edge)["id"])
    shape: dict[str, Any] = {
        "runId": state.run_id,
        "seq": state.seq,
        "nodes": nodes,
        "edges": edges,
    }
    return json.dumps(shape, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
