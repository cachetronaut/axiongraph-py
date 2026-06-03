"""AxionGraph — append-only execution-graph event model and deterministic reducer.

The bare ``axiongraph`` import is the core API; ``axiongraph.store_local`` exposes the
zero-service reference stores. This mirrors the TypeScript package's ``.`` and ``/store-local``
subpath exports."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from axiongraph_core import (
    Anomaly,
    AnomalyKind,
    EdgePayload,
    EdgeStatus,
    GraphEvent,
    GraphEventType,
    GraphState,
    GraphStore,
    GraphVocabulary,
    NodePayload,
    OnAnomaly,
    ValidationResult,
    canonicalize,
    empty_state,
    example_vocabulary,
    reduce,
    reduce_all,
    subgraph,
    validate,
)

try:
    __version__ = version("axiongraph")
except PackageNotFoundError:  # pragma: no cover - only during local source runs
    __version__ = "0.0.0"

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
    "__version__",
    "canonicalize",
    "empty_state",
    "example_vocabulary",
    "reduce",
    "reduce_all",
    "subgraph",
    "validate",
]
