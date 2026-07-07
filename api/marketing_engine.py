from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import db
from models import (
    Categoria,
    ContentCalendarItem,
    ContentJobStatus,
    ContentPiece,
    ContentPiecesRecord,
    EstadoAprobacion,
    IaAutomatizacionItem,
    IaAutomatizacionRecord,
    MarketingActionTicketsRecord,
    MarketingGenerateRequest,
    MarketingPlan,
    MarketingPlanRecord,
    MetricaItem,
    MetricasClaveRecord,
    Plan90Dias,
    Plan90DiasTicketsRecord,
    Plan90ExecutionLogEntry,
    Plan90Ticket,
    Prioridad,
    Ticket,
    WhatsAppMessage,
    WhatsAppMessagesRecord,
)
from audit_engine import run_full_audit
from project_engine import ProjectStore
from wp_agent_client import WPAgentClient

PLANS_DIR = Path(__file__).parent / "marketing_plans"
CONTENT_DIR = Path(__file__).parent / "content_pieces"
ACTIONS_DIR = Path(__file__).parent / "action_tickets"
MESSAGES_DIR = Path(__file__).parent / "whatsapp_messages"
PLAN90_DIR = Path(__file__).parent / "plan90_tickets"
IA_DIR = Path(__file__).parent / "ia_automatizacion"
METRICAS_DIR = Path(__file__).parent / "metricas_clave"

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 32000
# El SDK de anthropic usa por defecto 600s de read timeout. Generar 8 piezas de
# contenido con max_tokens=32000 puede superar ese límite bajo carga, así que lo
# subimos explícitamente (con margen sobre el mínimo de 120s pedido).
_CLIENT_TIMEOUT = 900.0


def _anthropic_client(_anthropic: Any) -> Any:
    return _anthropic.Anthropic(timeout=_CLIENT_TIMEOUT)

# ---------------------------------------------------------------------------
# MarketingAgent — generates the 9-module plan via the Anthropic API
# ---------------------------------------------------------------------------

_JSON_SCHEMA = """\
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin bloques markdown):
{
  "diagnostico_inicial": ["hallazgo 1...", "hallazgo 2...", "..."],
  "estrategia_adquisicion": ["canal/táctica 1...", "..."],
  "calendario_contenido": [
    {"dia": 1, "objetivo": "...", "formato": "Reel|Post|Historia|Blog|Email", "guion": "...", "cta": "..."},
    "... exactamente 8 piezas distribuidas en los 30 días ..."
  ],
  "embudo_ventas": ["Anuncio: ...", "Landing: ...", "WhatsApp: ...", "Cotización: ...", "Venta: ...", "Seguimiento: ...", "Referidos: ..."],
  "estrategia_whatsapp": ["mensaje automático de bienvenida...", "seguimiento...", "reactivación...", "solicitud de reseña..."],
  "plan_ejecucion_90_dias": {
    "semana_1_2": ["acción...", "..."],
    "semana_3_4": ["acción...", "..."],
    "mes_2": ["acción...", "..."],
    "mes_3": ["acción...", "..."]
  },
  "ia_automatizacion": ["herramienta + uso concreto...", "..."],
  "metricas_clave": ["CPL: definición y cómo medirla en este caso...", "..."],
  "top_10_acciones": ["acción 1 de mayor impacto en 7 días...", "... exactamente 10 acciones ..."]
}"""

_SYSTEM_PROMPT = f"""Eres MarketingAgent, estratega de growth y marketing digital para PYMEs LATAM dentro de WPRecover 2.0.
Generas planes de marketing completos y accionables para clientes WordPress/WooCommerce a partir de
su diagnóstico técnico real, su rubro, ciudad y presupuesto disponible.

PRINCIPIOS:
- Personaliza cada módulo con los datos reales del sitio (Recovery Score, PageSpeed, checks fallidos) —
  nunca generes un plan genérico que ignore esos datos.
- Ajusta tácticas y presupuesto sugerido al nivel de "monthly_budget" (bajo/medio/alto) y al paquete
  WPRecover contratado (starter/growth/scale/elite): paquetes más altos habilitan tácticas más ambiciosas.
- Sé concreto: nombres de herramientas, textos de ejemplo, cifras y plazos reales, no genéricos.
- Todo el contenido debe estar en español neutro LATAM.

{_JSON_SCHEMA}"""


