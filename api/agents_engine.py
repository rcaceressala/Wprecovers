from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

import db
from models import AgentResponse, Categoria, PendingFix, SiteContext, Ticket
from project_engine import resolve_api_key
from ticket_engine import CHECK_CONFIG
from wp_agent_client import WPAgentClient

AGENTS_DIR = Path(__file__).parent / "agents"
_HISTORY_DIR = AGENTS_DIR / "history"
_PENDING_DIR = Path(__file__).parent / "fixes" / "pending"

_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# JSON response schema injected into every system prompt
# ---------------------------------------------------------------------------

_JSON_SCHEMA = """\
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin bloques markdown):
{
  "recomendaciones": ["paso 1...", "paso 2...", "paso 3..."],
  "fix_sugerido": "comando WP-CLI o snippet PHP exacto, o null si no aplica",
  "mensaje_cliente": "explicación no técnica en español (2–3 oraciones)",
  "prioridad": "Critica|Alta|Media|Baja",
  "estimacion_impacto": "impacto esperado cuantificable"
}"""

_SEO_WHITELIST = """\
COMANDOS WP-CLI PERMITIDOS (el plugin WPRepro Agent solo ejecuta estos — \
cualquier otro es rechazado por su whitelist):
- wp option update <nombre> <valor>
- wp post meta update <post_id> <meta_key> <meta_value>
- wp plugin activate|deactivate|update|list|status <slug>
- wp cache flush
- wp rewrite flush
- wp yoast ...

Reglas de los comandos:
- <post_id> debe ser numérico (usa el wp_post_id verificado del contexto, nunca lo inventes).
- El valor final puede ir entre comillas dobles si contiene espacios.
- NUNCA uses los caracteres ; & | ` $ < > ni saltos de línea dentro de un comando — \
son rechazados por seguridad.

Si la corrección requiere modificar el contenido (post_content) de una página — por \
ejemplo, insertar o eliminar un <h1> — NO existe un comando wp-cli para eso. En su lugar, \
devuelve un snippet PHP autocontenido dentro de un bloque ```php que use \
add_filter('the_content', ...) (este snippet se aplica vía el pipeline de revisión manual, \
nunca edites post_content directamente ni generes HTML/Markdown fuera del bloque ```php)."""

_SEO_SYSTEM = f"""Eres SEOAgent, especialista en SEO técnico para WordPress dentro de WPRecover 2.0.
Analiza tickets de SEO fallidos y genera recomendaciones precisas y accionables.

EXPERIENCIA: meta tags, canonicals, sitemaps XML, robots.txt, Schema.org, indexación,
Yoast/Rank Math, Core Web Vitals, Google Search Console, penalizaciones algorítmicas.

{_SEO_WHITELIST}

REGLAS PARA RESOLUCIÓN AUTOMÁTICA DE ESTOS DOS CHECKS:
- "Falta meta descripción" (meta_desc): si el contexto incluye un wp_post_id verificado, \
fix_sugerido debe ser EXACTAMENTE una línea:
  wp post meta update <wp_post_id> _yoast_wpseo_metadesc "<descripción de 120-155 caracteres, \
basada en content_excerpt, sin los caracteres prohibidos>"
  Si no hay wp_post_id en el contexto, devuelve fix_sugerido=null y explica en recomendaciones \
que se necesita identificar el post de portada antes de poder aplicar el fix.
- "H1 ausente o duplicado" (h1): usa h1_count del contexto.
  - h1_count == 0 → genera un snippet ```php que inyecte un único <h1> coherente con \
content_excerpt usando add_filter('the_content', ...).
  - h1_count > 1 → genera un snippet ```php que elimine los <h1> adicionales dejando solo \
el primero (por ejemplo con preg_replace en un add_filter('the_content', ...)).
  - Nunca generes un comando wp-cli para este check — no existe uno permitido.

{_JSON_SCHEMA}"""

