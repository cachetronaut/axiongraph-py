"""The cross-language parity suite. Each case under ``parity/<case>/`` is a language-neutral
fixture both the TypeScript and Python cores must satisfy (spec §"Cross-language parity").

The default operation folds ``events.json`` and compares the canonical state to ``state.json``.
An optional ``manifest.json`` selects ``subgraph`` (fold then filter) or ``validate`` (the event
ids a vocabulary rejects)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from axiongraph_core import (
    GraphState,
    GraphVocabulary,
    canonicalize,
    reduce_all,
    subgraph,
    validate,
)

PARITY_DIR = Path(__file__).parent / "parity"

REQUIRED_CASES = {
    "create_then_update",
    "duplicate_seq",
    "out_of_order_seq",
    "subgraph_chain",
    "unknown_update_dropped",
    "vocabulary_rejection",
}


def _cases() -> list[str]:
    return sorted(entry.name for entry in PARITY_DIR.iterdir() if entry.is_dir())


def _read_json(case: str, name: str) -> Any:
    return json.loads((PARITY_DIR / case / name).read_text())


def _state_from_serialized(serialized: dict[str, Any]) -> GraphState:
    return GraphState(
        run_id=serialized["runId"],
        nodes={node["id"]: node for node in serialized["nodes"]},
        edges={edge["id"]: edge for edge in serialized["edges"]},
        seq=serialized["seq"],
    )


def test_discovers_required_cases() -> None:
    assert REQUIRED_CASES.issubset(set(_cases()))


@pytest.mark.parametrize("case", _cases())
def test_matches_golden_fixture(case: str) -> None:
    events = _read_json(case, "events.json")
    run_id = events[0]["runId"] if events else ""

    manifest_path = PARITY_DIR / case / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    op = manifest.get("op", "reduce")

    if op == "validate":
        vocab = GraphVocabulary(
            node_kinds=frozenset(manifest["vocab"]["nodeKinds"]),
            edge_kinds=frozenset(manifest["vocab"]["edgeKinds"]),
        )
        rejected = [event["id"] for event in events if not validate(event, vocab).ok]
        assert rejected == manifest.get("rejected", [])
        return

    if op == "subgraph":
        keep = set(manifest.get("keepNodeKinds", []))
        folded = subgraph(reduce_all(run_id, events), lambda node: node["kind"] in keep)
        expected = _state_from_serialized(_read_json(case, "state.json"))
        assert canonicalize(folded) == canonicalize(expected)
        return

    folded = reduce_all(run_id, events)
    expected = _state_from_serialized(_read_json(case, "state.json"))
    assert canonicalize(folded) == canonicalize(expected)
