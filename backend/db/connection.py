"""
ForgeSight — Postgres connectivity (Supabase). A lazily-opened psycopg connection pool
shared by tools (RAG, spares), the audit sink, and persistence.

`DATABASE_URL` must be the Supabase connection string (Project Settings → Database →
Connection string → URI; use the pooler host). pgvector is enabled by migrations.sql.
"""

from __future__ import annotations

from functools import lru_cache

import psycopg
from psycopg_pool import ConnectionPool

from backend.config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    url = get_settings().database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is empty. Set it in .env "
            "(Supabase → Project Settings → Database → Connection string / URI)."
        )
    # open=True keeps the pool warm; conservative sizing for the free tier.
    return ConnectionPool(url, min_size=1, max_size=5, open=True, kwargs={"autocommit": True})


def connect() -> psycopg.Connection:
    """A standalone autocommit connection (used by scripts / migrations)."""
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is empty — see .env.")
    return psycopg.connect(url, autocommit=True)


def healthcheck() -> bool:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)
    except Exception:  # noqa: BLE001
        return False
