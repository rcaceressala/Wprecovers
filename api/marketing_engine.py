from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import db
from models import (
    ContentCalendarItem,
    ContentPiece,
    ContentPiecesRecord,
    MarketingGenerateRequest,
    MarketingPlan,
    MarketingPlanRecord,
    Plan90Dias,
)
from audit_engine import run_full_audit

PLANS_DIR = Path(__file__).parent / "marketing_plans"
CONTENT_DIR = Path(__file__).parent / "content_pieces"

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


async def execute_content_plan(plan_id: str) -> ContentPiecesRecord:
    """Ejecuta el Módulo 3 (Calendario de Contenido) de un plan ya generado.

    Idempotente: si ya existe contenido generado para este plan_id, devuelve el
    resultado cacheado sin volver a llamar a Claude.
    """
    cached = ContentPieceStore.load(plan_id)
    if cached:
        return cached

    plan_record = MarketingPlanStore.load(plan_id)
    if not plan_record:
        raise ValueError(f"No marketing plan found with id '{plan_id}'")

    agent = ContentAgent()
    pieces, _tokens = agent.run(plan_record.request, plan_record.plan.calendario_contenido)

    record = ContentPiecesRecord(
        plan_id=plan_id,
        pieces=pieces,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ContentPieceStore.save(record)
    return record


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
            f"Plan de Marketing — {req.site_url}",
            style("sub", fontSize=12, textColor=colors.HexColor(cls._GRAY), alignment=TA_CENTER, spaceAfter=4),
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor(cls._BLUE), spaceAfter=10))
        story.append(Paragraph(
            f"Rubro: {req.business_type} · Ciudad: {req.city} · Presupuesto: {req.monthly_budget} · "
            f"Paquete: {req.plan} · Fecha: {datetime.now().strftime('%d/%m/%Y')}",
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
    def _render_section(key: str, value: Any) -> List[str]:
        if key == "calendario_contenido":
            return [
                f"<b>Día {item['dia']}</b> — {item['objetivo']} ({item['formato']}): "
                f"{item['guion']} <i>CTA: {item['cta']}</i>"
                for item in value
            ]
        if key == "plan_ejecucion_90_dias":
            lines: List[str] = []
            for period_label, period_key in [
                ("Semana 1-2", "semana_1_2"), ("Semana 3-4", "semana_3_4"),
                ("Mes 2", "mes_2"), ("Mes 3", "mes_3"),
            ]:
                lines.append(f"<b>{period_label}:</b>")
                lines.extend(f"&nbsp;&nbsp;• {item}" for item in value[period_key])
            return lines
        return [f"• {item}" for item in value]


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
    plan, _tokens = agent.run(req, audit_context)

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
