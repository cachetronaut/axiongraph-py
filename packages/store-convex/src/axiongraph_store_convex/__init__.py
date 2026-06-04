"""axiongraph-store-convex — a client-only Convex GraphStore adapter.
Published as the ``axiongraph.store_convex`` subpath, gated behind the ``convex`` extra."""

from __future__ import annotations

from .convex import ConvexStore

__all__ = ["ConvexStore"]
