from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import db
from models import (
    ChartData,
    ClientReportSection,
    GuaranteeResult,
    ReportRecord,
    ReportRequest,
    SiteMetrics,
)

REPORTS_DIR = Path(__file__).parent / "reports"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEIGHTS: Dict[str, float] = {
    "SEO": 0.30,
    "Performance": 0.20,
    "Conversion": 0.20,
    "Seguridad": 0.15,
    "WooCommerce": 0.15,
}

# Human-readable check names (Spanish, client-facing)
CHECK_LABELS: Dict[str, str] = {
    "title": "Título de la página",
    "meta_desc": "Descripción en Google",
    "canonical": "Etiqueta canonical",
    "og_image": "Imagen en redes sociales",
    "schema": "Datos estructurados (Schema)",
    "sitemap": "Mapa del sitio XML",
    "robots": "Archivo robots.txt",
    "h1": "Encabezado principal (H1)",
    "alt_imgs": "Texto alternativo en imágenes",
    "LCP": "Velocidad de carga principal (LCP)",
    "CLS": "Estabilidad visual (CLS)",
    "INP": "Tiempo de respuesta (INP)",
    "cache": "Caché del navegador",
    "gzip": "Compresión de archivos (GZIP)",
    "webp": "Imágenes en formato WebP",
    "lazy_load": "Carga diferida de imágenes",
    "tel_clickeable": "Teléfono clickeable en móvil",
    "whatsapp": "Botón de WhatsApp",
    "formularios": "Formularios de contacto",
    "CTA": "Llamada a la acción (CTA)",
    "tracking": "Analytics y seguimiento",
    "wp_version": "Versión de WordPress oculta",
    "plugins_desact": "Plugins innecesarios eliminados",
    "meta_generator": "Versión WP no expuesta",
    "headers": "Cabeceras de seguridad HTTP",
    "ssl": "Certificado SSL/HTTPS",
    "productos_sin_cat": "Categorías de productos",
    "productos_sin_img": "Imágenes de productos",
    "slugs_dup": "URLs de productos (sin duplicados)",
    "precios": "Precios configurados",
    "pasarelas": "Pasarela de pago activa",
}

# Non-technical category labels and descriptions for client report
CATEGORY_CLIENT: Dict[str, Tuple[str, str]] = {
    "SEO": (
        "Posicionamiento en Google",
        "Mejoras que ayudan a que tu negocio aparezca mejor en los resultados de búsqueda.",
    ),
    "Performance": (
        "Velocidad del sitio",
        "Optimizaciones que hacen que tu web cargue más rápido, reduciendo el abandono de visitantes.",
    ),
    "Conversion": (
        "Captación de clientes",
        "Elementos que facilitan que los visitantes te contacten o realicen una compra.",
    ),
    "Seguridad": (
        "Seguridad web",
        "Protecciones que mantienen tu sitio y los datos de tus clientes seguros.",
    ),
    "WooCommerce": (
        "Tienda online",
        "Correcciones en tu tienda para que los clientes puedan comprar sin problemas.",
    ),
}


# ---------------------------------------------------------------------------
# RecoveryScoreCalculator
# ---------------------------------------------------------------------------

