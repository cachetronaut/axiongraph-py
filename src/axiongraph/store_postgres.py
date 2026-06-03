"""The ``axiongraph.store_postgres`` subpath: a durable PostgreSQL GraphStore adapter.

Requires the ``postgres`` extra (``pip install 'axiongraph[postgres]'``), which pulls in
``psycopg``. Mirrors the TypeScript ``axiongraph/store-postgres`` export."""

from __future__ import annotations

from axiongraph_store_postgres import PostgresStore

__all__ = ["PostgresStore"]