_PERF_SYSTEM = f"""Eres PerfAgent, especialista en rendimiento web y Core Web Vitals para WordPress dentro de WPRecover 2.0.
Analiza tickets de Performance y genera fixes específicos para mejorar LCP, CLS, INP y PageSpeed.

EXPERIENCIA: LCP, CLS, INP, FCP, TTFB, WebP, lazy loading, caché (Redis, Cloudflare, CDN),
GZIP/Brotli, minificación CSS/JS, render-blocking, PHP-FPM, OPcache, hosting.

{_JSON_SCHEMA}"""

_CRO_SYSTEM = f"""Eres CROAgent, especialista en Conversión y UX para sitios WordPress dentro de WPRecover 2.0.
Analiza tickets de Conversión y genera fixes que maximicen leads, llamadas y ventas.

EXPERIENCIA: CTAs, formularios, botones click-to-call, WhatsApp, heat maps,
funnel de ventas, UX mobile, velocidad percibida, social proof, urgencia/escasez.

{_JSON_SCHEMA}"""

_SEC_SYSTEM = f"""Eres SecAgent, especialista en seguridad WordPress dentro de WPRecover 2.0.
Analiza tickets de Seguridad y genera fixes que protejan el sitio sin interrumpir el servicio.

EXPERIENCIA: SSL/TLS, headers HTTP de seguridad (CSP, HSTS, X-Frame-Options),
WordPress hardening, permisos de archivos, WP-CLI security, malware, spam, backups.

{_JSON_SCHEMA}"""

_WOO_SYSTEM = f"""Eres WooAgent, especialista en WooCommerce dentro de WPRecover 2.0.
Analiza tickets de WooCommerce y genera fixes que recuperen ventas y mejoren el checkout.

EXPERIENCIA: checkout flow, pasarelas de pago (Stripe, PayPal, MercadoPago),
productos sin imagen, inventario, emails transaccionales, cupones, envíos,
SSL en checkout, abandono de carrito, mobile checkout.

{_JSON_SCHEMA}"""

_REPORT_SYSTEM = f"""Eres ReportAgent, especialista en redacción de informes ejecutivos dentro de WPRecover 2.0.
Genera resúmenes claros y accionables para directivos no técnicos.

EXPERIENCIA: redacción ejecutiva, KPIs digitales, ROI de correcciones web,
presentación de resultados antes/después, narrativa de recuperación de sitios.

{_JSON_SCHEMA}"""

_OUTREACH_SYSTEM = f"""Eres OutreachAgent, especialista en prospección de clientes para WPRecover 2.0.
Genera mensajes personalizados de outreach basados en los problemas detectados en el sitio.

EXPERIENCIA: copywriting de ventas, propuesta de valor técnica en lenguaje de negocio,
emails fríos, mensajes LinkedIn/WhatsApp, urgencia sin presión, beneficios cuantificables.

{_JSON_SCHEMA}"""


# ---------------------------------------------------------------------------
# AgentBase
# ---------------------------------------------------------------------------

