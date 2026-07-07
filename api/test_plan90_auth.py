"""
Pruebas de la capa de auth de los PATCH approve/reject de tickets del Plan 90
días (M6). Complementan test_plan90_approval.py (que cubre la lógica de estados
a nivel de motor); aquí se ejercita el borde HTTP: la key de admin, la identidad
del operador (X-Actor) y el comportamiento fail-closed.

Cada test controla WPREPRO_ADMIN_KEY vía monkeypatch (no depende de api/.env) y
usa un plan_id temporal sobre el file-store, borrándolo al terminar.

Ejecutar con:  cd api && python -m pytest test_plan90_auth.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

# Forzar el file-store ANTES de importar db/marketing_engine/main.
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

import marketing_engine as me  # noqa: E402
from main import app  # noqa: E402
from models import (  # noqa: E402
    Categoria,
    EstadoAprobacion,
    Plan90DiasTicketsRecord,
    Plan90Ticket,
    Prioridad,
)

TEST_PLAN_ID = "__test_auth_plan__"
ADMIN_KEY = "test-admin-key-123"

client = TestClient(app)


def _mk_ticket(ticket_id: str) -> Plan90Ticket:
    return Plan90Ticket(
        id=ticket_id,
        categoria=Categoria.Marketing,
        titulo="Acción de prueba",
        prioridad=Prioridad.Alta,
        impacto="impacto de prueba",
        agente="MarketingAgent",
        estimacion=90,
        semana=1,
        estado_aprobacion=EstadoAprobacion.pendiente_revision,
    )


def _seed(*tickets: Plan90Ticket) -> None:
    me.Plan90DiasTicketsStore.save(
        Plan90DiasTicketsRecord(
            plan_id=TEST_PLAN_ID,
            tickets=list(tickets),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )


def _reload(ticket_id: str) -> Plan90Ticket:
    record = me.Plan90DiasTicketsStore.load(TEST_PLAN_ID)
    return me._find_plan90_ticket(record, ticket_id)


def _approve_url(ticket_id: str) -> str:
    return f"/marketing/{TEST_PLAN_ID}/tickets/{ticket_id}/approve"


def _reject_url(ticket_id: str) -> str:
    return f"/marketing/{TEST_PLAN_ID}/tickets/{ticket_id}/reject"


@pytest.fixture(autouse=True)
def _env_and_cleanup(monkeypatch):
    """Key de admin configurada por defecto (los tests que prueben el caso
    fail-closed la borran) y limpieza del JSON temporal antes/después."""
    monkeypatch.setenv("WPREPRO_ADMIN_KEY", ADMIN_KEY)
    path = me.Plan90DiasTicketsStore._path(TEST_PLAN_ID)
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. Sin X-Admin-Key -> 401 y el ticket NO cambia
# ---------------------------------------------------------------------------
def test_approve_sin_key_401():
    _seed(_mk_ticket("A1"))
    r = client.patch(_approve_url("A1"), headers={"X-Actor": "ana@wp.cl"})
    assert r.status_code == 401
    assert _reload("A1").estado_aprobacion == EstadoAprobacion.pendiente_revision


# ---------------------------------------------------------------------------
# 2. Key incorrecta -> 401
# ---------------------------------------------------------------------------
def test_approve_key_incorrecta_401():
    _seed(_mk_ticket("A2"))
    r = client.patch(
        _approve_url("A2"),
        headers={"X-Admin-Key": "clave-equivocada", "X-Actor": "ana@wp.cl"},
    )
    assert r.status_code == 401
    assert _reload("A2").estado_aprobacion == EstadoAprobacion.pendiente_revision


# ---------------------------------------------------------------------------
# 3. Key correcta pero sin X-Actor -> 400 (la identidad es obligatoria)
# ---------------------------------------------------------------------------
def test_approve_sin_actor_400():
    _seed(_mk_ticket("A3"))
    r = client.patch(_approve_url("A3"), headers={"X-Admin-Key": ADMIN_KEY})
    assert r.status_code == 400
    assert _reload("A3").estado_aprobacion == EstadoAprobacion.pendiente_revision


# ---------------------------------------------------------------------------
# 4. Key + X-Actor correctos -> 200, aprobado y aprobado_por persistido
# ---------------------------------------------------------------------------
def test_approve_ok_persiste_identidad():
    _seed(_mk_ticket("A4"))
    r = client.patch(
        _approve_url("A4"),
        headers={"X-Admin-Key": ADMIN_KEY, "X-Actor": "ana@wp.cl"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["estado_aprobacion"] == EstadoAprobacion.aprobado.value
    assert body["aprobado_por"] == "ana@wp.cl"
    reloaded = _reload("A4")
    assert reloaded.estado_aprobacion == EstadoAprobacion.aprobado
    assert reloaded.aprobado_por == "ana@wp.cl"


# ---------------------------------------------------------------------------
# 5. reject con key + X-Actor -> 200, rechazado_por y motivo persistidos
# ---------------------------------------------------------------------------
def test_reject_ok_persiste_identidad_y_motivo():
    _seed(_mk_ticket("A5"))
    r = client.patch(
        _reject_url("A5"),
        headers={"X-Admin-Key": ADMIN_KEY, "X-Actor": "leo@wp.cl"},
        json={"motivo": "fuera de presupuesto"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["estado_aprobacion"] == EstadoAprobacion.rechazado.value
    assert body["rechazado_por"] == "leo@wp.cl"
    assert body["motivo_rechazo"] == "fuera de presupuesto"
    reloaded = _reload("A5")
    assert reloaded.rechazado_por == "leo@wp.cl"


# ---------------------------------------------------------------------------
# 6. Fail-closed: sin WPREPRO_ADMIN_KEY en el servidor -> 503 aunque la
#    petición traiga headers
# ---------------------------------------------------------------------------
def test_fail_closed_sin_env_503(monkeypatch):
    monkeypatch.delenv("WPREPRO_ADMIN_KEY", raising=False)
    _seed(_mk_ticket("A6"))
    r = client.patch(
        _approve_url("A6"),
        headers={"X-Admin-Key": ADMIN_KEY, "X-Actor": "ana@wp.cl"},
    )
    assert r.status_code == 503
    assert _reload("A6").estado_aprobacion == EstadoAprobacion.pendiente_revision
