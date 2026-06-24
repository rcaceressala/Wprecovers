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

            # fix_engine.py — RollbackManager (latest applied fix per ticket)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fix_rollback_state (
                    ticket_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)

            # fix_engine.py — FixLog (append-only audit trail)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fix_log (
                    id SERIAL PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS fix_log_ticket_idx ON fix_log (ticket_id)")

            # agents_engine.py — AgentHistoryStore (append-only per ticket)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_history (
                    id SERIAL PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS agent_history_ticket_idx ON agent_history (ticket_id)")

            # agents_engine.py — PendingFixStore (one mutable record per ticket)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_fixes (
                    ticket_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)

            # qa_engine.py — BaselineCapture
            cur.execute("""
                CREATE TABLE IF NOT EXISTS qa_baselines (
                    ticket_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)

            # qa_engine.py — EvidenceLogger (append-only, multiple per ticket)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS qa_evidence (
                    id SERIAL PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS qa_evidence_ticket_idx ON qa_evidence (ticket_id)")

            # billing_engine.py — SubscriptionStore
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    client_id TEXT PRIMARY KEY,
                    plan TEXT NOT NULL,
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    stripe_subscription_item_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # billing_engine.py — UsageTracker (one row per client per month)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usage_records (
                    client_id TEXT NOT NULL,
                    period TEXT NOT NULL,
                    audits_used INTEGER NOT NULL DEFAULT 0,
                    fixes_used INTEGER NOT NULL DEFAULT 0,
                    agents_used INTEGER NOT NULL DEFAULT 0,
                    reports_used INTEGER NOT NULL DEFAULT 0,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY (client_id, period)
                )
            """)

            # report_engine.py — ReportStore (metadata + PDF bytes so downloads
            # survive redeploys too, not just the JSON record)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    ticket_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    pdf_data BYTEA
                )
            """)

            # marketing_engine.py — MarketingPlanStore (metadata + PDF bytes)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS marketing_plans (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    data JSONB NOT NULL,
                    pdf_data BYTEA,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS marketing_plans_project_idx ON marketing_plans (project_id)")

            # marketing_engine.py — ContentPieceStore (Módulo 3 ejecutado: 8 piezas reales por plan)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS content_pieces (
                    plan_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)

            # marketing_engine.py — MarketingActionTicketsStore (Módulo 9 ejecutado: tickets por plan)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS action_tickets (
                    plan_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)

            # marketing_engine.py — WhatsAppMessageStore (Módulo 5 ejecutado: mensajes reales por plan)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_messages (
                    plan_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)

            # marketing_engine.py — Plan90DiasTicketsStore (Módulo 6 ejecutado: tickets por plan)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plan90_tickets (
                    plan_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)

            # marketing_engine.py — IaAutomatizacionStore (Módulo 7 ejecutado: fichas IA por plan)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ia_automatizacion (
                    plan_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
