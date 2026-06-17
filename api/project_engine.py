from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import db
from models import ProjectCreateRequest, ProjectRecord, ProjectStatus

PROJECTS_DIR = Path(__file__).parent / "projects"

# In-process cache: project_id -> ProjectRecord
_projects: Dict[str, ProjectRecord] = {}

# Column order shared by every SQL statement below.
_COLUMNS = [
    "id", "client_name", "site_url", "plan", "notas", "status",
    "score_before", "score_after", "improvement_points", "improvement_pct",
    "guarantee_met", "checks_before", "pagespeed_before", "wprepro_api_key",
    "created_at", "updated_at",
]


def _row_to_record(row: tuple) -> ProjectRecord:
    return ProjectRecord(**dict(zip(_COLUMNS, row)))


class ProjectStore:
    """
    Persists and retrieves project records.

    Uses Postgres (via api/db.py) when DATABASE_URL is configured — required
    in production, since Render web services have an ephemeral filesystem
    that's wiped on every redeploy. Falls back to JSON files on disk for
    local dev when DATABASE_URL isn't set.
    """

    @staticmethod
    def _path(project_id: str) -> Path:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        return PROJECTS_DIR / f"{project_id}.json"

    @classmethod
    def create(cls, req: ProjectCreateRequest) -> ProjectRecord:
        now = datetime.now(timezone.utc).isoformat()
        record = ProjectRecord(
            id=uuid.uuid4().hex[:12],
            client_name=req.client_name,
            site_url=req.site_url,
            plan=req.plan,
            notas=req.notas,
            status=ProjectStatus.DRAFT,
            wprepro_api_key=secrets.token_urlsafe(32),
            created_at=now,
            updated_at=now,
        )
        cls.save(record)
        return record

    @classmethod
    def save(cls, record: ProjectRecord) -> None:
        _projects[record.id] = record

        if db.is_configured():
            from psycopg.types.json import Json

            values = [getattr(record, c) for c in _COLUMNS]
            checks_idx = _COLUMNS.index("checks_before")
            values[checks_idx] = Json(values[checks_idx]) if values[checks_idx] is not None else None

            assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO projects ({", ".join(_COLUMNS)})
                    VALUES ({", ".join(["%s"] * len(_COLUMNS))})
                    ON CONFLICT (id) DO UPDATE SET {assignments}
                    """,
                    values,
                )
            return

        cls._path(record.id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def get(cls, project_id: str) -> Optional[ProjectRecord]:
        if project_id in _projects:
            record = _projects[project_id]
        elif db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM projects WHERE id = %s",
                    (project_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            record = _row_to_record(row)
            _projects[project_id] = record
        else:
            path = cls._path(project_id)
            if not path.exists():
                return None
            record = ProjectRecord(**json.loads(path.read_text(encoding="utf-8")))
            _projects[project_id] = record

        # Backfill: projects created before per-project keys existed.
        if not record.wprepro_api_key:
            record.wprepro_api_key = secrets.token_urlsafe(32)
            cls.save(record)

        return record

    @classmethod
    def delete(cls, project_id: str) -> bool:
        _projects.pop(project_id, None)

        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
                return cur.rowcount > 0

        path = cls._path(project_id)
        if path.exists():
            path.unlink()
            return True
        return False

    @classmethod
    def list_all(cls) -> List[ProjectRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(_COLUMNS)} FROM projects ORDER BY created_at DESC")
                rows = cur.fetchall()
            records = [_row_to_record(r) for r in rows]
            for r in records:
                _projects[r.id] = r
            return records

        if not PROJECTS_DIR.exists():
            return []
        records_by_id: Dict[str, ProjectRecord] = {}
        for f in PROJECTS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                records_by_id[data["id"]] = ProjectRecord(**data)
            except Exception:
                pass
        records_by_id.update(_projects)
        return sorted(records_by_id.values(), key=lambda p: p.created_at, reverse=True)


def resolve_api_key(project_id: Optional[str]) -> str:
    """
    Per-project WPRepro Agent key when `project_id` is known; falls back to
    the legacy global WPREPRO_API_KEY env var for ad-hoc flows that aren't
    tied to a project record (e.g. the Dashboard's standalone Run Audit).
    """
    if project_id:
        record = ProjectStore.get(project_id)
        if record and record.wprepro_api_key:
            return record.wprepro_api_key
    return os.getenv("WPREPRO_API_KEY", "")
