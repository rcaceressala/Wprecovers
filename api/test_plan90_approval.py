"""
Pruebas del flujo de aprobación manual de los tickets del Plan 90 días (M6).

Cubren únicamente la capa de aprobación (generación + estados). NO tocan la
lógica de ejecución (sesión posterior) ni datos de clientes reales: cada test
usa un plan_id temporal y fuerza el file-store (sin DATABASE_URL), escribiendo
en api/plan90_tickets/<plan_id>.json y borrándolo al terminar.

Ejecutar con:  cd api && python -m pytest test_plan90_approval.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

# Forzar el file-store ANTES de importar db/marketing_engine, para que ni
# siquiera intente conectar a una BD real durante los tests.
os.environ.pop("DATABASE_URL", None)

import marketing_engine as me  # noqa: E402
from models import (  # noqa: E402
    Categoria,
    EstadoAprobacion,
    EstadoTicket,
    Plan90DiasTicketsRecord,
    Plan90Ticket,
    Prioridad,
)

TEST_PLAN_ID = "__test_tmp_plan__"


def _mk_ticket(
    ticket_id: str,
    estado_aprobacion: EstadoAprobacion = EstadoAprobacion.pendiente_revision,
) -> Plan90Ticket:
    """Ticket mínimo válido; nace en pendiente_revision salvo que se indique otro."""
    return Plan90Ticket(
        id=ticket_id,
        categoria=Categoria.Marketing,
        titulo="Acción de prueba",
        prioridad=Prioridad.Alta,
        impacto="impacto de prueba",
        agente="MarketingAgent",
        estimacion=90,
        semana=1,
        estado_aprobacion=estado_aprobacion,
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
    """Relee desde el store (disco) para confirmar que los cambios persisten."""
    record = me.Plan90DiasTicketsStore.load(TEST_PLAN_ID)
    return me._find_plan90_ticket(record, ticket_id)


@pytest.fixture(autouse=True)
def _cleanup_temp_plan():
    """Borra el JSON temporal antes y después de cada test."""
    path = me.Plan90DiasTicketsStore._path(TEST_PLAN_ID)
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. approve: pendiente_revision -> aprobado
# ---------------------------------------------------------------------------
def test_approve_pendiente_to_aprobado():
    _seed(_mk_ticket("T1"))

    result = me.approve_plan90_ticket(TEST_PLAN_ID, "T1")

    assert result.estado_aprobacion == EstadoAprobacion.aprobado
    # y persiste en el store, no solo en el objeto devuelto
    assert _reload("T1").estado_aprobacion == EstadoAprobacion.aprobado


# ---------------------------------------------------------------------------
# 2. reject: pendiente_revision -> rechazado, con motivo opcional
# ---------------------------------------------------------------------------
def test_reject_pendiente_to_rechazado():
    _seed(_mk_ticket("T2"), _mk_ticket("T2b"))

    # con motivo
    con_motivo = me.reject_plan90_ticket(
        TEST_PLAN_ID, "T2", motivo="presupuesto insuficiente este mes"
    )
    assert con_motivo.estado_aprobacion == EstadoAprobacion.rechazado
    assert con_motivo.motivo_rechazo == "presupuesto insuficiente este mes"
    assert _reload("T2").motivo_rechazo == "presupuesto insuficiente este mes"

    # sin motivo (el campo es opcional -> None)
    sin_motivo = me.reject_plan90_ticket(TEST_PLAN_ID, "T2b")
    assert sin_motivo.estado_aprobacion == EstadoAprobacion.rechazado
    assert sin_motivo.motivo_rechazo is None


# ---------------------------------------------------------------------------
# 3. transición inválida: approve/reject sobre estados no-pendientes
#    debe lanzar excepción y NO cambiar el estado silenciosamente
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "estado_inicial",
    [EstadoAprobacion.completado, EstadoAprobacion.rechazado, EstadoAprobacion.aprobado],
)
def test_approve_invalido_desde_estado_no_pendiente(estado_inicial):
    _seed(_mk_ticket("T3", estado_aprobacion=estado_inicial))

    with pytest.raises(me.Plan90TicketTransitionError):
        me.approve_plan90_ticket(TEST_PLAN_ID, "T3")

    # el estado no cambió (ni en memoria ni en disco)
    assert _reload("T3").estado_aprobacion == estado_inicial


def test_reject_invalido_desde_completado():
    _seed(_mk_ticket("T4", estado_aprobacion=EstadoAprobacion.completado))

    with pytest.raises(me.Plan90TicketTransitionError):
        me.reject_plan90_ticket(TEST_PLAN_ID, "T4", motivo="tarde")

    reloaded = _reload("T4")
    assert reloaded.estado_aprobacion == EstadoAprobacion.completado
    assert reloaded.motivo_rechazo is None  # no se escribió el motivo


# ---------------------------------------------------------------------------
# 4. estado (EstadoTicket de M9) permanece intacto: approve/reject solo
#    tocan estado_aprobacion
# ---------------------------------------------------------------------------
def test_estado_m9_intacto():
    _seed(_mk_ticket("T5"), _mk_ticket("T6"))

    # antes: ambos en OPEN (default de EstadoTicket)
    assert _reload("T5").estado == EstadoTicket.OPEN
    assert _reload("T6").estado == EstadoTicket.OPEN

    aprobado = me.approve_plan90_ticket(TEST_PLAN_ID, "T5")
    rechazado = me.reject_plan90_ticket(TEST_PLAN_ID, "T6", motivo="no aplica")

    # estado_aprobacion cambió...
    assert aprobado.estado_aprobacion == EstadoAprobacion.aprobado
    assert rechazado.estado_aprobacion == EstadoAprobacion.rechazado
    # ...pero estado (M9) NO
    assert aprobado.estado == EstadoTicket.OPEN
    assert rechazado.estado == EstadoTicket.OPEN
    assert _reload("T5").estado == EstadoTicket.OPEN
    assert _reload("T6").estado == EstadoTicket.OPEN


# ---------------------------------------------------------------------------
# Extra: errores de "no encontrado" (plan sin tickets / ticket inexistente)
# ---------------------------------------------------------------------------
def test_plan_sin_tickets_raise_not_found():
    # sin _seed(): no existe el registro
    with pytest.raises(me.Plan90TicketNotFound):
        me.approve_plan90_ticket(TEST_PLAN_ID, "T1")


def test_ticket_inexistente_raise_not_found():
    _seed(_mk_ticket("T1"))
    with pytest.raises(me.Plan90TicketNotFound):
        me.approve_plan90_ticket(TEST_PLAN_ID, "NO-EXISTE")
