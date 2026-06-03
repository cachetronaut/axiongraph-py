"""Open-taxonomy machinery (spec D2). Core ships the machinery and a neutral example set;
it never hard-codes a domain's vocabulary into the model."""

from __future__ import annotations

from dataclasses import dataclass

from .types import GraphEvent


@dataclass(frozen=True)
class GraphVocabulary:
    """A declared closed vocabulary of allowed node and edge kinds."""

    node_kinds: frozenset[str]
    edge_kinds: frozenset[str]


@dataclass(frozen=True)
class ValidationResult:
    """The typed result of :func:`validate`. ``validate`` never raises on bad input."""

    ok: bool
    reason: str | None = None


def validate(event: GraphEvent, vocab: GraphVocabulary) -> ValidationResult:
    """Reject ``*_created`` events whose kind is outside the supplied vocabulary."""
    if event["type"] == "node_created":
        kind = event["node"]["kind"]
        if kind not in vocab.node_kinds:
            return ValidationResult(ok=False, reason=f"unknown node kind: {kind}")
    if event["type"] == "edge_created":
        kind = event["edge"]["kind"]
        if kind not in vocab.edge_kinds:
            return ValidationResult(ok=False, reason=f"unknown edge kind: {kind}")
    return ValidationResult(ok=True)


# A neutral example vocabulary for docs and tests. Reveals no product domain.
example_vocabulary = GraphVocabulary(
    node_kinds=frozenset(
        {
            "human",
            "agent",
            "task",
            "delegation",
            "connector",
            "tool",
            "artifact",
            "source",
            "approval",
            "policy_decision",
            "budget_check",
            "error",
            "model_call",
        }
    ),
    edge_kinds=frozenset(
        {
            "created_task",
            "delegated_to",
            "handoff_to",
            "called_tool",
            "called_connector",
            "used_model",
            "read_source",
            "created_artifact",
            "requested_approval",
            "approved_by",
            "denied_by",
            "blocked_by_policy",
            "blocked_by_budget",
            "derived_from",
            "cited_source",
            "failed_with",
        }
    ),
)
