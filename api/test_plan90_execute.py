"""
Pruebas de la ejecución real de tickets del Plan 90 días (M6 Sesión 3).

Cubren la máquina de estados de /execute, la resolución de la key POR PROYECTO
(sin fallback al WPREPRO_API_KEY global — ese fallback causó los 403 en clientes
reales) y el log de auditoría. El WPRepro Agent se mockea (no se toca ningún sitio
real) y todo corre sobre el file-store con ids temporales.

Ejecutar con:  cd api && python -m pytest test_plan90_execute.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.pop("DATABASE_URL", None)  # forzar file-store antes de importar

import marketing_engine as me  # noqa: E402
from models import (  # noqa: E402
    Categoria,
    EstadoAprobacion,
    Plan90DiasTicketsRecord,
    Plan90Ticket,
    Prioridad,
    ProjectCreateRequest,
)

TEST_PLAN_ID = "__test_exec_plan__"
ACTOR = "ana@wp.cl"


class _FakeClient:
    """Reemplazo de WPAgentClient que registra la construcción y la llamada."""
    last: dict = {}

    def __init__(self, site_url: str, api_key: str):
        _FakeClient.last = {"site_url": site_url, "api_key": api_key}

    def execute(self, commands):
        _FakeClient.last["commands"] = commands
        return {"results": [{"command": c, "ok": True} for c in commands]}


class _FailingClient:
    def __init__(self, site_url: str, api_key: str):
        pass

    def execute(self, commands):
        raise RuntimeError("403 Forbidden del WPRepro Agent")


def _mk_ticket(
    ticket_id: str,
    *,
    project_id,
    modulo_origen: str = me.EXECUTABLE_MODULO,
    estado: EstadoAprobacion = EstadoAprobacion.aprobado,
) -> Plan90Ticket:
    return Plan90Ticket(
        id=ticket_id,
        categoria=Categoria.Marketing,
        titulo="SSL/HTTPS no configurado",
        prioridad=Prioridad.Alta,
        impacto="impacto de prueba",
        agente="MarketingAgent",
        estimacion=45,
        semana=1,
        project_id=project_id,
        modulo_origen=modulo_origen,
        estado_aprobacion=estado,
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
    return me._find_plan90_ticket(me.Plan90DiasTicketsStore.load(TEST_PLAN_ID), ticket_id)


@pytest.fixture()
def project_id():
    """Proyecto real (file-store) con site_url + wprepro_api_key propias."""
    rec = me.ProjectStore.create(
        ProjectCreateRequest(client_name="Test SA", site_url="https://test.example", plan="starter")
    )
    yield rec.id
    me.ProjectStore.delete(rec.id)


def _clear_exec_logs() -> None:
    for tid in ("E1", "E2", "E3", "E4", "E5", "E6"):
        me.Plan90ExecutionLog._path(tid).unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _cleanup():
    tickets_path = me.Plan90DiasTicketsStore._path(TEST_PLAN_ID)
    tickets_path.unlink(missing_ok=True)
    _clear_exec_logs()
    _FakeClient.last = {}
    yield
    tickets_path.unlink(missing_ok=True)
    _clear_exec_logs()


# ---------------------------------------------------------------------------
# 1. Happy path: aprobado -> completado, usa la key del proyecto, loguea
# ---------------------------------------------------------------------------
def test_execute_ok(project_id, monkeypatch):
    monkeypatch.setattr(me, "WPAgentClient", _FakeClient)
    project = me.ProjectStore.get(project_id)
    _seed(_mk_ticket("E1", project_id=project_id))

    result = me.execute_plan90_ticket(TEST_PLAN_ID, "E1", actor=ACTOR)

    assert result.estado_aprobacion == EstadoAprobacion.completado
    assert result.ejecutado_por == ACTOR
    assert result.error_ejecucion is None
    assert _reload("E1").estado_aprobacion == EstadoAprobacion.completado
    # usó la key/site del PROYECTO, no la global
    assert _FakeClient.last["api_key"] == project.wprepro_api_key
    assert _FakeClient.last["site_url"] == "https://test.example"
    # auditoría: started + completed
    outcomes = [e.outcome for e in me.Plan90ExecutionLog.read("E1")]
    assert outcomes == ["started", "completed"]


# ---------------------------------------------------------------------------
# 2. Guard de estado: solo 'aprobado' es ejecutable
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "estado",
    [EstadoAprobacion.pendiente_revision, EstadoAprobacion.rechazado, EstadoAprobacion.completado],
)
def test_execute_estado_invalido(project_id, monkeypatch, estado):
    monkeypatch.setattr(me, "WPAgentClient", _FakeClient)
    _seed(_mk_ticket("E2", project_id=project_id, estado=estado))
    with pytest.raises(me.Plan90TicketTransitionError):
        me.execute_plan90_ticket(TEST_PLAN_ID, "E2", actor=ACTOR)
    assert _reload("E2").estado_aprobacion == estado  # sin cambios


# ---------------------------------------------------------------------------
# 3. Subset ejecutable: modulo_origen no técnico -> NotExecutable
# ---------------------------------------------------------------------------
def test_execute_no_ejecutable(project_id, monkeypatch):
    monkeypatch.setattr(me, "WPAgentClient", _FakeClient)
    _seed(_mk_ticket("E3", project_id=project_id, modulo_origen="Módulo 5: Estrategia WhatsApp"))
    with pytest.raises(me.Plan90TicketNotExecutable):
        me.execute_plan90_ticket(TEST_PLAN_ID, "E3", actor=ACTOR)
    assert _reload("E3").estado_aprobacion == EstadoAprobacion.aprobado


# ---------------------------------------------------------------------------
# 4. Sin project_id -> ConfigError y NO usa la key global (aunque esté seteada)
# ---------------------------------------------------------------------------
def test_execute_sin_project_no_usa_global(monkeypatch):
    monkeypatch.setenv("WPREPRO_API_KEY", "GLOBAL-NO-DEBE-USARSE")
    called = {"n": 0}

    class _Spy(_FakeClient):
        def __init__(self, site_url, api_key):
            called["n"] += 1
            super().__init__(site_url, api_key)

    monkeypatch.setattr(me, "WPAgentClient", _Spy)
    _seed(_mk_ticket("E4", project_id=None))

    with pytest.raises(me.Plan90ExecutionConfigError):
        me.execute_plan90_ticket(TEST_PLAN_ID, "E4", actor=ACTOR)

    assert called["n"] == 0  # nunca se construyó un cliente -> no hubo fallback global
    assert _reload("E4").estado_aprobacion == EstadoAprobacion.aprobado  # estado intacto


# ---------------------------------------------------------------------------
# 5. Proyecto inexistente -> ConfigError
# ---------------------------------------------------------------------------
def test_execute_proyecto_inexistente(monkeypatch):
    monkeypatch.setattr(me, "WPAgentClient", _FakeClient)
    _seed(_mk_ticket("E5", project_id="no-existe-999"))
    with pytest.raises(me.Plan90ExecutionConfigError):
        me.execute_plan90_ticket(TEST_PLAN_ID, "E5", actor=ACTOR)


# ---------------------------------------------------------------------------
# 6. Falla del WPRepro Agent -> vuelve a 'aprobado' con error_ejecucion + log
# ---------------------------------------------------------------------------
def test_execute_falla_wp_vuelve_a_aprobado(project_id, monkeypatch):
    monkeypatch.setattr(me, "WPAgentClient", _FailingClient)
    _seed(_mk_ticket("E6", project_id=project_id))

    with pytest.raises(me.Plan90ExecutionError):
        me.execute_plan90_ticket(TEST_PLAN_ID, "E6", actor=ACTOR)

    reloaded = _reload("E6")
    assert reloaded.estado_aprobacion == EstadoAprobacion.aprobado  # reintentable
    assert "403" in (reloaded.error_ejecucion or "")
    outcomes = [e.outcome for e in me.Plan90ExecutionLog.read("E6")]
    assert outcomes == ["started", "failed"]