class AgentBase:
    NOMBRE: str = "BaseAgent"
    SCOPE: str = "General"
    SYSTEM_PROMPT: str = ""
    MODEL: str = _MODEL
    MAX_TOKENS: int = 2048

    def run(
        self,
        ticket: Ticket,
        site_context: SiteContext,
        historial: List[Dict[str, Any]],
        validate: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None,
    ) -> AgentResponse:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install 'anthropic>=0.40.0'"
            ) from exc

        client = _anthropic.Anthropic()
        user_msg = self._build_user_message(ticket, site_context)
        messages: List[Dict[str, Any]] = list(historial) + [
            {"role": "user", "content": user_msg}
        ]

        text, tokens = self._invoke(client, messages)
        parsed = self._parse_json(text)

        # Server-side validation for fix_sugerido (auto-resolvable SEO checks):
        # one corrective retry before giving up and nulling the fix, so an
        # invalid/placeholder/non-whitelisted command never reaches staging.
        if validate is not None:
            ok, reason = validate(parsed)
            if not ok:
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": (
                    f"Tu fix_sugerido anterior no es válido: {reason}. "
                    "Corrígelo siguiendo EXACTAMENTE el formato indicado en las "
                    "instrucciones del sistema (sin placeholders, sin caracteres "
                    "prohibidos, una sola línea si es wp-cli) y responde de nuevo "
                    "con el mismo JSON completo."
                )})
                retry_text, retry_tokens = self._invoke(client, messages)
                tokens += retry_tokens
                retry_parsed = self._parse_json(retry_text)
                ok2, reason2 = validate(retry_parsed)
                if ok2:
                    parsed, text = retry_parsed, retry_text
                else:
                    parsed["fix_sugerido"] = None
                    parsed["recomendaciones"] = list(parsed.get("recomendaciones", [])) + [
                        f"No se pudo generar un fix automático válido tras reintento "
                        f"({reason2}). Requiere revisión manual."
                    ]

        return AgentResponse(
            agent=self.NOMBRE,
            scope=self.SCOPE,
            ticket_id=ticket.id,
            recomendaciones=parsed.get("recomendaciones", [text] if text else []),
            fix_sugerido=parsed.get("fix_sugerido"),
            mensaje_cliente=parsed.get("mensaje_cliente", ""),
            prioridad=parsed.get("prioridad", str(ticket.prioridad)),
            estimacion_impacto=parsed.get("estimacion_impacto", ""),
            tokens_used=tokens,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _invoke(self, client: Any, messages: List[Dict[str, Any]]) -> Tuple[str, int]:
        response = client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=self.SYSTEM_PROMPT,
            messages=messages,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens

    @staticmethod
    def _build_user_message(ticket: Ticket, context: SiteContext) -> str:
        enrichment = ""
        if context.wp_post_id is not None or context.h1_count is not None or context.content_excerpt:
            enrichment = (
                f"\nDATOS VERIFICADOS DEL SITIO (obtenidos en vivo, no asumas otros valores):\n"
                f"wp_post_id (ID del post/página de portada): "
                f"{context.wp_post_id if context.wp_post_id is not None else 'No detectado'}\n"
                f"h1_count (cantidad de <h1> encontrados): "
                f"{context.h1_count if context.h1_count is not None else 'No determinado'}\n"
                f"content_excerpt (extracto del contenido visible): "
                f"{context.content_excerpt or 'No disponible'}\n"
            )
        return (
            f"TICKET:\n"
            f"ID: {ticket.id}\n"
            f"Categoría: {ticket.categoria}\n"
            f"Título: {ticket.titulo}\n"
            f"Prioridad: {ticket.prioridad}\n"
            f"Impacto: {ticket.impacto}\n"
            f"Estimación: {ticket.estimacion} min\n"
            f"Estado: {ticket.estado}\n\n"
            f"CONTEXTO DEL SITIO:\n"
            f"URL: {context.url}\n"
            f"Plataforma: {context.platform}\n"
            f"Recovery Score: {context.recovery_score if context.recovery_score is not None else 'N/A'}\n"
            f"PageSpeed: {context.pagespeed_score if context.pagespeed_score is not None else 'N/A'}\n"
            f"Sector: {context.sector or 'General'}\n"
            f"Notas: {context.notas or 'Ninguna'}\n"
            f"{enrichment}"
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
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
# Specialized agents — each overrides only NOMBRE, SCOPE, SYSTEM_PROMPT
# ---------------------------------------------------------------------------

class SEOAgent(AgentBase):
    NOMBRE = "SEOAgent"
    SCOPE = "SEO"
    SYSTEM_PROMPT = _SEO_SYSTEM


class PerfAgent(AgentBase):
    NOMBRE = "PerfAgent"
    SCOPE = "Performance"
    SYSTEM_PROMPT = _PERF_SYSTEM


class CROAgent(AgentBase):
    NOMBRE = "CROAgent"
    SCOPE = "Conversion"
    SYSTEM_PROMPT = _CRO_SYSTEM


class SecAgent(AgentBase):
    NOMBRE = "SecAgent"
    SCOPE = "Seguridad"
    SYSTEM_PROMPT = _SEC_SYSTEM


class WooAgent(AgentBase):
    NOMBRE = "WooAgent"
    SCOPE = "WooCommerce"
    SYSTEM_PROMPT = _WOO_SYSTEM


class ReportAgent(AgentBase):
    NOMBRE = "ReportAgent"
    SCOPE = "Reportes"
    SYSTEM_PROMPT = _REPORT_SYSTEM


class OutreachAgent(AgentBase):
    NOMBRE = "OutreachAgent"
    SCOPE = "Prospección"
    SYSTEM_PROMPT = _OUTREACH_SYSTEM


# ---------------------------------------------------------------------------
# Scope → agent registry (singletons)
# ---------------------------------------------------------------------------

SCOPE_TO_AGENT: Dict[str, AgentBase] = {
    "SEO": SEOAgent(),
    "Performance": PerfAgent(),
    "Conversion": CROAgent(),
    "Seguridad": SecAgent(),
    "WooCommerce": WooAgent(),
    "Reportes": ReportAgent(),
    "Prospección": OutreachAgent(),
}


# ---------------------------------------------------------------------------
# SEOContextEnricher — pre-LLM enrichment for auto-resolvable SEO tickets
#
# Fetches the live homepage HTML so SEOAgent gets verified facts (the real
# post ID behind the front page, the actual <h1> count, real body text)
# instead of guessing them — required to safely auto-resolve "meta_desc"
# (needs a wp_post_id to target with wp post meta update) and "h1" (needs
# to know whether it's missing vs. duplicated).
# ---------------------------------------------------------------------------

_H1_TAG_RE = re.compile(r"<h1\b", re.IGNORECASE)
_SHORTLINK_RE = re.compile(
    r'rel=["\']shortlink["\'][^>]*href=["\'][^"\']*\?p=(\d+)', re.IGNORECASE
)
_BODY_POST_ID_RE = re.compile(r'\b(?:page-id|postid)-(\d+)\b')
_BODY_TAG_RE = re.compile(r"<body[^>]*>(.*)</body>", re.IGNORECASE | re.DOTALL)
_SCRIPT_STYLE_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Tickets that SEOAgent can resolve automatically — check_name -> handled by
# a verified pre-LLM fetch, see CHECK_CONFIG[Categoria.SEO] in ticket_engine.py.
AUTO_RESOLVABLE_SEO_CHECKS = {"meta_desc", "h1"}

# Reverse lookup: ticket.titulo -> check_name (Ticket has no check_name field,
# so this is how we recognize e.g. "Falta meta descripción" == "meta_desc").
_SEO_CHECK_NAME_BY_TITLE: Dict[str, str] = {
    cfg[0]: check_name
    for check_name, cfg in CHECK_CONFIG.get(Categoria.SEO, {}).items()
}


def _seo_check_name(ticket: Ticket) -> Optional[str]:
    if str(ticket.categoria).split(".")[-1] != "SEO":
        return None
    return _SEO_CHECK_NAME_BY_TITLE.get(ticket.titulo)


def _is_auto_resolvable_seo_ticket(ticket: Ticket) -> bool:
    return _seo_check_name(ticket) in AUTO_RESOLVABLE_SEO_CHECKS


class SEOContextEnricher:
    """Fetches the homepage and extracts wp_post_id / h1_count / content_excerpt."""

    @staticmethod
    def enrich(url: str) -> Dict[str, Any]:
        empty = {"wp_post_id": None, "h1_count": None, "content_excerpt": None}
        if not url:
            return empty

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "WPRecoverBot/2.0"})
                resp.raise_for_status()
                html = resp.text
        except Exception:
            return empty

        h1_count = len(_H1_TAG_RE.findall(html))

        wp_post_id: Optional[int] = None
        match = _SHORTLINK_RE.search(html) or _BODY_POST_ID_RE.search(html)
        if match:
            try:
                wp_post_id = int(match.group(1))
            except ValueError:
                wp_post_id = None

        body_match = _BODY_TAG_RE.search(html)
        body_html = body_match.group(1) if body_match else html
        text = _SCRIPT_STYLE_TAG_RE.sub(" ", body_html)
        text = _ANY_TAG_RE.sub(" ", text)
        text = _WHITESPACE_RE.sub(" ", text).strip()

        return {
            "wp_post_id": wp_post_id,
            "h1_count": h1_count,
            "content_excerpt": text[:500] if text else None,
        }