class MarketingAgent:
    NOMBRE = "MarketingAgent"
    MODEL = _MODEL

    def run(self, req: MarketingGenerateRequest, audit_context: str) -> Tuple[MarketingPlan, int]:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'anthropic>=0.40.0'"
            ) from exc

        client = _anthropic_client(_anthropic)
        user_msg = self._build_user_message(req, audit_context)
        messages = [{"role": "user", "content": user_msg}]

        text, tokens, stop_reason = self._invoke(client, messages)
        parsed = self._parse_json(text)

        required_keys = (
            "diagnostico_inicial", "estrategia_adquisicion", "calendario_contenido",
            "embudo_ventas", "estrategia_whatsapp", "plan_ejecucion_90_dias",
            "ia_automatizacion", "metricas_clave", "top_10_acciones",
        )
        if not parsed or not all(parsed.get(k) for k in required_keys):
            hint = (
                "la respuesta se truncó por max_tokens — sube _MAX_TOKENS"
                if stop_reason == "max_tokens"
                else "la respuesta no es JSON válido o le faltan módulos"
            )
            raise RuntimeError(
                f"MarketingAgent: no se pudo generar un plan completo ({hint}). "
                f"stop_reason={stop_reason}, respuesta cruda (primeros 500 chars): {text[:500]!r}"
            )

        plan = MarketingPlan(
            diagnostico_inicial=parsed.get("diagnostico_inicial", []),
            estrategia_adquisicion=parsed.get("estrategia_adquisicion", []),
            calendario_contenido=[
                ContentCalendarItem(**item) for item in parsed.get("calendario_contenido", [])
            ],
            embudo_ventas=parsed.get("embudo_ventas", []),
            estrategia_whatsapp=parsed.get("estrategia_whatsapp", []),
            plan_ejecucion_90_dias=Plan90Dias(**parsed.get("plan_ejecucion_90_dias", {
                "semana_1_2": [], "semana_3_4": [], "mes_2": [], "mes_3": [],
            })),
            ia_automatizacion=parsed.get("ia_automatizacion", []),
            metricas_clave=parsed.get("metricas_clave", []),
            top_10_acciones=parsed.get("top_10_acciones", []),
        )
        return plan, tokens

    def _invoke(self, client: Any, messages: List[Dict[str, Any]]) -> Tuple[str, int, str]:
        with client.messages.stream(
            model=self.MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens, response.stop_reason

    @staticmethod
    def _build_user_message(req: MarketingGenerateRequest, audit_context: str) -> str:
        return (
            f"DATOS DEL CLIENTE:\n"
            f"Sitio: {req.site_url}\n"
            f"Rubro: {req.business_type}\n"
            f"Ciudad: {req.city}\n"
            f"Presupuesto mensual: {req.monthly_budget}\n"
            f"Paquete WPRecover contratado: {req.plan}\n\n"
            f"DIAGNÓSTICO TÉCNICO REAL DEL SITIO (audit_engine, no asumas otros valores):\n"
            f"{audit_context}\n\n"
            "Genera el plan de marketing completo de 9 módulos siguiendo exactamente el esquema indicado."
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean.strip())
        try:
            return json.loads(clean)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


_CONTENT_JSON_SCHEMA = """\
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin bloques markdown):
{
  "piezas": [
    {
      "dia": 1,
      "formato": "Reel|Post|Historia|Blog|Email",
      "objetivo": "...",
      "texto_completo": "texto final del post/guion, listo para publicar, en español neutro LATAM...",
      "prompt_imagen": "prompt detallado para generar la imagen/portada con IA (estilo, composición, colores)...",
      "hashtags": ["#hashtag1", "#hashtag2", "..."],
      "mejor_horario": "Día de la semana + hora sugerida, ej. 'Martes 18:00'"
    },
    "... una entrada por cada pieza del calendario recibido, mismo orden, mismo número de piezas ..."
  ]
}"""

_CONTENT_SYSTEM_PROMPT = f"""Eres ContentAgent, redactor senior de contenido para redes sociales de PYMEs LATAM
dentro de WPRecover 2.0. Tu trabajo es tomar el Calendario de Contenido (Módulo 3) de un plan de marketing
ya aprobado y producir el contenido REAL, listo para publicar, para cada una de sus piezas.

PRINCIPIOS:
- No describas la pieza, escríbela completa: el texto_completo debe ser el post/guion final, no un resumen.
- El prompt_imagen debe ser específico y usable directamente en un generador de imágenes (estilo visual,
  encuadre, colores, elementos), coherente con el rubro y la ciudad del cliente.
- Los hashtags deben ser relevantes al rubro, la ciudad y el formato — mezcla genéricos y de nicho.
- mejor_horario debe ser una recomendación concreta (día + hora), no una franja vaga.
- Respeta el objetivo, formato y CTA ya definidos en cada pieza del calendario original.
- Todo el contenido debe estar en español neutro LATAM.

{_CONTENT_JSON_SCHEMA}"""


class ContentAgent:
    NOMBRE = "ContentAgent"
    MODEL = _MODEL

    def run(
        self, req: MarketingGenerateRequest, calendario: List[ContentCalendarItem]
    ) -> Tuple[List[ContentPiece], int]:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'anthropic>=0.40.0'"
            ) from exc

        client = _anthropic_client(_anthropic)
        user_msg = self._build_user_message(req, calendario)
        messages = [{"role": "user", "content": user_msg}]

        text, tokens, stop_reason = self._invoke(client, messages)
        parsed = self._parse_json(text)
        piezas = parsed.get("piezas") if parsed else None

        if not piezas or len(piezas) != len(calendario):
            hint = (
                "la respuesta se truncó por max_tokens — sube _MAX_TOKENS"
                if stop_reason == "max_tokens"
                else "la respuesta no es JSON válido o no tiene una pieza por cada día del calendario"
            )
            raise RuntimeError(
                f"ContentAgent: no se pudo generar el contenido completo ({hint}). "
                f"stop_reason={stop_reason}, respuesta cruda (primeros 500 chars): {text[:500]!r}"
            )

        pieces = [ContentPiece(**item) for item in piezas]
        return pieces, tokens

    def _invoke(self, client: Any, messages: List[Dict[str, Any]]) -> Tuple[str, int, str]:
        with client.messages.stream(
            model=self.MODEL,
            max_tokens=_MAX_TOKENS,
            system=_CONTENT_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens, response.stop_reason

    @staticmethod
    def _build_user_message(req: MarketingGenerateRequest, calendario: List[ContentCalendarItem]) -> str:
        calendario_text = "\n".join(
            f"- Día {item.dia} | {item.formato} | Objetivo: {item.objetivo} | "
            f"Guion original: {item.guion} | CTA: {item.cta}"
            for item in calendario
        )
        return (
            f"DATOS DEL CLIENTE:\n"
            f"Sitio: {req.site_url}\n"
            f"Rubro: {req.business_type}\n"
            f"Ciudad: {req.city}\n\n"
            f"CALENDARIO DE CONTENIDO A EJECUTAR ({len(calendario)} piezas):\n"
            f"{calendario_text}\n\n"
            "Genera el contenido real de cada pieza siguiendo exactamente el esquema indicado, "
            "manteniendo el mismo orden y el mismo número de piezas."
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean.strip())
        try:
            return json.loads(clean)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


_WHATSAPP_JSON_SCHEMA = """\
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin bloques markdown):
{
  "mensajes": [
    {
      "categoria": "Bienvenida",
      "mensaje_texto": "texto final del mensaje de WhatsApp, listo para copiar y enviar, en español neutro LATAM...",
      "variables_sugeridas": ["{nombre_cliente}", "{nombre_negocio}"],
      "mejor_momento_envio": "Disparador o momento concreto, ej. 'Inmediatamente tras la primera consulta'"
    },
    "... una entrada por cada categoría de estrategia_whatsapp recibida, mismo orden, mismo número de mensajes ..."
  ]
}"""

_WHATSAPP_SYSTEM_PROMPT = f"""Eres WhatsAppAgent, especialista en mensajería conversacional para PYMEs LATAM
dentro de WPRecover 2.0. Tu trabajo es tomar la Estrategia de WhatsApp (Módulo 5) de un plan de marketing
ya aprobado y producir el texto REAL de cada mensaje, listo para copiar y enviar — no se envía nada
automáticamente, el negocio copia el texto generado a su WhatsApp.

PRINCIPIOS:
- No describas la estrategia, escribe el mensaje completo: mensaje_texto debe ser el texto final, no un
  resumen de la táctica.
- Usa marcadores de variable entre llaves para los datos que cambian por cliente (nombre, producto, fecha) —
  nunca inventes un nombre o número real; lista esos mismos marcadores en variables_sugeridas.
- mejor_momento_envio debe ser un disparador o momento concreto, no una franja vaga.
- Respeta el orden y el número de categorías de estrategia_whatsapp ya definidas en el plan original.
- Todo el contenido debe estar en español neutro LATAM.

{_WHATSAPP_JSON_SCHEMA}"""


class WhatsAppAgent:
    NOMBRE = "WhatsAppAgent"
    MODEL = _MODEL

    def run(
        self, req: MarketingGenerateRequest, estrategia_whatsapp: List[str]
    ) -> Tuple[List[WhatsAppMessage], int]:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'anthropic>=0.40.0'"
            ) from exc

        client = _anthropic_client(_anthropic)
        user_msg = self._build_user_message(req, estrategia_whatsapp)
        messages = [{"role": "user", "content": user_msg}]

        text, tokens, stop_reason = self._invoke(client, messages)
        parsed = self._parse_json(text)
        mensajes = parsed.get("mensajes") if parsed else None

        if not mensajes or len(mensajes) != len(estrategia_whatsapp):
            hint = (
                "la respuesta se truncó por max_tokens — sube _MAX_TOKENS"
                if stop_reason == "max_tokens"
                else "la respuesta no es JSON válido o no tiene un mensaje por cada categoría de la estrategia"
            )
            raise RuntimeError(
                f"WhatsAppAgent: no se pudo generar los mensajes completos ({hint}). "
                f"stop_reason={stop_reason}, respuesta cruda (primeros 500 chars): {text[:500]!r}"
            )

        return [WhatsAppMessage(**item) for item in mensajes], tokens

    def _invoke(self, client: Any, messages: List[Dict[str, Any]]) -> Tuple[str, int, str]:
        with client.messages.stream(
            model=self.MODEL,
            max_tokens=_MAX_TOKENS,
            system=_WHATSAPP_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens, response.stop_reason

    @staticmethod
    def _build_user_message(req: MarketingGenerateRequest, estrategia_whatsapp: List[str]) -> str:
        estrategia_text = "\n".join(f"- {item}" for item in estrategia_whatsapp)
        return (
            f"DATOS DEL CLIENTE:\n"
            f"Sitio: {req.site_url}\n"
            f"Rubro: {req.business_type}\n"
            f"Ciudad: {req.city}\n\n"
            f"ESTRATEGIA DE WHATSAPP A EJECUTAR ({len(estrategia_whatsapp)} categorías):\n"
            f"{estrategia_text}\n\n"
            "Genera el mensaje real de cada categoría siguiendo exactamente el esquema indicado, "
            "manteniendo el mismo orden y el mismo número de mensajes."
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean.strip())
        try:
            return json.loads(clean)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


# ---------------------------------------------------------------------------
# ContentPieceStore
# ---------------------------------------------------------------------------

class ContentPieceStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        return CONTENT_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: ContentPiecesRecord) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO content_pieces (plan_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (record.plan_id, Json(json.loads(record.model_dump_json()))),
                )
            return

        cls._path(record.plan_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[ContentPiecesRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM content_pieces WHERE plan_id = %s", (plan_id,))
                row = cur.fetchone()
            return ContentPiecesRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return ContentPiecesRecord(**json.loads(path.read_text(encoding="utf-8")))


async def start_content_job(plan_id: str) -> ContentPiecesRecord:
    """Ejecuta el Módulo 3 (Calendario de Contenido) de un plan ya generado.

    Devuelve de inmediato: si ya hay contenido cacheado (DONE) o un job en
    curso (RUNNING) lo retorna tal cual; si no, deja un placeholder RUNNING
    guardado y lanza la llamada a Claude en background. El llamador debe
    seguir consultando el resultado vía ContentPieceStore.load(plan_id)
    (ver GET /marketing/{plan_id}/content) hasta que el status sea DONE/FAILED.

    Esto evita bloquear la respuesta HTTP durante los minutos que tarda
    Claude en generar las piezas, lo que en Render terminaba en un 502
    (el proxy corta la conexión mucho antes de que el cliente Anthropic
    llegue a su propio timeout).
    """
    cached = ContentPieceStore.load(plan_id)
    if cached and cached.status in (ContentJobStatus.DONE, ContentJobStatus.RUNNING):
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    placeholder = ContentPiecesRecord(
        plan_id=plan_id,
        pieces=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        status=ContentJobStatus.RUNNING,
    )
    ContentPieceStore.save(placeholder)
    asyncio.create_task(_run_content_job(plan_id, plan_record))
    return placeholder


async def _run_content_job(plan_id: str, plan_record: MarketingPlanRecord) -> None:
    agent = ContentAgent()
    try:
        pieces, _tokens = await asyncio.to_thread(
            agent.run, plan_record.request, plan_record.plan.calendario_contenido
        )
        record = ContentPiecesRecord(
            plan_id=plan_id,
            pieces=pieces,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.DONE,
        )
    except Exception as exc:
        record = ContentPiecesRecord(
            plan_id=plan_id,
            pieces=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.FAILED,
            error=str(exc),
        )
    ContentPieceStore.save(record)


# ---------------------------------------------------------------------------
# MarketingActionTicketsStore — Módulo 9 ejecutado: Top 10 Acciones -> tickets
# ---------------------------------------------------------------------------

class MarketingActionTicketsStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        ACTIONS_DIR.mkdir(parents=True, exist_ok=True)
        return ACTIONS_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: MarketingActionTicketsRecord) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO action_tickets (plan_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (record.plan_id, Json(json.loads(record.model_dump_json()))),
                )
            return

        cls._path(record.plan_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[MarketingActionTicketsRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM action_tickets WHERE plan_id = %s", (plan_id,))
                row = cur.fetchone()
            return MarketingActionTicketsRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return MarketingActionTicketsRecord(**json.loads(path.read_text(encoding="utf-8")))


# Top 10 Acciones ya viene ordenada por impacto ("acción 1 de mayor impacto en 7
# días..."), así que la prioridad se deriva de la posición sin necesidad de una
# llamada adicional a Claude.
_ACTION_PRIORIDAD_BY_POSITION = (
    [Prioridad.Alta] * 3 + [Prioridad.Media] * 4 + [Prioridad.Baja] * 3
)
_ACTION_ESTIMACION_BY_PRIORIDAD = {
    Prioridad.Alta: 90,
    Prioridad.Media: 60,
    Prioridad.Baja: 30,
}


def _build_action_tickets(plan_id: str, plan_record: MarketingPlanRecord) -> List[Ticket]:
    acciones = plan_record.plan.top_10_acciones
    project_id = plan_record.request.project_id
    tickets: List[Ticket] = []
    for i, accion in enumerate(acciones):
        prioridad = (
            _ACTION_PRIORIDAD_BY_POSITION[i]
            if i < len(_ACTION_PRIORIDAD_BY_POSITION)
            else Prioridad.Baja
        )
        tickets.append(
            Ticket(
                id=f"TKT-MKT-{plan_id[-6:]}-{i + 1:02d}",
                categoria=Categoria.Marketing,
                titulo=accion,
                prioridad=prioridad,
                impacto=f"Acción #{i + 1} de 10 del plan de marketing (Módulo 9), prioridad {prioridad.value} según orden de impacto.",
                agente="MarketingAgent",
                estimacion=_ACTION_ESTIMACION_BY_PRIORIDAD[prioridad],
                dependencias=[],
                project_id=project_id,
            )
        )
    return tickets


async def start_actions_job(plan_id: str) -> MarketingActionTicketsRecord:
    """Convierte el Módulo 9 (Top 10 Acciones Inmediatas) de un plan ya generado
    en tickets reales (categoría Marketing), siguiendo el mismo patrón
    job-en-background + polling que start_content_job.

    Idempotente: si ya hay tickets generados (DONE) o un job en curso
    (RUNNING) para este plan_id, los devuelve sin volver a crearlos.
    """
    cached = MarketingActionTicketsStore.load(plan_id)
    if cached and cached.status in (ContentJobStatus.DONE, ContentJobStatus.RUNNING):
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    placeholder = MarketingActionTicketsRecord(
        plan_id=plan_id,
        tickets=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        status=ContentJobStatus.RUNNING,
    )
    MarketingActionTicketsStore.save(placeholder)
    asyncio.create_task(_run_actions_job(plan_id, plan_record))
    return placeholder


async def _run_actions_job(plan_id: str, plan_record: MarketingPlanRecord) -> None:
    try:
        tickets = await asyncio.to_thread(_build_action_tickets, plan_id, plan_record)
        record = MarketingActionTicketsRecord(
            plan_id=plan_id,
            tickets=tickets,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.DONE,
        )
    except Exception as exc:
        record = MarketingActionTicketsRecord(
            plan_id=plan_id,
            tickets=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.FAILED,
            error=str(exc),
        )
    MarketingActionTicketsStore.save(record)


# ---------------------------------------------------------------------------
# Plan90DiasTicketsStore — Módulo 6 ejecutado: Plan 90 días -> tickets
# ---------------------------------------------------------------------------

class Plan90DiasTicketsStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        PLAN90_DIR.mkdir(parents=True, exist_ok=True)
        return PLAN90_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: Plan90DiasTicketsRecord) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO plan90_tickets (plan_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (record.plan_id, Json(json.loads(record.model_dump_json()))),
                )
            return

        cls._path(record.plan_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[Plan90DiasTicketsRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM plan90_tickets WHERE plan_id = %s", (plan_id,))
                row = cur.fetchone()
            return Plan90DiasTicketsRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return Plan90DiasTicketsRecord(**json.loads(path.read_text(encoding="utf-8")))


# El Plan de Ejecución (Módulo 6) ya viene organizado por fases temporales, así
# que la prioridad y la estimación se derivan de la fase sin una llamada
# adicional a Claude. mes_3 comparte prioridad Baja con mes_2 (no se añade una
# cuarta categoría a Prioridad), pero su estimación es menor por ser la fase más
# alejada en el tiempo.
_FASE_PLAN90: List[Tuple[str, str]] = [
    ("semana_1_2", "Semana 1-2"),
    ("semana_3_4", "Semana 3-4"),
    ("mes_2", "Mes 2"),
    ("mes_3", "Mes 3"),
]
_FASE_PRIORIDAD = {
    "semana_1_2": Prioridad.Alta,
    "semana_3_4": Prioridad.Media,
    "mes_2": Prioridad.Baja,
    "mes_3": Prioridad.Baja,
}
_FASE_ESTIMACION = {
    "semana_1_2": 90,
    "semana_3_4": 60,
    "mes_2": 30,
    "mes_3": 20,
}
# Rango de semanas (1-12) que cubre cada fase, usado como fallback cuando la
# acción no trae un "Día N"/"Semana N" explícito en su texto.
_FASE_SEMANAS = {
    "semana_1_2": (1, 2),
    "semana_3_4": (3, 4),
    "mes_2": (5, 8),
    "mes_3": (9, 12),
}

_SEMANA_RE = re.compile(r"semana\s+(\d{1,2})", re.IGNORECASE)
_DIA_RE = re.compile(r"d[íi]a\s+(\d{1,3})", re.IGNORECASE)


def _derive_semana(fase_key: str, titulo: str, pos: int, count: int) -> int:
    """Deriva la semana (1-12) de una acción de forma determinista.

    1) Si el texto trae "Semana N" explícito, usa N.
    2) Si trae "Día N", convierte a semana con ceil(N/7).
    3) Si no, reparte las acciones de la fase uniformemente en su rango de
       semanas según su posición.
    El resultado siempre se acota a [1, 12].
    """
    m = _SEMANA_RE.search(titulo)
    if m:
        return min(max(int(m.group(1)), 1), 12)

    m = _DIA_RE.search(titulo)
    if m:
        semana = (int(m.group(1)) + 6) // 7  # ceil(dia / 7)
        return min(max(semana, 1), 12)

    lo, hi = _FASE_SEMANAS[fase_key]
    span = hi - lo + 1
    if count <= 1:
        return lo
    return lo + min((pos * span) // count, span - 1)


# Clasificación heurística (determinista) de cada acción hacia uno de los
# módulos del plan de marketing. Se evalúa en orden; la primera coincidencia
# gana. Si ninguna coincide, cae en el propio Módulo 6 (la acción es puramente
# de coordinación/ejecución del plan). No usa IA: es una aproximación por
# palabras clave, no una clasificación semántica.
_MODULO_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("Módulo 5: Estrategia WhatsApp", ("whatsapp", "joinchat")),
    ("Módulo 3: Calendario de contenido", ("calendario", "contenido", "reel", "blog", "instagram", "publicar", "newsletter", "post")),
    ("Módulo 4: Embudo de ventas", ("klaviyo", "email", "carrito abandonado", "embudo", "checkout", "reactivación", "upsell", "cross-sell", "referidos")),
    ("Módulo 2: Estrategia de adquisición", ("google ads", "meta ads", "shopping", "pauta", "campaña", "remarketing", "retargeting", "lookalike", "pixel", "píxel", "influencer", "merchant center")),
    ("Módulo 8: Métricas clave", ("métrica", "metrica", "reporte", "roas", "cpl", "analytics", "search console", "kpi", "conversión del checkout", "posicionamiento")),
    ("Módulo 7: IA y automatización", ("automatización", "chatbot", "tidio", "chat en vivo")),
    ("Módulo 1: Diagnóstico inicial", ("pagespeed", "seguridad", "headers", "ssl", "auditoría", "diagnóstico")),
]
_MODULO_DEFAULT = "Módulo 6: Plan de Ejecución 90 días"


def _derive_modulo_origen(titulo: str) -> str:
    t = titulo.lower()
    for modulo, keywords in _MODULO_KEYWORDS:
        if any(kw in t for kw in keywords):
            return modulo
    return _MODULO_DEFAULT


def _build_plan90_tickets(plan_id: str, plan_record: MarketingPlanRecord) -> List[Plan90Ticket]:
    plan90 = plan_record.plan.plan_ejecucion_90_dias
    project_id = plan_record.request.project_id
    tickets: List[Plan90Ticket] = []
    idx = 0
    for fase_key, fase_label in _FASE_PLAN90:
        prioridad = _FASE_PRIORIDAD[fase_key]
        estimacion = _FASE_ESTIMACION[fase_key]
        acciones = getattr(plan90, fase_key)
        for pos, accion in enumerate(acciones):
            idx += 1
            semana = _derive_semana(fase_key, accion, pos, len(acciones))
            tickets.append(
                Plan90Ticket(
                    id=f"TKT-90D-{plan_id[-6:]}-{idx:02d}",
                    categoria=Categoria.Marketing,
                    titulo=accion,
                    prioridad=prioridad,
                    impacto=f"Acción de la fase {fase_label} del Plan de Ejecución 90 días (Módulo 6), prioridad {prioridad.value}.",
                    agente="MarketingAgent",
                    estimacion=estimacion,
                    dependencias=[],
                    project_id=project_id,
                    semana=semana,
                    modulo_origen=_derive_modulo_origen(accion),
                    # Invariante no-auto-approve: TODOS nacen pendientes de revisión.
                    estado_aprobacion=EstadoAprobacion.pendiente_revision,
                )
            )
    return tickets


async def start_plan90_job(plan_id: str) -> Plan90DiasTicketsRecord:
    """Convierte el Módulo 6 (Plan de Ejecución 90 días) de un plan ya generado
    en tickets reales (categoría Marketing), siguiendo el mismo patrón
    job-en-background + polling que start_actions_job.

    Idempotente: si ya hay tickets generados (DONE) o un job en curso
    (RUNNING) para este plan_id, los devuelve sin volver a crearlos.
    """
    cached = Plan90DiasTicketsStore.load(plan_id)
    if cached and cached.status in (ContentJobStatus.DONE, ContentJobStatus.RUNNING):
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    placeholder = Plan90DiasTicketsRecord(
        plan_id=plan_id,
        tickets=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        status=ContentJobStatus.RUNNING,
    )
    Plan90DiasTicketsStore.save(placeholder)
    asyncio.create_task(_run_plan90_job(plan_id, plan_record))
    return placeholder


async def _run_plan90_job(plan_id: str, plan_record: MarketingPlanRecord) -> None:
    try:
        tickets = await asyncio.to_thread(_build_plan90_tickets, plan_id, plan_record)
        record = Plan90DiasTicketsRecord(
            plan_id=plan_id,
            tickets=tickets,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.DONE,
        )
    except Exception as exc:
        record = Plan90DiasTicketsRecord(
            plan_id=plan_id,
            tickets=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.FAILED,
            error=str(exc),
        )
    Plan90DiasTicketsStore.save(record)


# ---------------------------------------------------------------------------
# Capa de aprobación manual de los tickets del Plan 90 días (Módulo 6)
#
# La persistencia es por-plan (un registro Plan90DiasTicketsRecord con la lista
# embebida), así que aprobar/rechazar un ticket significa cargar el registro,
# mutar el ticket concreto y volver a guardar el registro completo. Por eso
# estos endpoints reciben plan_id además de ticket_id.
#
# NOTA DE SCOPE: aquí NO se ejecuta ningún ticket. Las transiciones a
# en_ejecucion/completado son de la sesión POSTERIOR y no existen todavía.
# ---------------------------------------------------------------------------

class Plan90TicketNotFound(ValueError):
    """El plan no tiene tickets generados, o el ticket_id no existe."""


class Plan90TicketTransitionError(Exception):
    """Transición de estado_aprobacion no permitida por el flujo."""


class Plan90TicketNotExecutable(Exception):
    """El ticket no pertenece al subset ejecutable vía WordPress (modulo_origen)."""


class Plan90ExecutionConfigError(Exception):
    """No se puede determinar contra qué sitio/con qué key ejecutar el ticket:
    falta project_id, el proyecto no existe, o no tiene site_url/wprepro_api_key.
    Fallo explícito — nunca se cae al WPREPRO_API_KEY global (ese fallback causó
    los 403 en clientes reales)."""


class Plan90ExecutionError(Exception):
    """El WPRepro Agent rechazó o falló la acción. El ticket vuelve a 'aprobado'
    con error_ejecucion registrado para poder reintentarse."""


# Único módulo cuyas acciones son ejecutables vía WordPress hoy: las técnicas que
# _derive_modulo_origen clasifica como diagnóstico (ssl/headers/pagespeed/...).
# El resto son acciones de marketing sin representación en el WPRepro Agent.
EXECUTABLE_MODULO = "Módulo 1: Diagnóstico inicial"


def _load_plan90_record_or_raise(plan_id: str) -> Plan90DiasTicketsRecord:
    record = Plan90DiasTicketsStore.load(plan_id)
    if not record:
        raise Plan90TicketNotFound(
            f"No hay tickets del Plan 90 días para el plan '{plan_id}'. "
            f"Genéralos primero con POST /marketing/{plan_id}/generate-tickets."
        )
    return record


def _find_plan90_ticket(record: Plan90DiasTicketsRecord, ticket_id: str) -> Plan90Ticket:
    for ticket in record.tickets:
        if ticket.id == ticket_id:
            return ticket
    raise Plan90TicketNotFound(
        f"Ticket '{ticket_id}' no encontrado en el plan '{record.plan_id}'."
    )


def list_plan90_tickets(
    plan_id: str,
    estado: Optional[EstadoAprobacion] = None,
    semana: Optional[int] = None,
) -> Plan90DiasTicketsRecord:
    """Devuelve el registro del plan con la lista de tickets filtrada por
    estado_aprobacion y/o semana (no muta el registro almacenado)."""
    record = _load_plan90_record_or_raise(plan_id)
    tickets = record.tickets
    if estado is not None:
        tickets = [t for t in tickets if t.estado_aprobacion == estado]
    if semana is not None:
        tickets = [t for t in tickets if t.semana == semana]
    return record.model_copy(update={"tickets": tickets})


def approve_plan90_ticket(
    plan_id: str, ticket_id: str, actor: Optional[str] = None
) -> Plan90Ticket:
    """Transición pendiente_revision -> aprobado. Acción HUMANA explícita:
    es el único punto del código que pone un ticket en 'aprobado'. `actor` es la
    identidad (auto-declarada) del operador, tomada del header X-Actor en la capa
    HTTP; queda registrada en el ticket para trazabilidad."""
    record = _load_plan90_record_or_raise(plan_id)
    ticket = _find_plan90_ticket(record, ticket_id)
    if ticket.estado_aprobacion != EstadoAprobacion.pendiente_revision:
        raise Plan90TicketTransitionError(
            f"Solo se puede aprobar un ticket en 'pendiente_revision'; "
            f"'{ticket_id}' está en '{ticket.estado_aprobacion.value}'."
        )
    ticket.estado_aprobacion = EstadoAprobacion.aprobado
    ticket.motivo_rechazo = None
    ticket.aprobado_por = actor
    Plan90DiasTicketsStore.save(record)
    return ticket


def reject_plan90_ticket(
    plan_id: str, ticket_id: str, motivo: Optional[str] = None, actor: Optional[str] = None
) -> Plan90Ticket:
    """Transición pendiente_revision -> rechazado, con motivo opcional. `actor`
    es la identidad (auto-declarada) del operador que rechaza, registrada para
    trazabilidad (ver approve_plan90_ticket)."""
    record = _load_plan90_record_or_raise(plan_id)
    ticket = _find_plan90_ticket(record, ticket_id)
    if ticket.estado_aprobacion != EstadoAprobacion.pendiente_revision:
        raise Plan90TicketTransitionError(
            f"Solo se puede rechazar un ticket en 'pendiente_revision'; "
            f"'{ticket_id}' está en '{ticket.estado_aprobacion.value}'."
        )
    ticket.estado_aprobacion = EstadoAprobacion.rechazado
    ticket.motivo_rechazo = motivo
    ticket.rechazado_por = actor
    Plan90DiasTicketsStore.save(record)
    return ticket


# ---------------------------------------------------------------------------
# Ejecución real de tickets aprobados (M6 Sesión 3)
#
# SCOPE: solo el subset EXECUTABLE_MODULO se ejecuta vía WordPress. La acción
# concreta que se corre es todavía un STUB verificable (wp plugin list, read-only):
# esta sesión construye la máquina de estados + auth + resolución de key por
# proyecto + auditoría; el mapeo real título->WP-CLI/snippet es de la Sesión 4.
# ---------------------------------------------------------------------------

# Acción placeholder read-only. WP-CLI dentro de la whitelist del plugin; no muta
# el sitio. Se reemplaza por el mapeo real por ticket en la Sesión 4.
_STUB_EXECUTE_COMMANDS = ["wp plugin list"]


class Plan90ExecutionLog:
    """Log append-only (espejo de fix_engine.FixLog) de cada intento de ejecución."""

    @staticmethod
    def _path(ticket_id: str) -> Path:
        _dir = Path(__file__).parent / "plan90_execution_log"
        _dir.mkdir(parents=True, exist_ok=True)
        return _dir / f"{ticket_id}.jsonl"

    @classmethod
    def append(cls, entry: Plan90ExecutionLogEntry) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO plan90_execution_log (ticket_id, data) VALUES (%s, %s)",
                    (entry.ticket_id, Json(json.loads(entry.model_dump_json()))),
                )
            return
        with cls._path(entry.ticket_id).open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")

    @classmethod
    def read(cls, ticket_id: str) -> List[Plan90ExecutionLogEntry]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM plan90_execution_log WHERE ticket_id = %s ORDER BY id ASC",
                    (ticket_id,),
                )
                rows = cur.fetchall()
            return [Plan90ExecutionLogEntry(**r[0]) for r in rows]
        path = cls._path(ticket_id)
        if not path.exists():
            return []
        return [
            Plan90ExecutionLogEntry(**json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _log_execution(plan_id: str, ticket_id: str, actor: str, outcome: str, detail: Optional[str] = None) -> None:
    Plan90ExecutionLog.append(
        Plan90ExecutionLogEntry(
            plan_id=plan_id,
            ticket_id=ticket_id,
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat(),
            outcome=outcome,
            detail=detail,
        )
    )


def _resolve_project_target(ticket: Plan90Ticket) -> Tuple[str, str]:
    """Devuelve (site_url, wprepro_api_key) del proyecto del ticket, o lanza
    Plan90ExecutionConfigError. NO usa resolve_api_key(): nunca cae al global."""
    if not ticket.project_id:
        raise Plan90ExecutionConfigError(
            f"El ticket '{ticket.id}' no tiene project_id — no se puede saber contra "
            f"qué sitio ejecutar. Regenera los tickets desde un plan con project_id."
        )
    project = ProjectStore.get(ticket.project_id)
    if not project:
        raise Plan90ExecutionConfigError(
            f"No existe el proyecto '{ticket.project_id}' del ticket '{ticket.id}'."
        )
    if not project.site_url:
        raise Plan90ExecutionConfigError(
            f"El proyecto '{ticket.project_id}' no tiene site_url configurado."
        )
    if not project.wprepro_api_key:
        raise Plan90ExecutionConfigError(
            f"El proyecto '{ticket.project_id}' no tiene wprepro_api_key propia. "
            f"Configúrala en el proyecto (no se usa la key global)."
        )
    return project.site_url, project.wprepro_api_key


def execute_plan90_ticket(plan_id: str, ticket_id: str, actor: str) -> Plan90Ticket:
    """Ejecuta un ticket APROBADO del subset técnico contra su sitio WordPress.

    Flujo de estados: aprobado -> en_ejecucion (persistido) -> completado (OK) /
    de vuelta a aprobado con error_ejecucion (falla). Cada intento queda en el
    log de auditoría. La key se resuelve por proyecto, sin fallback al global.
    """
    record = _load_plan90_record_or_raise(plan_id)
    ticket = _find_plan90_ticket(record, ticket_id)

    if ticket.estado_aprobacion != EstadoAprobacion.aprobado:
        raise Plan90TicketTransitionError(
            f"Solo se puede ejecutar un ticket en 'aprobado'; "
            f"'{ticket_id}' está en '{ticket.estado_aprobacion.value}'."
        )
    if ticket.modulo_origen != EXECUTABLE_MODULO:
        raise Plan90TicketNotExecutable(
            f"El ticket '{ticket_id}' ({ticket.modulo_origen}) no es ejecutable vía "
            f"WordPress. Solo '{EXECUTABLE_MODULO}' lo es."
        )

    # Resuelve el objetivo ANTES de mover el estado: si no hay sitio/key, el ticket
    # se queda en 'aprobado' y no se registra un intento fallido espurio.
    site_url, api_key = _resolve_project_target(ticket)

    # Persistir en_ejecucion antes de la llamada (visible para polling/otros lectores).
    ticket.estado_aprobacion = EstadoAprobacion.en_ejecucion
    ticket.ejecutado_por = actor
    ticket.ejecutado_at = datetime.now(timezone.utc).isoformat()
    ticket.error_ejecucion = None
    Plan90DiasTicketsStore.save(record)
    _log_execution(plan_id, ticket_id, actor, "started", detail=" ".join(_STUB_EXECUTE_COMMANDS))

    try:
        client = WPAgentClient(site_url, api_key)
        result = client.execute(_STUB_EXECUTE_COMMANDS)  # STUB: acción real en Sesión 4
    except Exception as exc:
        ticket.estado_aprobacion = EstadoAprobacion.aprobado
        ticket.error_ejecucion = str(exc)
        Plan90DiasTicketsStore.save(record)
        _log_execution(plan_id, ticket_id, actor, "failed", detail=str(exc))
        raise Plan90ExecutionError(str(exc)) from exc

    ticket.estado_aprobacion = EstadoAprobacion.completado
    ticket.error_ejecucion = None
    Plan90DiasTicketsStore.save(record)
    _log_execution(plan_id, ticket_id, actor, "completed", detail=json.dumps(result)[:500])
    return ticket


# ---------------------------------------------------------------------------
# WhatsAppMessageStore — Módulo 5 ejecutado: mensajes reales por plan
# ---------------------------------------------------------------------------

class WhatsAppMessageStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
        return MESSAGES_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: WhatsAppMessagesRecord) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO whatsapp_messages (plan_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (record.plan_id, Json(json.loads(record.model_dump_json()))),
                )
            return

        cls._path(record.plan_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[WhatsAppMessagesRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM whatsapp_messages WHERE plan_id = %s", (plan_id,))
                row = cur.fetchone()
            return WhatsAppMessagesRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return WhatsAppMessagesRecord(**json.loads(path.read_text(encoding="utf-8")))


async def start_whatsapp_job(plan_id: str) -> WhatsAppMessagesRecord:
    """Ejecuta el Módulo 5 (Estrategia WhatsApp) de un plan ya generado.

    Mismo patrón job-en-background + polling que start_content_job: devuelve
    de inmediato (cacheado si DONE/RUNNING, o un placeholder RUNNING) y lanza
    la llamada a Claude en background. El llamador debe seguir consultando
    WhatsAppMessageStore.load(plan_id) (ver GET /marketing/{plan_id}/whatsapp)
    hasta que el status sea DONE/FAILED.

    Solo genera el texto de cada mensaje — no envía nada vía WhatsApp.
    """
    cached = WhatsAppMessageStore.load(plan_id)
    if cached and cached.status in (ContentJobStatus.DONE, ContentJobStatus.RUNNING):
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    placeholder = WhatsAppMessagesRecord(
        plan_id=plan_id,
        mensajes=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        status=ContentJobStatus.RUNNING,
    )
    WhatsAppMessageStore.save(placeholder)
    asyncio.create_task(_run_whatsapp_job(plan_id, plan_record))
    return placeholder


async def _run_whatsapp_job(plan_id: str, plan_record: MarketingPlanRecord) -> None:
    agent = WhatsAppAgent()
    try:
        mensajes, _tokens = await asyncio.to_thread(
            agent.run, plan_record.request, plan_record.plan.estrategia_whatsapp
        )
        record = WhatsAppMessagesRecord(
            plan_id=plan_id,
            mensajes=mensajes,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.DONE,
        )
    except Exception as exc:
        record = WhatsAppMessagesRecord(
            plan_id=plan_id,
            mensajes=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.FAILED,
            error=str(exc),
        )
    WhatsAppMessageStore.save(record)


# ---------------------------------------------------------------------------
# IaAutomatizacionAgent — Módulo 7: estructura cada string de ia_automatizacion
# (prosa) en una ficha ejecutable {herramienta, caso_uso, pasos, costo,
# prioridad, estimacion} vía Claude. Mismo mecanismo que WhatsAppAgent.
# ---------------------------------------------------------------------------

_IA_JSON_SCHEMA = """\
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin bloques markdown):
{
  "items": [
    {
      "herramienta": "Klaviyo Predictive Analytics",
      "caso_uso": "Segmentación predictiva para email marketing",
      "pasos": ["Ir a Segments > Predictive analytics > High purchase likelihood", "..."],
      "costo": "USD $20/mes",
      "prioridad": "Alta",
      "estimacion": 45,
      "mejor_momento": "Tras acumular ≥100 pedidos para que el modelo predictivo tenga datos suficientes"
    },
    "... una entrada por cada recomendación de ia_automatizacion recibida, mismo orden, mismo número ..."
  ]
}"""

_IA_SYSTEM_PROMPT = f"""Eres IaAutomatizacionAgent, especialista en automatización con IA para PYMEs LATAM
dentro de WPRecover 2.0. Tu trabajo es tomar las recomendaciones de IA y Automatización (Módulo 7) de un
plan de marketing ya aprobado y convertir cada una en una ficha ejecutable y estructurada — el negocio la
usa como checklist de implementación.

PRINCIPIOS:
- Cada string de entrada es una recomendación en prosa que mezcla herramienta, caso de uso, pasos de
  configuración y costo. Tu trabajo es SEPARAR esos componentes en campos limpios, sin inventar datos que
  no estén en el texto original.
- herramienta: el nombre concreto de la herramienta/IA (ej. "Klaviyo Predictive Analytics").
- caso_uso: una sola línea de para qué sirve, orientada al negocio.
- pasos: lista de pasos accionables de configuración, en orden, extraídos o inferidos razonablemente del
  texto. Si el texto trae una ruta de dashboard o un prompt, consérvalo literal.
- costo: el costo tal como aparece en el texto, conservando la moneda ("USD $20/mes", "CLP $7.000/mes",
  "gratuito"). Si el texto no menciona costo, usa "no especificado".
- prioridad: INFIÉRELA con criterio de impacto vs. esfuerzo para una PYME: Alta = alto impacto y setup
  rápido/barato (quick win); Media = impacto medio o costo recurrente relevante; Baja = nice-to-have o
  costo alto. Usa solo Alta, Media o Baja (nunca Critica).
- estimacion: minutos realistas de setup inicial (no de operación continua).
- mejor_momento: una sola línea que indique CUÁNDO conviene implementar o activar esta automatización,
  inferida desde el caso de uso y el rubro del negocio. Orientada a la decisión del dueño de la PYME
  (ej. "Antes de campañas de temporada alta (CyberDay, Navidad)", "Tras acumular ≥100 pedidos/mes",
  "Desde el día 1, es un quick win sin requisitos previos", "Cuando el volumen de consultas en WhatsApp
  supere lo que el equipo puede responder a mano"). No inventes cifras del negocio que no puedas inferir
  razonablemente; si no hay un disparador claro, indica que puede implementarse de inmediato.
- Respeta el orden y el número EXACTO de recomendaciones recibidas: una ficha por cada una.
- Todo el contenido en español neutro LATAM.

{_IA_JSON_SCHEMA}"""


class IaAutomatizacionAgent:
    NOMBRE = "IaAutomatizacionAgent"
    MODEL = _MODEL

    def run(
        self, req: MarketingGenerateRequest, ia_automatizacion: List[str]
    ) -> Tuple[List[Dict[str, Any]], int]:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'anthropic>=0.40.0'"
            ) from exc

        client = _anthropic_client(_anthropic)
        user_msg = self._build_user_message(req, ia_automatizacion)
        messages = [{"role": "user", "content": user_msg}]

        text, tokens, stop_reason = self._invoke(client, messages)
        parsed = self._parse_json(text)
        items = parsed.get("items") if parsed else None

        if not items or len(items) != len(ia_automatizacion):
            hint = (
                "la respuesta se truncó por max_tokens — sube _MAX_TOKENS"
                if stop_reason == "max_tokens"
                else "la respuesta no es JSON válido o no tiene una ficha por cada recomendación recibida"
            )
            raise RuntimeError(
                f"IaAutomatizacionAgent: no se pudieron estructurar las fichas ({hint}). "
                f"stop_reason={stop_reason}, respuesta cruda (primeros 500 chars): {text[:500]!r}"
            )

        return items, tokens

    def _invoke(self, client: Any, messages: List[Dict[str, Any]]) -> Tuple[str, int, str]:
        with client.messages.stream(
            model=self.MODEL,
            max_tokens=_MAX_TOKENS,
            system=_IA_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens, response.stop_reason

    @staticmethod
    def _build_user_message(req: MarketingGenerateRequest, ia_automatizacion: List[str]) -> str:
        recomendaciones_text = "\n".join(f"- {item}" for item in ia_automatizacion)
        return (
            f"DATOS DEL CLIENTE:\n"
            f"Sitio: {req.site_url}\n"
            f"Rubro: {req.business_type}\n"
            f"Ciudad: {req.city}\n\n"
            f"RECOMENDACIONES DE IA Y AUTOMATIZACIÓN A ESTRUCTURAR ({len(ia_automatizacion)} recomendaciones):\n"
            f"{recomendaciones_text}\n\n"
            "Convierte cada recomendación en una ficha ejecutable siguiendo exactamente el esquema indicado, "
            "manteniendo el mismo orden y el mismo número de fichas."
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean.strip())
        try:
            return json.loads(clean)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


# ---------------------------------------------------------------------------
# IaAutomatizacionStore — Módulo 7 ejecutado: fichas IA por plan
# ---------------------------------------------------------------------------

class IaAutomatizacionStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        IA_DIR.mkdir(parents=True, exist_ok=True)
        return IA_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: IaAutomatizacionRecord) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ia_automatizacion (plan_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (record.plan_id, Json(json.loads(record.model_dump_json()))),
                )
            return

        cls._path(record.plan_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[IaAutomatizacionRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM ia_automatizacion WHERE plan_id = %s", (plan_id,))
                row = cur.fetchone()
            return IaAutomatizacionRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return IaAutomatizacionRecord(**json.loads(path.read_text(encoding="utf-8")))


def _build_ia_items(
    plan_id: str, project_id: Optional[str], raw_items: List[Dict[str, Any]]
) -> List[IaAutomatizacionItem]:
    """Completa las fichas que devuelve Claude (7 campos de contenido) con los
    campos fijos/generados en Python: id, categoria, agente, estado, project_id."""
    items: List[IaAutomatizacionItem] = []
    for idx, raw in enumerate(raw_items, 1):
        items.append(
            IaAutomatizacionItem(
                id=f"IA-{plan_id[-6:]}-{idx:02d}",
                herramienta=raw.get("herramienta", ""),
                caso_uso=raw.get("caso_uso", ""),
                pasos=raw.get("pasos") or [],
                costo=raw.get("costo") or "no especificado",
                prioridad=raw.get("prioridad", Prioridad.Media),
                estimacion=int(raw.get("estimacion", 30)),
                mejor_momento=raw.get("mejor_momento", ""),
                project_id=project_id,
            )
        )
    return items


async def start_iaautomatizacion_job(plan_id: str) -> IaAutomatizacionRecord:
    """Ejecuta el Módulo 7 (IA y Automatización) de un plan ya generado: convierte
    cada recomendación en prosa de ia_automatizacion en una ficha ejecutable vía
    IaAutomatizacionAgent. Mismo patrón job-en-background + polling que
    start_whatsapp_job. Idempotente: si ya hay fichas (DONE) o un job en curso
    (RUNNING) para este plan_id, los devuelve sin volver a llamar a Claude.
    """
    cached = IaAutomatizacionStore.load(plan_id)
    if cached and cached.status in (ContentJobStatus.DONE, ContentJobStatus.RUNNING):
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    placeholder = IaAutomatizacionRecord(
        plan_id=plan_id,
        items=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        status=ContentJobStatus.RUNNING,
    )
    IaAutomatizacionStore.save(placeholder)
    asyncio.create_task(_run_iaautomatizacion_job(plan_id, plan_record))
    return placeholder


async def _run_iaautomatizacion_job(plan_id: str, plan_record: MarketingPlanRecord) -> None:
    agent = IaAutomatizacionAgent()
    try:
        raw_items, _tokens = await asyncio.to_thread(
            agent.run, plan_record.request, plan_record.plan.ia_automatizacion
        )
        items = _build_ia_items(plan_id, plan_record.request.project_id, raw_items)
        record = IaAutomatizacionRecord(
            plan_id=plan_id,
            items=items,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.DONE,
        )
    except Exception as exc:
        record = IaAutomatizacionRecord(
            plan_id=plan_id,
            items=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.FAILED,
            error=str(exc),
        )
    IaAutomatizacionStore.save(record)


# ---------------------------------------------------------------------------
# MetricasClaveAgent — Módulo 8: estructura cada string de metricas_clave
# (prosa) en una ficha de métrica {nombre, formula, benchmark, objetivo,
# donde_medir, frecuencia_revision, mejor_momento} vía Claude. Mismo mecanismo
# que IaAutomatizacionAgent.
# ---------------------------------------------------------------------------

_METRICA_JSON_SCHEMA = """\
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin bloques markdown):
{
  "items": [
    {
      "nombre": "ROAS (Retorno sobre Inversión en Publicidad)",
      "formula": "Ingresos atribuidos a la campaña / Gasto publicitario de esa campaña",
      "benchmark": "Mínimo aceptable 3x",
      "objetivo": "Alcanzar 5x a mes 3",
      "donde_medir": ["Google Ads (conversiones e-commerce con GA4)", "Meta Ads Manager (ROAS de conversión en sitio web)"],
      "frecuencia_revision": "Semanal",
      "mejor_momento": "Desde la primera campaña pagada activa; clave durante temporada alta"
    },
    "... una entrada por cada métrica de metricas_clave recibida, mismo orden, mismo número ..."
  ]
}"""

_METRICA_SYSTEM_PROMPT = f"""Eres MetricasClaveAgent, especialista en analítica de marketing para PYMEs LATAM
dentro de WPRecover 2.0. Tu trabajo es tomar las Métricas Clave (Módulo 8) de un plan de marketing ya
aprobado y convertir cada una en una ficha estructurada — el negocio la usa como tablero de seguimiento.

PRINCIPIOS:
- Cada string de entrada es una métrica en prosa que mezcla nombre, definición/fórmula, benchmark del
  rubro, objetivo del negocio, dónde medirla y cada cuánto revisarla. Tu trabajo es SEPARAR esos
  componentes en campos limpios, sin inventar datos que no estén en el texto original.
- nombre: el nombre de la métrica con su sigla si la tiene (ej. "ROAS (Retorno sobre Inversión en Publicidad)").
- formula: cómo se calcula la métrica, en una línea. Si el texto trae un ejemplo numérico, puedes resumirlo
  pero prioriza la fórmula. Si no hay fórmula explícita, describe brevemente qué mide.
- benchmark: el rango/valor de referencia del rubro tal como aparece ("1-3%", "mínimo 3x", "5-15%"). Si el
  texto no menciona benchmark, usa "no especificado".
- objetivo: la meta concreta del negocio para esta métrica ("superar 2.5% a mes 3", "5x a mes 3",
  "+15% mes 1 a mes 3"). Si no hay objetivo explícito, usa "no especificado".
- donde_medir: lista de las herramientas/paneles donde se mide, extraídas del texto (ej. ["Google Ads",
  "GA4", "WooCommerce > Informes"]). Una entrada por herramienta.
- frecuencia_revision: cada cuánto revisar la métrica tal como aparece ("Semanal", "Quincenal", "Mensual").
  Respeta el texto; si no se menciona, infiere con criterio (métricas de pauta → semanal; de catálogo/SEO →
  mensual) y deja el valor en español capitalizado.
- mejor_momento: una sola línea que indique CUÁNDO esta métrica se vuelve relevante o desde cuándo conviene
  empezar a medirla, inferida desde el caso de uso (ej. "Desde la primera campaña pagada activa",
  "Tras acumular ≥100 pedidos para que el dato sea representativo", "Desde el día 1, es una métrica base").
  No inventes cifras que no puedas inferir razonablemente.
- Respeta el orden y el número EXACTO de métricas recibidas: una ficha por cada una.
- Todo el contenido en español neutro LATAM.

{_METRICA_JSON_SCHEMA}"""


class MetricasClaveAgent:
    NOMBRE = "MetricasClaveAgent"
    MODEL = _MODEL

    def run(
        self, req: MarketingGenerateRequest, metricas_clave: List[str]
    ) -> Tuple[List[Dict[str, Any]], int]:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'anthropic>=0.40.0'"
            ) from exc

        client = _anthropic_client(_anthropic)
        user_msg = self._build_user_message(req, metricas_clave)
        messages = [{"role": "user", "content": user_msg}]

        text, tokens, stop_reason = self._invoke(client, messages)
        parsed = self._parse_json(text)
        items = parsed.get("items") if parsed else None

        if not items or len(items) != len(metricas_clave):
            hint = (
                "la respuesta se truncó por max_tokens — sube _MAX_TOKENS"
                if stop_reason == "max_tokens"
                else "la respuesta no es JSON válido o no tiene una ficha por cada métrica recibida"
            )
            raise RuntimeError(
                f"MetricasClaveAgent: no se pudieron estructurar las métricas ({hint}). "
                f"stop_reason={stop_reason}, respuesta cruda (primeros 500 chars): {text[:500]!r}"
            )

        return items, tokens

    def _invoke(self, client: Any, messages: List[Dict[str, Any]]) -> Tuple[str, int, str]:
        with client.messages.stream(
            model=self.MODEL,
            max_tokens=_MAX_TOKENS,
            system=_METRICA_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens, response.stop_reason

    @staticmethod
    def _build_user_message(req: MarketingGenerateRequest, metricas_clave: List[str]) -> str:
        metricas_text = "\n".join(f"- {item}" for item in metricas_clave)
        return (
            f"DATOS DEL CLIENTE:\n"
            f"Sitio: {req.site_url}\n"
            f"Rubro: {req.business_type}\n"
            f"Ciudad: {req.city}\n\n"
            f"MÉTRICAS CLAVE A ESTRUCTURAR ({len(metricas_clave)} métricas):\n"
            f"{metricas_text}\n\n"
            "Convierte cada métrica en una ficha estructurada siguiendo exactamente el esquema indicado, "
            "manteniendo el mismo orden y el mismo número de fichas."
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean.strip())
        try:
            return json.loads(clean)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


# ---------------------------------------------------------------------------
# MetricasClaveStore — Módulo 8 ejecutado: métricas estructuradas por plan
# ---------------------------------------------------------------------------

class MetricasClaveStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        METRICAS_DIR.mkdir(parents=True, exist_ok=True)
        return METRICAS_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: MetricasClaveRecord) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO metricas_clave (plan_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (plan_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (record.plan_id, Json(json.loads(record.model_dump_json()))),
                )
            return

        cls._path(record.plan_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[MetricasClaveRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM metricas_clave WHERE plan_id = %s", (plan_id,))
                row = cur.fetchone()
            return MetricasClaveRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return MetricasClaveRecord(**json.loads(path.read_text(encoding="utf-8")))


def _build_metrica_items(
    plan_id: str, project_id: Optional[str], raw_items: List[Dict[str, Any]]
) -> List[MetricaItem]:
    """Completa las fichas que devuelve Claude (7 campos de contenido) con los
    campos fijos/generados en Python: id, categoria, agente, estado, project_id."""
    items: List[MetricaItem] = []
    for idx, raw in enumerate(raw_items, 1):
        items.append(
            MetricaItem(
                id=f"MET-{plan_id[-6:]}-{idx:02d}",
                nombre=raw.get("nombre", ""),
                formula=raw.get("formula", ""),
                benchmark=raw.get("benchmark") or "no especificado",
                objetivo=raw.get("objetivo") or "no especificado",
                donde_medir=raw.get("donde_medir") or [],
                frecuencia_revision=raw.get("frecuencia_revision", ""),
                mejor_momento=raw.get("mejor_momento", ""),
                project_id=project_id,
            )
        )
    return items


async def start_metricasclave_job(plan_id: str) -> MetricasClaveRecord:
    """Ejecuta el Módulo 8 (Métricas Clave) de un plan ya generado: convierte cada
    métrica en prosa de metricas_clave en una ficha estructurada vía
    MetricasClaveAgent. Mismo patrón job-en-background + polling que
    start_iaautomatizacion_job. Idempotente: si ya hay fichas (DONE) o un job en
    curso (RUNNING) para este plan_id, los devuelve sin volver a llamar a Claude.
    """
    cached = MetricasClaveStore.load(plan_id)
    if cached and cached.status in (ContentJobStatus.DONE, ContentJobStatus.RUNNING):
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    placeholder = MetricasClaveRecord(
        plan_id=plan_id,
        items=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        status=ContentJobStatus.RUNNING,
    )
    MetricasClaveStore.save(placeholder)
    asyncio.create_task(_run_metricasclave_job(plan_id, plan_record))
    return placeholder


async def _run_metricasclave_job(plan_id: str, plan_record: MarketingPlanRecord) -> None:
    agent = MetricasClaveAgent()
    try:
        raw_items, _tokens = await asyncio.to_thread(
            agent.run, plan_record.request, plan_record.plan.metricas_clave
        )
        items = _build_metrica_items(plan_id, plan_record.request.project_id, raw_items)
        record = MetricasClaveRecord(
            plan_id=plan_id,
            items=items,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.DONE,
        )
    except Exception as exc:
        record = MetricasClaveRecord(
            plan_id=plan_id,
            items=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            status=ContentJobStatus.FAILED,
            error=str(exc),
        )
    MetricasClaveStore.save(record)


async def _build_audit_context(site_url: str) -> Tuple[str, Optional[float], Optional[float]]:
    """Runs a live audit and renders it as plain text for the LLM prompt."""
    try:
        result = await run_full_audit(site_url)
    except Exception as exc:
        return f"No se pudo auditar el sitio en vivo ({exc}). Usa supuestos razonables para el rubro.", None, None

    failed_checks: List[str] = []
    for categoria, checks in (result.checks or {}).items():
        for check_name, passed in checks.items():
            if not passed:
                failed_checks.append(f"{categoria}.{check_name}")

    lines = [
        f"Recovery Score: {result.recovery_score:.1f} / 100",
        f"PageSpeed Score: {result.pagespeed_score if result.pagespeed_score is not None else 'N/A'}",
        f"Checks fallidos ({len(failed_checks)}): {', '.join(failed_checks) if failed_checks else 'ninguno'}",
        f"Tickets generados: {result.resumen.total} (críticos: {result.resumen.criticos}, altos: {result.resumen.altos})",
    ]
    return "\n".join(lines), result.recovery_score, result.pagespeed_score


# ---------------------------------------------------------------------------
# MarketingPlanPDF — reportlab, same visual style as report_engine.BeforeAfterReport
# ---------------------------------------------------------------------------

class MarketingPlanPDF:
    _BLUE = "#2563EB"
    _GRAY = "#6B7280"

    _SECTION_TITLES = [
        ("diagnostico_inicial", "1. Diagnóstico Inicial"),
        ("estrategia_adquisicion", "2. Estrategia de Adquisición"),
        ("calendario_contenido", "3. Calendario de Contenido (30 días)"),
        ("embudo_ventas", "4. Embudo de Ventas"),
        ("estrategia_whatsapp", "5. Estrategia WhatsApp"),
        ("plan_ejecucion_90_dias", "6. Plan de Ejecución (90 días)"),
        ("ia_automatizacion", "7. IA y Automatización"),
        ("metricas_clave", "8. Métricas Clave"),
        ("top_10_acciones", "9. Top 10 Acciones Inmediatas"),
    ]

    @classmethod
    def generate(cls, plan_id: str, req: MarketingGenerateRequest, plan: MarketingPlan) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                HRFlowable,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
            )
        except ImportError as exc:
            raise RuntimeError("reportlab not installed. Run: pip install reportlab") from exc

        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = PLANS_DIR / f"{plan_id}.pdf"

        doc = SimpleDocTemplate(
            str(pdf_path), pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()

        def style(name: str, **kw) -> ParagraphStyle:
            return ParagraphStyle(name, parent=styles["Normal"], **kw)

        story: List[Any] = []
        story.append(Paragraph(
            "<b>WPRecover · Marketing OS</b>",
            style("h1", fontSize=22, textColor=colors.HexColor(cls._BLUE), alignment=TA_CENTER, leading=28),
        ))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Plan de Marketing — {cls._esc(req.site_url)}",
            style("sub", fontSize=12, textColor=colors.HexColor(cls._GRAY), alignment=TA_CENTER, spaceAfter=4),
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor(cls._BLUE), spaceAfter=10))
        story.append(Paragraph(
            f"Rubro: {cls._esc(req.business_type)} · Ciudad: {cls._esc(req.city)} · "
            f"Presupuesto: {cls._esc(req.monthly_budget)} · "
            f"Paquete: {cls._esc(req.plan)} · Fecha: {datetime.now().strftime('%d/%m/%Y')}",
            style("meta", fontSize=9, textColor=colors.HexColor(cls._GRAY)),
        ))
        story.append(Spacer(1, 14))

        plan_dict = plan.model_dump()
        for key, title in cls._SECTION_TITLES:
            story.append(Paragraph(title, style("h2", fontSize=13, textColor=colors.HexColor(cls._BLUE), spaceAfter=6)))
            value = plan_dict[key]
            for line in cls._render_section(key, value):
                story.append(Paragraph(line, style("body", fontSize=9.5, leading=13, spaceAfter=3)))
            story.append(Spacer(1, 10))

        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor(cls._GRAY)))
        story.append(Paragraph(
            "Generado por WPRecover 2.0 — Marketing OS (M10)",
            style("footer", fontSize=8, textColor=colors.HexColor(cls._GRAY), alignment=TA_CENTER),
        ))

        doc.build(story)
        return pdf_path

    @staticmethod
    def _esc(text: Any) -> str:
        """Escapa los caracteres especiales de XML para que el mini-parser de
        markup de ReportLab (Paragraph) no se rompa con &, <, > crudos en el
        texto del plan ('paraparser: ... unclosed tags'). El markup intencional
        (<b>, <i>, &nbsp;) lo añade el caller DESPUÉS de escapar."""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @classmethod
    def _render_section(cls, key: str, value: Any) -> List[str]:
        esc = cls._esc
        if key == "calendario_contenido":
            return [
                f"<b>Día {esc(item['dia'])}</b> — {esc(item['objetivo'])} ({esc(item['formato'])}): "
                f"{esc(item['guion'])} <i>CTA: {esc(item['cta'])}</i>"
                for item in value
            ]
        if key == "plan_ejecucion_90_dias":
            lines: List[str] = []
            for period_label, period_key in [
                ("Semana 1-2", "semana_1_2"), ("Semana 3-4", "semana_3_4"),
                ("Mes 2", "mes_2"), ("Mes 3", "mes_3"),
            ]:
                lines.append(f"<b>{period_label}:</b>")
                lines.extend(f"&nbsp;&nbsp;• {esc(item)}" for item in value[period_key])
            return lines
        return [f"• {esc(item)}" for item in value]


# ---------------------------------------------------------------------------
# MarketingPlanStore
# ---------------------------------------------------------------------------

class MarketingPlanStore:
    @staticmethod
    def _path(plan_id: str) -> Path:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        return PLANS_DIR / f"{plan_id}.json"

    @classmethod
    def save(cls, record: MarketingPlanRecord, pdf_bytes: Optional[bytes] = None) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO marketing_plans (id, project_id, data, pdf_data)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        data = EXCLUDED.data,
                        pdf_data = COALESCE(EXCLUDED.pdf_data, marketing_plans.pdf_data)
                    """,
                    (record.id, record.request.project_id, Json(json.loads(record.model_dump_json())), pdf_bytes),
                )
            return

        cls._path(record.id).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, plan_id: str) -> Optional[MarketingPlanRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM marketing_plans WHERE id = %s", (plan_id,))
                row = cur.fetchone()
            return MarketingPlanRecord(**row[0]) if row else None

        path = cls._path(plan_id)
        if not path.exists():
            return None
        return MarketingPlanRecord(**json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def load_pdf_bytes(cls, plan_id: str) -> Optional[bytes]:
        if not db.is_configured():
            return None
        with db.get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pdf_data FROM marketing_plans WHERE id = %s", (plan_id,))
            row = cur.fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

    @classmethod
    def list_all(cls, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        "SELECT data FROM marketing_plans WHERE project_id = %s ORDER BY inserted_at DESC",
                        (project_id,),
                    )
                else:
                    cur.execute("SELECT data FROM marketing_plans ORDER BY inserted_at DESC")
                rows = cur.fetchall()
            return [cls._summary(data) for (data,) in rows]

        if not PLANS_DIR.exists():
            return []
        result = []
        for f in sorted(PLANS_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if project_id and data.get("request", {}).get("project_id") != project_id:
                    continue
                result.append(cls._summary(data))
            except Exception:
                pass
        return result

    @staticmethod
    def _summary(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": data["id"],
            "site_url": data["request"]["site_url"],
            "project_id": data["request"].get("project_id"),
            "recovery_score": data.get("recovery_score"),
            "pdf_available": data.get("pdf_available", False),
            "created_at": data["created_at"],
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def generate_marketing_plan(req: MarketingGenerateRequest) -> MarketingPlanRecord:
    """Single entry-point: audit + Claude plan + PDF + persist."""
    audit_context, recovery_score, pagespeed_score = await _build_audit_context(req.site_url)

    agent = MarketingAgent()
    plan, _tokens = await asyncio.to_thread(agent.run, req, audit_context)

    plan_id = f"mkt_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    record = MarketingPlanRecord(
        id=plan_id,
        request=req,
        plan=plan,
        recovery_score=recovery_score,
        pagespeed_score=pagespeed_score,
        pdf_available=False,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    pdf_bytes: Optional[bytes] = None
    try:
        pdf_path = MarketingPlanPDF.generate(plan_id, req, plan)
        record.pdf_available = True
        if db.is_configured():
            pdf_bytes = pdf_path.read_bytes()
    except RuntimeError:
        pass  # reportlab not installed — plan still saved without PDF

    MarketingPlanStore.save(record, pdf_bytes=pdf_bytes)
    return record