class RecoveryScoreCalculator:
    """
    Weighted score: SEO 30% + Performance 20% + Conversion 20%
                    + Seguridad 15% + WooCommerce 15%
    """

    @classmethod
    def calculate(cls, checks: Dict[str, Dict[str, bool]]) -> float:
        total = 0.0
        for cat, weight in WEIGHTS.items():
            cat_checks = checks.get(cat, {})
            if not cat_checks:
                continue
            passed = sum(1 for v in cat_checks.values() if v)
            total += (passed / len(cat_checks)) * 100 * weight
        return round(total, 2)

    @classmethod
    def per_category(cls, checks: Dict[str, Dict[str, bool]]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for cat in WEIGHTS:
            cat_checks = checks.get(cat, {})
            if cat_checks:
                passed = sum(1 for v in cat_checks.values() if v)
                result[cat] = round((passed / len(cat_checks)) * 100, 1)
            else:
                result[cat] = 0.0
        return result

    @classmethod
    def checks_diff(
        cls,
        before: Dict[str, Dict[str, bool]],
        after: Dict[str, Dict[str, bool]],
    ) -> Tuple[List[str], List[str]]:
        """Returns (fixed_labels, regressed_labels) in human-readable Spanish."""
        fixed, regressed = [], []
        for cat, post_checks in after.items():
            pre_checks = before.get(cat, {})
            for name, post_val in post_checks.items():
                pre_val = pre_checks.get(name, post_val)
                label = CHECK_LABELS.get(name, name)
                if not pre_val and post_val:
                    fixed.append(label)
                elif pre_val and not post_val:
                    regressed.append(label)
        return fixed, regressed


# ---------------------------------------------------------------------------
# GuaranteeEvaluator
# ---------------------------------------------------------------------------

class GuaranteeEvaluator:
    THRESHOLD = 15.0  # minimum point improvement to honour the guarantee

    @classmethod
    def evaluate(cls, score_before: float, score_after: float) -> GuaranteeResult:
        improvement = round(score_after - score_before, 2)
        improvement_pct = round((improvement / score_before * 100) if score_before > 0 else 0.0, 2)
        return GuaranteeResult(
            guarantee_met=improvement >= cls.THRESHOLD,
            improvement_points=improvement,
            improvement_pct=improvement_pct,
            threshold=cls.THRESHOLD,
            score_before=score_before,
            score_after=score_after,
        )


# ---------------------------------------------------------------------------
# ClientReport
# ---------------------------------------------------------------------------

class ClientReport:
    """Builds a non-technical JSON report with chart data for the client."""

    @classmethod
    def build(
        cls,
        ticket_id: str,
        req: ReportRequest,
        score_before: float,
        score_after: float,
        per_cat_before: Dict[str, float],
        per_cat_after: Dict[str, float],
        checks_fixed: List[str],
        checks_regressed: List[str],
        guarantee: GuaranteeResult,
    ) -> Tuple[List[ClientReportSection], ChartData, str]:
        sections: List[ClientReportSection] = []
        for cat in WEIGHTS:
            nombre, desc = CATEGORY_CLIENT.get(cat, (cat, ""))
            sb = per_cat_before.get(cat, 0.0)
            sa = per_cat_after.get(cat, 0.0)
            # checks fixed in this specific category
            cat_fixed = [
                CHECK_LABELS.get(k, k)
                for k, v in req.post_fix.checks.get(cat, {}).items()
                if v and not req.baseline.checks.get(cat, {}).get(k, True)
            ]
            sections.append(ClientReportSection(
                categoria=cat,
                nombre_simple=nombre,
                descripcion=desc,
                score_antes=sb,
                score_despues=sa,
                delta=round(sa - sb, 1),
                checks_arreglados=cat_fixed,
            ))

        chart = ChartData(
            labels=list(WEIGHTS.keys()),
            before=[per_cat_before.get(c, 0.0) for c in WEIGHTS],
            after=[per_cat_after.get(c, 0.0) for c in WEIGHTS],
            weights=[int(w * 100) for w in WEIGHTS.values()],
        )

        delta = guarantee.improvement_points
        total_fixed = len(checks_fixed)
        if score_before == score_after:
            # Initial diagnostic report — no fixes applied yet.
            n_issues = sum(
                1 for cat_checks in req.baseline.checks.values()
                for v in cat_checks.values() if not v
            )
            resumen = (
                f"Diagnóstico inicial: tu sitio obtuvo un Recovery Score de {score_before:.0f}/100. "
                f"Detectamos {n_issues} {'punto' if n_issues == 1 else 'puntos'} de mejora "
                f"que, una vez corregidos, están cubiertos por nuestra garantía de "
                f"al menos {cls.THRESHOLD:.0f} puntos de mejora."
            )
        else:
            resumen = (
                f"Mejoramos tu sitio web en {total_fixed} {'área' if total_fixed == 1 else 'áreas'} clave. "
                f"Tu puntuación aumentó de {score_before:.0f} a {score_after:.0f} puntos "
                f"({'+' if delta >= 0 else ''}{delta:.1f} pts, {guarantee.improvement_pct:+.1f}%). "
            )
            if guarantee.guarantee_met:
                resumen += "✓ La garantía de mejora ha sido cumplida."
            else:
                resumen += f"Se requieren {cls.THRESHOLD - delta:.1f} pts adicionales para cumplir la garantía."

        return sections, chart, resumen

    THRESHOLD = GuaranteeEvaluator.THRESHOLD


# ---------------------------------------------------------------------------
# BeforeAfterReport — PDF generation
# ---------------------------------------------------------------------------

class BeforeAfterReport:
    """Generates a professional PDF using reportlab."""

    # Brand colours
    _BLUE = "#2563EB"
    _GREEN = "#10B981"
    _RED = "#EF4444"
    _GRAY = "#6B7280"
    _LIGHT = "#F3F4F6"

    # Colour per Recovery Score category — usada como bullet cuadrado de color
    # delante del nombre de cada categoría en la tabla de scores.
    _CAT_COLOR: Dict[str, str] = {
        "SEO": "#2563EB",          # azul
        "Performance": "#10B981",  # verde
        "Conversion": "#F97316",   # naranja
        "Seguridad": "#EF4444",    # rojo
        "WooCommerce": "#8B5CF6",  # morado
    }

    @staticmethod
    def _esc(text: Any) -> str:
        """Escapa los caracteres especiales de XML para que el mini-parser de
        markup de ReportLab (Paragraph) no se rompa con &, <, > crudos en el
        texto libre ('paraparser: ... unclosed tags'). El markup intencional
        (<b>, <font>) lo añade el caller DESPUÉS de escapar. NO aplicar a celdas
        de Table: esas no se parsean como markup y mostrarían &amp; literal."""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @classmethod
    def generate(
        cls,
        ticket_id: str,
        req: ReportRequest,
        score_before: float,
        score_after: float,
        per_cat_before: Dict[str, float],
        per_cat_after: Dict[str, float],
        checks_fixed: List[str],
        guarantee: GuaranteeResult,
        resumen_ejecutivo: str,
    ) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                HRFlowable,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:
            raise RuntimeError("reportlab not installed. Run: pip install reportlab") from exc

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        pdf_path = REPORTS_DIR / f"{ticket_id}_{ts}.pdf"

        doc = SimpleDocTemplate(
            str(pdf_path), pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()

        def style(name: str, **kw) -> ParagraphStyle:
            return ParagraphStyle(name, parent=styles["Normal"], **kw)

        story = []

        # ── Header ────────────────────────────────────────────────────────────
        is_diagnostico = score_before == score_after
        header_subtitle = (
            "Reporte de Diagnóstico Inicial" if is_diagnostico
            else "Reporte de Recuperación de Sitio Web"
        )
        story.append(Paragraph(
            "<b>WPRecover</b>",
            style("h1", fontSize=34, textColor=colors.HexColor(cls._BLUE), alignment=TA_CENTER, leading=40),
        ))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            header_subtitle,
            style("sub", fontSize=14, textColor=colors.HexColor(cls._GRAY), alignment=TA_CENTER, spaceAfter=4),
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor(cls._BLUE), spaceAfter=10))

        # ── Client info ───────────────────────────────────────────────────────
        info = [
            ["Cliente:", req.client_name, "Sitio:", req.site_url],
            ["Fecha:", datetime.now().strftime("%d/%m/%Y"), "Ticket:", ticket_id],
        ]
        if req.client_logo_url:
            info[0].insert(0, f"Logo: {req.client_logo_url}")

        info_table = Table(info, colWidths=[3 * cm, 6 * cm, 2.5 * cm, 5 * cm])
        info_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 12))

        # ── Score summary ─────────────────────────────────────────────────────
        delta = guarantee.improvement_points
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        pct_str = f"{guarantee.improvement_pct:+.1f}%"

        if is_diagnostico:
            score_data = [
                ["Recovery Score", "Resultado"],
                ["Score General", f"{score_before:.1f} / 100"],
            ]
            score_table = Table(score_data, colWidths=[8 * cm, 8 * cm])
        else:
            score_data = [
                ["Recovery Score", "Antes", "Después", "Mejora", "% Mejora"],
                ["Score General", f"{score_before:.1f}", f"{score_after:.1f}", delta_str, pct_str],
            ]
            score_table = Table(score_data, colWidths=[5.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm])

        score_col_colors = colors.HexColor(cls._GREEN if delta >= 0 else cls._RED)
        score_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(cls._BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(cls._LIGHT)),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 1), (-1, -1), 13),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (3, 1), (-1, -1), score_col_colors),
            ("FONTNAME", (3, 1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 10))

        # ── Guarantee badge ───────────────────────────────────────────────────
        if is_diagnostico:
            story.append(Paragraph(
                f'<font color="{cls._BLUE}"><b>[DIAGNÓSTICO INICIAL]</b></font>'
                f'  Score actual: <b>{score_before:.1f}/100</b>'
                f'  —  Garantía de mejora: al menos {guarantee.threshold:.0f} pts tras intervención',
                style("badge", fontSize=11, spaceAfter=14),
            ))
        else:
            badge_color = cls._GREEN if guarantee.guarantee_met else cls._GRAY
            badge_text = "GARANTIA CUMPLIDA" if guarantee.guarantee_met else "EN PROGRESO"
            story.append(Paragraph(
                f'<font color="{badge_color}"><b>[{badge_text}]</b></font>'
                f'  Mejora de <b>{delta_str} pts</b> ({pct_str})'
                f'  —  Umbral de garantia: {guarantee.threshold:.0f} pts',
                style("badge", fontSize=11, spaceAfter=14),
            ))

        # ── Per-category breakdown ────────────────────────────────────────────
        story.append(Paragraph(
            "<b>Desglose por Categoría</b>",
            style("h2", fontSize=13, textColor=colors.HexColor(cls._BLUE), spaceAfter=6),
        ))
        # Nombre de categoría con bullet cuadrado de color según _CAT_COLOR.
        cat_cell_style = style("catcell", fontSize=11, leading=13)

        def cat_cell(cat: str) -> Paragraph:
            color = cls._CAT_COLOR.get(cat, cls._GRAY)
            return Paragraph(
                f'<font color="{color}">■</font> <b>{cls._esc(cat)}</b>',
                cat_cell_style,
            )

        if is_diagnostico:
            cat_data = [["Categoría", "Peso", "Score actual"]]
            for cat, weight in WEIGHTS.items():
                sb = per_cat_before.get(cat, 0.0)
                cat_data.append([cat_cell(cat), f"{int(weight * 100)}%", f"{sb:.0f} / 100"])
            cat_table = Table(cat_data, colWidths=[7 * cm, 3 * cm, 6 * cm])
        else:
            cat_data = [["Categoría", "Peso", "Antes", "Después", "Delta"]]
            for cat, weight in WEIGHTS.items():
                sb = per_cat_before.get(cat, 0.0)
                sa = per_cat_after.get(cat, 0.0)
                d = sa - sb
                cat_data.append([cat_cell(cat), f"{int(weight * 100)}%", f"{sb:.0f}", f"{sa:.0f}",
                                  f"+{d:.0f}" if d >= 0 else f"{d:.0f}"])
            cat_table = Table(cat_data, colWidths=[5.5 * cm, 2 * cm, 2.5 * cm, 2.5 * cm, 3.5 * cm])

        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(cls._BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(cls._LIGHT), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 14))


        # ── Checks fixed / Issues found ──────────────────────────────────────────
        if is_diagnostico:
            failed_checks = [
                CHECK_LABELS.get(name, name)
                for cat_checks in req.baseline.checks.values()
                for name, passed in cat_checks.items()
                if not passed
            ]
            if failed_checks:
                story.append(Paragraph(
                    "<b>Puntos a Corregir</b>",
                    style("h2", fontSize=13, textColor=colors.HexColor(cls._BLUE), spaceAfter=6),
                ))
                for label in failed_checks:
                    story.append(Paragraph(
                        f'<font color="{cls._RED}">✗</font>  {cls._esc(label)}',
                        style("issue", fontSize=11, leftIndent=8, spaceAfter=3),
                    ))
                story.append(Spacer(1, 12))
        elif checks_fixed:
            story.append(Paragraph(
                "<b>Correcciones Aplicadas</b>",
                style("h2", fontSize=13, textColor=colors.HexColor(cls._BLUE), spaceAfter=6),
            ))
            for label in checks_fixed:
                story.append(Paragraph(
                    f'<font color="{cls._GREEN}">✓</font>  {cls._esc(label)}',
                    style("fix", fontSize=11, leftIndent=8, spaceAfter=3),
                ))
            story.append(Spacer(1, 12))

        # ── Executive summary ─────────────────────────────────────────────────
        story.append(Paragraph(
            "<b>Resumen Ejecutivo</b>",
            style("h2", fontSize=13, textColor=colors.HexColor(cls._BLUE), spaceAfter=4),
        ))
        story.append(Paragraph(cls._esc(resumen_ejecutivo), style("body", fontSize=11, spaceAfter=10)))

        if req.notas:
            story.append(Paragraph("<b>Notas adicionales:</b>", style("nb", fontSize=11, spaceAfter=2)))
            story.append(Paragraph(cls._esc(req.notas), style("nc", fontSize=10)))
            story.append(Spacer(1, 10))

        # ── Footer ────────────────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor(cls._GRAY)))
        story.append(Paragraph(
            "Generado por WPRecover 2.0 — Motor de Reportes M5",
            style("footer", fontSize=8, textColor=colors.HexColor(cls._GRAY), alignment=TA_CENTER),
        ))
        story.append(Paragraph(
            f"Documento confidencial — {cls._esc(req.client_name)} — {datetime.now().strftime('%d/%m/%Y')}",
            style("confidential", fontSize=8, textColor=colors.HexColor(cls._GRAY),
                  alignment=TA_CENTER, spaceBefore=2),
        ))

        doc.build(story)
        return pdf_path


