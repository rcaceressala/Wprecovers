from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import ProjectCreateRequest, ProjectRecord, ProjectStatus

PROJECTS_DIR = Path(__file__).parent / "projects"

# In-process cache: project_id -> ProjectRecord
_projects: Dict[str, ProjectRecord] = {}


class ProjectStore:
    """Persists and retrieves project records as JSON."""

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
        cls._path(record.id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def get(cls, project_id: str) -> Optional[ProjectRecord]:
        if project_id in _projects:
            record = _projects[project_id]
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
        path = cls._path(project_id)
        if path.exists():
            path.unlink()
            return True
        return False

    @classmethod
    def list_all(cls) -> List[ProjectRecord]:
        if not PROJECTS_DIR.exists():
            return []
        records: Dict[str, ProjectRecord] = {}
        for f in PROJECTS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                records[data["id"]] = ProjectRecord(**data)
            except Exception:
                pass
        records.update(_projects)
        return sorted(records.values(), key=lambda p: p.created_at, reverse=True)


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