# ---------------------------------------------------------------------------
# Server-side validation for auto-resolvable SEO fixes
#
# The LLM doesn't reliably follow the system prompt's exact-format mandate
# (observed: it substitutes a literal "POST_ID" placeholder instead of the
# real verified wp_post_id, or pipes several wp-cli commands together with
# "|" — which the WPRepro Agent plugin's whitelist rejects outright). This
# validates fix_sugerido deterministically; AgentBase.run() uses it to force
# one corrective retry before ever staging a non-compliant fix.
# ---------------------------------------------------------------------------

_FORBIDDEN_CMD_CHARS_RE = re.compile(r"[;&|`$<>\r\n]")
_PLACEHOLDER_RE = re.compile(r"\bPOST_ID\b|\{[^}]*post_id[^}]*\}|<[^>]*\bid\b[^>]*>", re.IGNORECASE)


def _validate_seo_fix(
    check_name: str, site_context: SiteContext, parsed: Dict[str, Any]
) -> Tuple[bool, str]:
    fix = parsed.get("fix_sugerido")

    if check_name == "meta_desc":
        if site_context.wp_post_id is None:
            if not fix:
                return True, ""
            return False, "no hay wp_post_id verificado en el contexto; fix_sugerido debe ser null"
        if not fix:
            return False, "hay wp_post_id verificado pero fix_sugerido es null; debe generarse el comando"
        if "\n" in fix.strip():
            return False, "fix_sugerido debe ser una sola línea (un único comando wp-cli)"
        if _FORBIDDEN_CMD_CHARS_RE.search(fix):
            return False, "fix_sugerido contiene caracteres prohibidos (; & | ` $ < > o salto de línea)"
        if _PLACEHOLDER_RE.search(fix):
            return False, "fix_sugerido usa un placeholder (ej. POST_ID) en vez del wp_post_id real"
        expected_prefix = f"wp post meta update {site_context.wp_post_id} _yoast_wpseo_metadesc"
        if not fix.strip().lower().startswith(expected_prefix.lower()):
            return False, f"fix_sugerido debe empezar exactamente con '{expected_prefix}'"
        return True, ""

    if check_name == "h1":
        if not fix:
            return True, ""
        if _extract_wp_cli_commands(fix):
            return False, "fix_sugerido para H1 no debe contener comandos wp-cli, solo un snippet PHP"
        if "```" not in fix:
            return False, "fix_sugerido para H1 debe incluir un snippet PHP dentro de un bloque ```php"
        return True, ""

    return True, ""