# ---------------------------------------------------------------------------
# FullProjectReport — single on-demand PDF aggregating audit + marketing
# ---------------------------------------------------------------------------

class FullProjectReport:
    """
    Builds ONE downloadable PDF per project, on-demand and in-memory (no disk),
    aggregating everything that already exists in the stores:

      1. Portada            — cliente, URL, Recovery Score antes/después, fecha
      2. Diagnóstico técnico — tickets derivados de project.checks_before
      3. Plan de marketing   — los 9 módulos del plan base (si existe)
      4. Módulos M10 ejecutados (solo los que tengan datos):
           M3 Contenido · M5 WhatsApp · M6 Plan 90 días ·
           M7 IA/Automatización · M8 Métricas · M9 Top 10 acciones
      5. Footer WPRecover

    Cada bloque se OMITE elegantemente si no hay datos — el PDF solo muestra lo
    que existe. Reutiliza BeforeAfterReport._esc + la paleta de marca y, para el
    plan base, MarketingPlanPDF._render_section.
    """

    _BLUE = BeforeAfterReport._BLUE
    _GREEN = BeforeAfterReport._GREEN
    _RED = BeforeAfterReport._RED
    _GRAY = BeforeAfterReport._GRAY
    _LIGHT = BeforeAfterReport._LIGHT

    _esc = staticmethod(BeforeAfterReport._esc)

    # Prioridad -> color de etiqueta (paleta de marca existente)
    _PRIO_COLOR = {
        "Critica": _RED,
        "Alta": _RED,
        "Media": _BLUE,
        "Baja": _GRAY,
    }

    # Hoja de estilos del PDF (CSS paged-media para WeasyPrint).
    # - @page :first pinta el degradado a sangre completa (portada full-bleed) y
    #   suprime el footer en la portada (margin 0 → sin caja @bottom-center).
    # - el resto de páginas lleva el footer "Generado por WPRecover · wprecover.cl".
    _CSS = """
        @page {
            size: A4;
            margin: 2cm;
            @bottom-center {
                content: "Generado por WPRecover · wprecover.cl";
                font-size: 8pt;
                color: #6B7280;
            }
        }
        @page :first {
            margin: 0;
            background: linear-gradient(135deg, #0A2540 0%, #1E3A5F 100%);
        }
        * { box-sizing: border-box; }
        body {
            font-family: "Helvetica Neue", Arial, "DejaVu Sans", sans-serif;
            font-size: 9.5pt;
            line-height: 1.4;
            color: #1F2937;
            margin: 0;
        }
        .cover {
            color: #FFFFFF;
            padding: 4cm 2.5cm 0;
            page-break-after: always;
        }
        .cover .brand { font-size: 30pt; font-weight: 700; letter-spacing: .5px; }
        .cover-sub { font-size: 13pt; color: #9DB8D6; margin-top: 4px; }
        .client-name { font-size: 38pt; font-weight: 800; margin: 2.4cm 0 .3cm; line-height: 1.05; }
        .cover-meta { font-size: 12pt; color: #C6D6EA; margin: 2px 0; }
        .score-grid { margin-top: 2.2cm; }
        .score-grid > div {
            display: inline-block;
            background: rgba(255,255,255,.10);
            border: 1px solid rgba(255,255,255,.25);
            border-radius: 10px;
            padding: 14px 22px;
            margin-right: 14px;
            text-align: center;
        }
        .score-label {
            display: block; font-size: 9pt; color: #9DB8D6;
            text-transform: uppercase; letter-spacing: 1px;
        }
        .score-val { display: block; font-size: 26pt; font-weight: 700; }
        .score-single { margin-top: 2.2cm; }
        .score-val-big { display: block; font-size: 54pt; font-weight: 800; }
        .cover-foot { margin-top: 3cm; font-size: 9pt; color: #9DB8D6; }
        .section-header {
            background: #1D6FA4;
            color: #FFFFFF;
            font-size: 13pt;
            font-weight: 700;
            padding: 8px 12px;
            border-radius: 4px;
            margin: 18px 0 10px;
        }
        .section-header .secnum {
            display: inline-block;
            width: 22px; height: 22px;
            line-height: 22px;
            text-align: center;
            background: rgba(255,255,255,.22);
            border-radius: 50%;
            margin-right: 10px;
            font-size: 11pt;
        }
        .subhead { color: #1D6FA4; font-size: 11.5pt; margin: 14px 0 6px; }
        .line { margin: 0 0 3px; }
        .muted { color: #6B7280; }
        p.muted { margin: 0 0 6px; }
        .ticket {
            border-left: 4px solid #6B7280;
            background: #F8FAFC;
            padding: 6px 10px;
            margin: 0 0 6px;
            border-radius: 0 4px 4px 0;
        }
        .prio { font-weight: 700; }
        .content-card {
            background: #F8FAFC;
            border: 1px solid #E5E7EB;
            border-left: 4px solid #1D6FA4;
            border-radius: 6px;
            padding: 10px 14px;
            margin: 0 0 10px;
            page-break-inside: avoid;
        }
        .content-card .cc-head { font-weight: 700; color: #0A2540; font-size: 10.5pt; margin: 0 0 2px; }
        .content-card .cc-obj  { color: #1D6FA4; font-weight: 600; }
        .content-card .cc-body { margin: 6px 0; white-space: pre-wrap; }
        .content-card .cc-meta {
            border-top: 1px solid #E5E7EB;
            padding-top: 5px; margin-top: 6px;
            color: #6B7280; font-size: 8.5pt;
        }
        .content-card .cc-tags { color: #1D6FA4; font-weight: 600; }
        .nav-pills {
            margin: 0 0 16px;
            page-break-inside: avoid;
            page-break-after: avoid;
        }
        .nav-pills .pill {
            display: inline-block;
            background: #EAF2F8;
            color: #1D6FA4;
            border: 1px solid #CFE0EF;
            border-radius: 999px;
            padding: 3px 11px;
            margin: 0 6px 6px 0;
            font-size: 8.5pt;
            font-weight: 600;
        }
        .nav-pills .pill .pill-num {
            color: #6B7280;
            font-weight: 700;
            margin-right: 5px;
        }
        .tkt-id {
            display: inline-block;
            font-family: "DejaVu Sans Mono", "Courier New", monospace;
            font-size: 8pt;
            background: #EEF2F7;
            color: #374151;
            border: 1px solid #E5E7EB;
            border-radius: 4px;
            padding: 1px 6px;
            margin-right: 6px;
        }
        .ia-card {
            background: #F8FAFC;
            border: 1px solid #E5E7EB;
            border-left: 4px solid #1D6FA4;
            border-radius: 6px;
            padding: 10px 14px;
            margin: 0 0 10px;
            page-break-inside: avoid;
        }
        .ia-card .ia-head { font-size: 10.5pt; color: #0A2540; margin: 0 0 6px; }
        .ia-card .ia-badges { margin: 0 0 6px; }
        .badge {
            display: inline-block;
            font-size: 8pt;
            font-weight: 700;
            border-radius: 999px;
            padding: 2px 9px;
            margin: 0 6px 0 0;
            border: 1px solid #CFE0EF;
        }
        .badge-costo { background: #ECFDF5; color: #047857; border-color: #A7F3D0; }
        .badge-setup { background: #EEF2F7; color: #374151; border-color: #E5E7EB; }
        .metrics-table {
            width: 100%;
            border-collapse: collapse;
            margin: 0 0 12px;
            font-size: 8.5pt;
        }
        .metrics-table thead { display: table-header-group; }
        .metrics-table th {
            background: #1D6FA4;
            color: #FFFFFF;
            text-align: left;
            padding: 5px 8px;
            font-size: 8.5pt;
        }
        .metrics-table td {
            border-bottom: 1px solid #E5E7EB;
            padding: 5px 8px;
            vertical-align: top;
        }
        .metrics-table tr { page-break-inside: avoid; }
        .metrics-table .metric-extra td {
            color: #6B7280;
            font-size: 8pt;
        }
        .page-break { page-break-before: always; }
    """

    @classmethod
    def generate(
        cls,
        project: Any,
        tickets: Optional[List[Any]] = None,
        marketing: Optional[Any] = None,
        content: Optional[Any] = None,
        whatsapp: Optional[Any] = None,
        plan90: Optional[Any] = None,
        ia: Optional[Any] = None,
        metricas: Optional[Any] = None,
        actions: Optional[Any] = None,
        incluir_contenido_real: bool = False,
    ) -> bytes:
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError("weasyprint not installed. Run: pip install weasyprint") from exc

        # _render_section / _SECTION_TITLES reusados del PDF de marketing. Import
        # diferido: marketing_engine no importa report_engine, así que no hay ciclo,
        # pero lo dejamos local para no acoplar el import de este módulo.
        from marketing_engine import MarketingPlanPDF

        esc = cls._esc
        parts: List[str] = []   # fragmentos HTML del cuerpo (post-portada)
        sec = 0                 # contador de secciones mayores
        section_titles: List[str] = []  # títulos para las nav pills

        def section_header(title: str) -> str:
            nonlocal sec
            sec += 1
            section_titles.append(title)
            return (
                f'<div class="section-header">'
                f'<span class="secnum">{sec}</span>{esc(title)}</div>'
            )

        # ── 1. Portada ─────────────────────────────────────────────────────────
        sb = project.score_before
        sa = project.score_after
        if sb is not None and sa is not None:
            delta = round(sa - sb, 1)
            delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
            score_block = (
                '<div class="score-grid">'
                f'<div><span class="score-label">Antes</span>'
                f'<span class="score-val">{sb:.1f}</span></div>'
                f'<div><span class="score-label">Después</span>'
                f'<span class="score-val">{sa:.1f}</span></div>'
                f'<div><span class="score-label">Mejora</span>'
                f'<span class="score-val">{delta_str}</span></div>'
                '</div>'
            )
        else:
            score_now = sb if sb is not None else (sa if sa is not None else 0.0)
            score_block = (
                '<div class="score-single">'
                f'<span class="score-val-big">{score_now:.1f}</span>'
                '<span class="score-label">Recovery Score / 100</span></div>'
            )

        estado = esc(getattr(project.status, "value", project.status))
        cover = (
            '<section class="cover">'
            '<div class="brand">WPRecover</div>'
            '<div class="cover-sub">Reporte Integral de Proyecto</div>'
            f'<div class="client-name">{esc(project.client_name)}</div>'
            f'<div class="cover-meta">{esc(project.site_url)}</div>'
            f'<div class="cover-meta">Plan {esc(project.plan)} · {estado} · '
            f'{datetime.now().strftime("%d/%m/%Y")}</div>'
            f'{score_block}'
            f'<div class="cover-foot">Proyecto {esc(project.id)}</div>'
            '</section>'
        )

        # ── 2. Diagnóstico técnico ───────────────────────────────────────────────
        if tickets:
            parts.append(section_header("Diagnóstico Técnico"))
            parts.append(
                f'<p class="muted">{len(tickets)} incidencias detectadas en la '
                'auditoría, ordenadas por prioridad.</p>'
            )
            for t in tickets:
                prio = getattr(t.prioridad, "value", t.prioridad)
                cat = getattr(t.categoria, "value", t.categoria)
                color = cls._PRIO_COLOR.get(prio, cls._GRAY)
                parts.append(
                    f'<div class="ticket" style="border-left-color:{color}">'
                    f'<span class="prio" style="color:{color}">[{esc(prio)}]</span> '
                    f'<b>{esc(t.titulo)}</b> '
                    f'<span class="muted">({esc(cat)} · {t.estimacion} min)</span><br>'
                    f'<span class="muted">{esc(t.impacto)}</span></div>'
                )

        # ── 3. Plan de marketing base (9 módulos) ────────────────────────────────
        if marketing is not None:
            plan = marketing.plan
            parts.append('<div class="page-break"></div>')
            parts.append(section_header("Plan de Marketing"))
            plan_dict = plan.model_dump()
            for key, title in MarketingPlanPDF._SECTION_TITLES:
                parts.append(f'<h3 class="subhead">{esc(title)}</h3>')
                # Las líneas ya traen markup válido (<b>, <i>, &nbsp;, •) — NO re-escapar.
                for line in MarketingPlanPDF._render_section(key, plan_dict[key]):
                    parts.append(f'<div class="line">{line}</div>')

        # ── 4. Módulos M10 ejecutados ─────────────────────────────────────────────
        def _has(record, attr: str) -> bool:
            return (
                record is not None
                and getattr(getattr(record, "status", None), "value", getattr(record, "status", None)) == "DONE"
                and bool(getattr(record, attr, None))
            )

        executed: List[str] = []

        # M3 — Contenido (solo si el upsell "Contenido Real" está activo)
        if incluir_contenido_real and _has(content, "pieces"):
            executed.append('<h3 class="subhead">Contenido (Módulo 3) — piezas listas para publicar</h3>')
            for p in content.pieces:
                meta_bits = []
                if p.hashtags:
                    meta_bits.append(f'<span class="cc-tags">{esc(" ".join(p.hashtags))}</span>')
                if p.mejor_horario:
                    meta_bits.append(f'Mejor horario: {esc(p.mejor_horario)}')
                if p.prompt_imagen:
                    meta_bits.append(f'<i>Prompt imagen:</i> {esc(p.prompt_imagen)}')
                meta_html = ' · '.join(meta_bits)
                executed.append(
                    '<div class="content-card">'
                    f'<div class="cc-head">Día {esc(p.dia)} · {esc(p.formato)} '
                    f'<span class="cc-obj">— {esc(p.objetivo)}</span></div>'
                    f'<div class="cc-body">{esc(p.texto_completo)}</div>'
                    + (f'<div class="cc-meta">{meta_html}</div>' if meta_html else '')
                    + '</div>'
                )

        # M5 — WhatsApp
        if _has(whatsapp, "mensajes"):
            executed.append('<h3 class="subhead">Mensajes de WhatsApp (Módulo 5)</h3>')
            for m in whatsapp.mensajes:
                executed.append(f'<div class="line"><b>{esc(m.categoria)}</b></div>')
                executed.append(f'<div class="line">{esc(m.mensaje_texto)}</div>')
                extra = []
                if m.variables_sugeridas:
                    extra.append(f"Variables: {esc(', '.join(m.variables_sugeridas))}")
                if m.mejor_momento_envio:
                    extra.append(f"Cuándo enviar: {esc(m.mejor_momento_envio)}")
                if extra:
                    executed.append(f'<div class="line muted">{" · ".join(extra)}</div>')

        # M6 — Plan 90 días (tickets)
        if _has(plan90, "tickets"):
            executed.append('<h3 class="subhead">Plan de Ejecución 90 días (Módulo 6)</h3>')
            executed.extend(cls._render_tickets(plan90.tickets))

        # M7 — IA y automatización
        if _has(ia, "items"):
            executed.append('<h3 class="subhead">IA y Automatización (Módulo 7)</h3>')
            executed.extend(cls._render_ia_cards(ia.items))

        # M8 — Métricas clave
        if _has(metricas, "items"):
            executed.append('<h3 class="subhead">Métricas Clave (Módulo 8)</h3>')
            executed.extend(cls._render_metrics_table(metricas.items))

        # M9 — Top 10 acciones (tickets)
        if _has(actions, "tickets"):
            executed.append('<h3 class="subhead">Top 10 Acciones Inmediatas (Módulo 9)</h3>')
            executed.extend(cls._render_tickets(actions.tickets))

        if executed:
            parts.append('<div class="page-break"></div>')
            parts.append(section_header("Módulos de Marketing Ejecutados"))
            parts.extend(executed)

        nav_pills = cls._render_nav_pills(section_titles)
        html_str = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{cls._CSS}</style></head><body>"
            f"{cover}{nav_pills}{''.join(parts)}"
            "</body></html>"
        )
        return HTML(string=html_str).write_pdf()

    @classmethod
    def _render_tickets(cls, tickets: List[Any]) -> List[str]:
        esc = cls._esc
        out: List[str] = []
        for t in tickets:
            prio = getattr(t.prioridad, "value", t.prioridad)
            color = cls._PRIO_COLOR.get(prio, cls._GRAY)
            tid = getattr(t, "id", "") or ""
            id_chip = f'<span class="tkt-id">{esc(tid)}</span>' if tid else ""
            out.append(
                f'<div class="ticket" style="border-left-color:{color}">'
                f'{id_chip}'
                f'<span class="prio" style="color:{color}">[{esc(prio)}]</span> '
                f'{esc(t.titulo)} '
                f'<span class="muted">({t.estimacion} min)</span></div>'
            )
        return out

    @classmethod
    def _render_nav_pills(cls, module_names: List[str]) -> str:
        """Fila de 'pills' de navegación con los módulos incluidos en el reporte.
        Función pura (devuelve HTML) — testeable sin WeasyPrint."""
        esc = cls._esc
        if not module_names:
            return ""
        pills = "".join(
            f'<span class="pill"><span class="pill-num">{i}</span>{esc(name)}</span>'
            for i, name in enumerate(module_names, start=1)
        )
        return f'<div class="nav-pills">{pills}</div>'

    @classmethod
    def _render_ia_cards(cls, items: List[Any]) -> List[str]:
        """Fichas de IA (M7) como tarjetas con badges de costo/setup/prioridad.
        Función pura (devuelve HTML) — testeable sin WeasyPrint."""
        esc = cls._esc
        out: List[str] = []
        for it in items:
            prio = getattr(it.prioridad, "value", it.prioridad)
            color = cls._PRIO_COLOR.get(prio, cls._GRAY)
            tid = getattr(it, "id", "") or ""
            id_chip = f'<span class="tkt-id">{esc(tid)}</span>' if tid else ""
            badges = (
                f'<span class="badge badge-costo">{esc(it.costo)}</span>'
                f'<span class="badge badge-setup">Setup {it.estimacion} min</span>'
                f'<span class="badge" style="color:{color};border-color:{color}">'
                f'{esc(prio)}</span>'
            )
            pasos = "".join(
                f'<div class="line">&nbsp;&nbsp;• {esc(p)}</div>'
                for p in (getattr(it, "pasos", []) or [])
            )
            momento = (
                f'<div class="line muted"><i>Mejor momento:</i> {esc(it.mejor_momento)}</div>'
                if getattr(it, "mejor_momento", "")
                else ""
            )
            out.append(
                '<div class="ia-card">'
                f'<div class="ia-head">{id_chip}<b>{esc(it.herramienta)}</b></div>'
                f'<div class="ia-badges">{badges}</div>'
                f'<div class="line">{esc(it.caso_uso)}</div>'
                f'{pasos}{momento}'
                '</div>'
            )
        return out

    @classmethod
    def _render_metrics_table(cls, items: List[Any]) -> List[str]:
        """Métricas clave (M8) como tabla estructurada (fórmula/benchmark/objetivo).
        Función pura (devuelve HTML) — testeable sin WeasyPrint."""
        esc = cls._esc
        if not items:
            return []
        rows: List[str] = []
        for mt in items:
            rows.append(
                "<tr>"
                f"<td><b>{esc(mt.nombre)}</b></td>"
                f"<td>{esc(mt.formula)}</td>"
                f"<td>{esc(mt.benchmark)}</td>"
                f"<td>{esc(mt.objetivo)}</td>"
                f"<td>{esc(mt.frecuencia_revision)}</td>"
                "</tr>"
            )
            extra: List[str] = []
            donde = getattr(mt, "donde_medir", []) or []
            if donde:
                extra.append(f"Dónde medir: {esc(', '.join(donde))}")
            if getattr(mt, "mejor_momento", ""):
                extra.append(f"Mejor momento: {esc(mt.mejor_momento)}")
            if extra:
                rows.append(
                    f'<tr class="metric-extra"><td colspan="5">{" · ".join(extra)}</td></tr>'
                )
        header = (
            "<tr><th>Métrica</th><th>Fórmula</th><th>Benchmark</th>"
            "<th>Objetivo</th><th>Revisión</th></tr>"
        )
        return [
            '<table class="metrics-table">'
            f"<thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>"
        ]


