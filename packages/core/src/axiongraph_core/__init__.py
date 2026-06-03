"""axiongraph-core — the append-only event model, deterministic reducer, canonicalizer,
vocabulary machinery, and the GraphStore port. Published as part of the ``axiongraph`` package."""

from __future__ import annotations

from .canonical import canonicalize
from .reducer import Anomaly, AnomalyKind, OnAnomaly, empty_state, reduce, reduce_all, subgraph
from .store import GraphStore
from .types import (
    EdgePayload,
    EdgeStatus,
    GraphEvent,
    GraphEventType,
    GraphState,
    NodePayload,
)
from .vocabulary import GraphVocabulary, ValidationResult, example_vocabulary, validate

__all__ = [
    "Anomaly",
    "AnomalyKind",
    "EdgePayload",
    "EdgeStatus",
    "GraphEvent",
    "GraphEventType",
    "GraphState",
    "GraphStore",
    "GraphVocabulary",
    "NodePayload",
    "OnAnomaly",
    "ValidationResult",
    "canonicalize",
    "empty_state",
    "example_vocabulary",
    "reduce",
    "reduce_all",
    "subgraph",
    "validate",
]