# ---------------------------------------------------------------------------
# AgentHistoryStore — append-only JSONL per ticket
# ---------------------------------------------------------------------------

class AgentHistoryStore:
    @staticmethod
    def _path(ticket_id: str) -> Path:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        return _HISTORY_DIR / f"{ticket_id}.jsonl"

    @classmethod
    def append(cls, response: AgentResponse) -> None:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_history (ticket_id, data) VALUES (%s, %s)",
                    (response.ticket_id, Json(json.loads(response.model_dump_json()))),
                )
            return

        path = cls._path(response.ticket_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(response.model_dump_json() + "\n")

    @classmethod
    def load(cls, ticket_id: str) -> List[AgentResponse]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM agent_history WHERE ticket_id = %s ORDER BY id ASC",
                    (ticket_id,),
                )
                rows = cur.fetchall()
            return [AgentResponse(**r[0]) for r in rows]

        path = cls._path(ticket_id)
        if not path.exists():
            return []
        entries: List[AgentResponse] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(AgentResponse(**json.loads(line)))
                except Exception:
                    pass
        return entries

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ticket_id, MAX(id) AS last_id
                    FROM agent_history
                    GROUP BY ticket_id
                    ORDER BY last_id DESC
                    """
                )
                ticket_ids = [r[0] for r in cur.fetchall()]
            result = []
            for ticket_id in ticket_ids:
                entries = cls.load(ticket_id)
                if entries:
                    last = entries[-1]
                    result.append({
                        "ticket_id": last.ticket_id,
                        "last_agent": last.agent,
                        "last_scope": last.scope,
                        "last_timestamp": last.timestamp,
                        "total_interactions": len(entries),
                    })
            return result

        if not _HISTORY_DIR.exists():
            return []
        result = []
        for f in sorted(_HISTORY_DIR.glob("*.jsonl"), reverse=True):
            entries = cls.load(f.stem)
            if entries:
                last = entries[-1]
                result.append({
                    "ticket_id": last.ticket_id,
                    "last_agent": last.agent,
                    "last_scope": last.scope,
                    "last_timestamp": last.timestamp,
                    "total_interactions": len(entries),
                })
        return result


# ---------------------------------------------------------------------------
# WPRepro Agent — pending fix pipeline
#
# When an agent suggests `wp ...` commands and/or a PHP snippet in
# fix_sugerido, stage them as a pending fix (api/fixes/pending/{ticket_id}.json)
# and — unless FIX_AUTO_APPROVE=true — wait for a human to approve via
# POST /fixes/approve/{ticket_id} before anything runs against the live
# WordPress site (site_context.url).
# ---------------------------------------------------------------------------

_WP_CLI_LINE = re.compile(r"^(?:\$\s*)?(wp\s+.+)$")
_PHP_FENCE = re.compile(r"```php\s*\n([\s\S]*?)```", re.IGNORECASE)
_GENERIC_FENCE = re.compile(r"```(?:\w+)?\s*\n([\s\S]*?)```")
_PHP_HINT = re.compile(r"add_action\(|add_filter\(|function\s+\w+\s*\(|<\?php|update_option\(|wp_enqueue")

# Apache / .htaccess directives — never valid as eval()'d PHP.
_HTACCESS_DIRECTIVE = re.compile(
    r"^\s*(?:RewriteEngine|RewriteCond|RewriteRule|RewriteBase|<IfModule|</IfModule|"
    r"Options|AddType|AddHandler|ExpiresActive|ExpiresByType|FileETag|"
    r"Header\s+(?:set|always|append|unset|edit)|<Files|</Files|<FilesMatch|</FilesMatch|"
    r"Order\s|Allow\s|Deny\s|Require\s|ErrorDocument)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Recognizable WordPress/PHP function calls expected in a real fix snippet.
_PHP_FUNCTION_CALL = re.compile(
    r"\b(?:add_action|add_filter|remove_action|remove_filter|do_action|apply_filters|"
    r"update_option|add_option|delete_option|update_post_meta|get_post_meta|"
    r"register_activation_hook|register_deactivation_hook|wp_enqueue_(?:script|style)|"
    r"wp_redirect|wp_die)\s*\(|function\s+\w+\s*\("
)

_PHP_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_HTML_TAG = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^<>]*)?>")
_HTML_ENTITY = re.compile(r"&[a-zA-Z#]\w*;")
# Spanish accents / ¿¡ outside of strings indicate prose, not PHP (identifiers are ASCII-only).
_NON_PHP_PROSE = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")


def _extract_wp_cli_commands(fix_sugerido: Optional[str]) -> List[str]:
    """Pull standalone `wp ...` command lines out of fix_sugerido."""
    if not fix_sugerido:
        return []
    commands: List[str] = []
    for line in fix_sugerido.splitlines():
        cleaned = line.strip().strip("`").strip()
        match = _WP_CLI_LINE.match(cleaned)
        if match:
            commands.append(match.group(1).strip())
    return commands


def _strip_php_tags(code: str) -> str:
    code = re.sub(r"^\s*<\?php\s*", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"\?>\s*$", "", code.strip())
    return code.strip()


def _is_safe_php_snippet(code: str) -> bool:
    """Heuristic check: is `code` a standalone PHP snippet safe to stage as a
    wprepro_fix and eval() on the live site?

    Rejects prose, HTML markup, and Apache/.htaccess directives — content
    that would throw a syntax error (or worse) when eval()'d as PHP.
    """
    if not code or not code.strip():
        return False

    if _HTACCESS_DIRECTIVE.search(code):
        return False

    # A leftover '<?php' / '?>' means the snippet mixes multiple PHP blocks
    # or HTML — eval() expects pure PHP statements without tag delimiters.
    if "<?php" in code.lower() or "?>" in code:
        return False

    skeleton = _PHP_STRING_LITERAL.sub("", code)

    # HTML tags/entities outside of quoted strings indicate raw markup mixed
    # into the snippet (e.g. echoed HTML without proper quoting).
    if _HTML_TAG.search(skeleton) or _HTML_ENTITY.search(skeleton):
        return False

    # Spanish prose leaking into fix_sugerido (PHP identifiers are ASCII-only).
    if _NON_PHP_PROSE.search(skeleton):
        return False

    # Must contain at least one recognizable WordPress/PHP function call.
    if not _PHP_FUNCTION_CALL.search(code):
        return False

    return True


def _extract_php_snippet(fix_sugerido: Optional[str]) -> Optional[str]:
    """Pull a PHP code snippet out of fix_sugerido, if present."""
    if not fix_sugerido:
        return None

    match = _PHP_FENCE.search(fix_sugerido)
    if match:
        return _strip_php_tags(match.group(1))

    match = _GENERIC_FENCE.search(fix_sugerido)
    if match and _PHP_HINT.search(match.group(1)):
        return _strip_php_tags(match.group(1))

    if "<?php" in fix_sugerido:
        return _strip_php_tags(fix_sugerido[fix_sugerido.index("<?php"):])

    if _PHP_HINT.search(fix_sugerido) and not _extract_wp_cli_commands(fix_sugerido):
        code = _strip_php_tags(fix_sugerido)
        return code if _is_safe_php_snippet(code) else None

    return None


# ---------------------------------------------------------------------------
# PendingFixStore — one JSON file per ticket under api/fixes/pending/
# ---------------------------------------------------------------------------

class PendingFixStore:
    @staticmethod
    def _path(ticket_id: str) -> Path:
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        return _PENDING_DIR / f"{ticket_id}.json"

    @classmethod
    def save(cls, ticket_id: str, record: Dict[str, Any]) -> Path:
        if db.is_configured():
            from psycopg.types.json import Json

            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pending_fixes (ticket_id, data)
                    VALUES (%s, %s)
                    ON CONFLICT (ticket_id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (ticket_id, Json(record)),
                )
            return Path(f"{ticket_id}.json")

        path = cls._path(ticket_id)
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def get(cls, ticket_id: str) -> Optional[Dict[str, Any]]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM pending_fixes WHERE ticket_id = %s", (ticket_id,))
                row = cur.fetchone()
            return row[0] if row else None

        path = cls._path(ticket_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def delete(cls, ticket_id: str) -> bool:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM pending_fixes WHERE ticket_id = %s", (ticket_id,))
                return cur.rowcount > 0

        path = cls._path(ticket_id)
        if path.exists():
            path.unlink()
            return True
        return False

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        if db.is_configured():
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT data FROM pending_fixes ORDER BY ticket_id ASC")
                return [r[0] for r in cur.fetchall()]

        if not _PENDING_DIR.exists():
            return []
        result: List[Dict[str, Any]] = []
        for f in sorted(_PENDING_DIR.glob("*.json")):
            try:
                result.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        return result


def _build_pending_fix(response: AgentResponse, ticket: Ticket, site_context: SiteContext) -> None:
    """Stage wp-cli commands / a PHP snippet from fix_sugerido as a pending fix.

    Nothing runs against the live site until /fixes/approve/{ticket_id} is
    called, unless FIX_AUTO_APPROVE=true.
    """
    commands = _extract_wp_cli_commands(response.fix_sugerido)
    php_snippet = _extract_php_snippet(response.fix_sugerido)

    # Final safety net before staging the snippet for eval() on the live site
    # (covers snippets extracted from ```php fences, not just the fallback).
    if php_snippet and not _is_safe_php_snippet(php_snippet):
        php_snippet = None

    if not commands and not php_snippet:
        return

    site_url = site_context.url
    api_key = resolve_api_key(site_context.project_id)
    auto_approve = os.getenv("FIX_AUTO_APPROVE", "false").strip().lower() == "true"

    record: Dict[str, Any] = {
        "ticket_id": ticket.id,
        "categoria": str(ticket.categoria).split(".")[-1],
        "agent": response.agent,
        "titulo": ticket.titulo,
        "wp_cli_commands": commands,
        "php_snippet": php_snippet,
        "site_url": site_url,
        "project_id": site_context.project_id,
        "snippet_id": None,
        "snippet_status": None,
        "auto_approve": auto_approve,
        "status": "pending",
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "applied_at": None,
        "approval_results": None,
    }

    if not site_url or not api_key:
        record["status"] = "error"
        record["error"] = "site_context.url / WPREPRO_API_KEY no configurados"
        PendingFixStore.save(ticket.id, record)
        response.pending_fix = PendingFix(**record)
        return

    client = WPAgentClient(site_url, api_key)
    try:
        if php_snippet:
            data = client.execute_snippet({
                "action": "create",
                "ticket_id": ticket.id,
                "title": f"WPRecover Fix {ticket.id} ({response.agent})",
                "code": php_snippet,
                "auto_approve": auto_approve,
            })
            record["snippet_id"] = data.get("snippet_id")
            record["snippet_status"] = data.get("status")

        if auto_approve:
            results: Dict[str, Any] = {}
            if commands:
                wp_cli = client.execute(commands)
                results["wp_cli"] = wp_cli.get("results", [])
            if record["snippet_id"] is not None:
                results["snippet"] = {
                    "snippet_id": record["snippet_id"],
                    "status": record["snippet_status"],
                }
            record["status"] = "applied"
            record["applied_at"] = datetime.now(timezone.utc).isoformat()
            record["approval_results"] = results
    except Exception as exc:
        record["status"] = "error"
        record["error"] = str(exc)

    PendingFixStore.save(ticket.id, record)
    response.pending_fix = PendingFix(**record)


# ---------------------------------------------------------------------------
# AgentOrchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    @classmethod
    def run_for_ticket(
        cls,
        ticket: Ticket,
        site_context: SiteContext,
        historial: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResponse:
        agent = SCOPE_TO_AGENT.get(str(ticket.categoria).split(".")[-1])
        if not agent:
            raise ValueError(
                f"No agent configured for category '{ticket.categoria}'. "
                f"Available scopes: {list(SCOPE_TO_AGENT.keys())}"
            )

        check_name = _seo_check_name(ticket)
        validate = None
        if check_name in AUTO_RESOLVABLE_SEO_CHECKS:
            if site_context.url:
                enrichment = SEOContextEnricher.enrich(site_context.url)
                site_context = site_context.model_copy(update=enrichment)
            validate = lambda parsed: _validate_seo_fix(check_name, site_context, parsed)  # noqa: E731

        response = agent.run(ticket, site_context, historial or [], validate=validate)
        _build_pending_fix(response, ticket, site_context)
        AgentHistoryStore.append(response)
        return response

    @classmethod
    def batch(
        cls,
        tickets: List[Ticket],
        site_context: SiteContext,
        historial: Optional[List[Dict[str, Any]]] = None,
    ) -> List[AgentResponse]:
        responses: List[AgentResponse] = []
        for ticket in tickets:
            try:
                responses.append(cls.run_for_ticket(ticket, site_context, historial))
            except Exception as exc:
                responses.append(
                    AgentResponse(
                        agent="ErrorAgent",
                        scope=str(ticket.categoria),
                        ticket_id=ticket.id,
                        recomendaciones=[f"Error procesando ticket: {exc}"],
                        fix_sugerido=None,
                        mensaje_cliente="No se pudo procesar este ticket automáticamente.",
                        prioridad=str(ticket.prioridad),
                        estimacion_impacto="N/A",
                        tokens_used=0,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
        return responses
