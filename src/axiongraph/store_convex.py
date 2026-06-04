"""The ``axiongraph.store_convex`` subpath: a client-only Convex GraphStore adapter.

Requires the ``convex`` extra (``pip install 'axiongraph[convex]'``), which pulls in the
``convex`` client. Mirrors the TypeScript ``axiongraph/store-convex`` export. The Convex component
itself ships only in the TypeScript package (Convex bundles it on deploy); this is the external
client that drives a deployment running it."""

from __future__ import annotations

from axiongraph_store_convex import ConvexStore

__all__ = ["ConvexStore"]
