"""axiongraph-store-postgres — a durable PostgreSQL GraphStore adapter (psycopg-backed).
Published as the ``axiongraph.store_postgres`` subpath, gated behind the ``postgres`` extra."""

from __future__ import annotations

from .postgres import PostgresStore

__all__ = ["PostgresStore"]