# ---------------------------------------------------------------------------
# ReportStore
# ---------------------------------------------------------------------------

class ReportStore:
    """
    Persists and retrieves report records.

    In Postgres mode the actual PDF bytes are stored alongside the JSON
    metadata (column `pdf_data`), since the local `pdf_path` file lives on
    Render's ephemeral disk and won't survive a redeploy — see
    `load_pdf_bytes` / `/report/download/{ticket_id}` in main.py.
    """

    @staticmethod
    def _path(ticket_id: str) -> Path:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        return REPORTS_DIR / f"{ticket_id}.json"

    @classmethod
    def save(cls, record: ReportRecord, pdf_bytes: Optional[bytes] = None) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reports (ticket_id, data, pdf_data)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (ticket_id) DO UPDATE SET
                        data = EXCLUDED.data,
                        pdf_data = COALESCE(EXCLUDED.pdf_data, reports.pdf_data)
                    """,
                    (record.ticket_id, Json(json.loads(record.model_dump_json())), pdf_bytes),
                )
            return

        cls._path(record.ticket_id).write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, ticket_id: str) -> Optional[ReportRecord]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM reports WHERE ticket_id = %s", (ticket_id,))
                row = cur.fetchone()
            return ReportRecord(**row[0]) if row else None

        path = cls._path(ticket_id)
        if not path.exists():
            return None
        return ReportRecord(**json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def load_pdf_bytes(cls, ticket_id: str) -> Optional[bytes]:
        """PDF bytes stored in Postgres for this ticket, if any."""
        if not db.is_configured():
            return None
        with db.get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pdf_data FROM reports WHERE ticket_id = %s", (ticket_id,))
            row = cur.fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM reports ORDER BY ticket_id DESC")
                rows = cur.fetchall()
            result = []
            for (data,) in rows:
                result.append({
                    "ticket_id": data["ticket_id"],
                    "client_name": data["client_name"],
                    "site_url": data["site_url"],
                    "score_before": data["score_before"],
                    "score_after": data["score_after"],
                    "improvement_points": data["improvement_points"],
                    "guarantee_met": data["guarantee_met"],
                    "timestamp": data["timestamp"],
                    "pdf_path": data.get("pdf_path"),
                })
            return result

        if not REPORTS_DIR.exists():
            return []
        result = []
        for f in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append({
                    "ticket_id": data["ticket_id"],
                    "client_name": data["client_name"],
                    "site_url": data["site_url"],
                    "score_before": data["score_before"],
                    "score_after": data["score_after"],
                    "improvement_points": data["improvement_points"],
                    "guarantee_met": data["guarantee_met"],
                    "timestamp": data["timestamp"],
                    "pdf_path": data.get("pdf_path"),
                })
            except Exception:
                pass
        return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def build_full_report(ticket_id: str, req: ReportRequest) -> ReportRecord:
    """Single entry-point: compute everything, generate PDF, persist record."""
    per_cat_before = RecoveryScoreCalculator.per_category(req.baseline.checks)
    per_cat_after = RecoveryScoreCalculator.per_category(req.post_fix.checks)

    score_before = RecoveryScoreCalculator.calculate(req.baseline.checks)
    score_after = RecoveryScoreCalculator.calculate(req.post_fix.checks)

    guarantee = GuaranteeEvaluator.evaluate(score_before, score_after)
    checks_fixed, checks_regressed = RecoveryScoreCalculator.checks_diff(
        req.baseline.checks, req.post_fix.checks
    )

    sections, chart, resumen = ClientReport.build(
        ticket_id, req,
        score_before, score_after,
        per_cat_before, per_cat_after,
        checks_fixed, checks_regressed, guarantee,
    )

    # PDF (graceful failure if reportlab not installed)
    pdf_path: Optional[str] = None
    pdf_bytes: Optional[bytes] = None
    try:
        pdf_file = BeforeAfterReport.generate(
            ticket_id, req,
            score_before, score_after,
            per_cat_before, per_cat_after,
            checks_fixed, guarantee, resumen,
        )
        pdf_path = str(pdf_file)
        if db.is_configured():
            pdf_bytes = pdf_file.read_bytes()
    except RuntimeError:
        pdf_path = None

    ts = datetime.now(timezone.utc).isoformat()
    record = ReportRecord(
        ticket_id=ticket_id,
        client_name=req.client_name,
        site_url=req.site_url,
        timestamp=ts,
        score_before=score_before,
        score_after=score_after,
        improvement_points=guarantee.improvement_points,
        improvement_pct=guarantee.improvement_pct,
        guarantee_met=guarantee.guarantee_met,
        guarantee_threshold=guarantee.threshold,
        pdf_path=pdf_path,
        per_category_before=per_cat_before,
        per_category_after=per_cat_after,
        checks_fixed_labels=checks_fixed,
        checks_regressed_labels=checks_regressed,
        chart_data=chart,
        client_sections=sections,
        notas=req.notas,
    )
    ReportStore.save(record, pdf_bytes=pdf_bytes)
    return record
