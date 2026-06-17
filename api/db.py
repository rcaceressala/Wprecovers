"""
Optional Postgres persistence layer.

DATABASE_URL unset -> every Store class below falls back to its original
JSON-file behavior (unchanged, used in local dev). DATABASE_URL set -> data
survives Render redeploys, which wipe the web service's ephemeral disk.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

DATABASE_URL = os.getenv("DATABASE_URL")


def is_configured() -> bool:
    return bool(DATABASE_URL)


@contextmanager
def get_connection() -> Iterator["psycopg.Connection"]:  # noqa: F821
    import psycopg  # imported lazily so local dev without DATABASE_URL never needs it installed

    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call on every startup."""
    if not is_configured():
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    site_url TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    notas TEXT,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    score_before DOUBLE PRECISION,
                    score_after DOUBLE PRECISION,
                    improvement_points DOUBLE PRECISION,
                    improvement_pct DOUBLE PRECISION,
                    guarantee_met BOOLEAN,
                    checks_before JSONB,
                    pagespeed_before DOUBLE PRECISION,
                    wprepro_api_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
