from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models import (
    FixApplyRequest,
    FixLogEntry,
    FixMethod,
    FixPayload,
    FixResult,
    FixStatus,
)

FIXES_DIR = Path(__file__).parent / "fixes"
_LOGS_DIR = FIXES_DIR / "logs"
_STATE_DIR = FIXES_DIR / "state"

# ---------------------------------------------------------------------------
# Fix catalog — derived from wprecover.modules.json M4.fixes_permitidos
# Keys match check_names from ticket_engine.CHECK_CONFIG + Contenido extras.
# Each entry: fix[metodo] → command/snippet, rollback[metodo] → undo command
# ---------------------------------------------------------------------------

FIX_CATALOG: Dict[str, Dict[str, Any]] = {
    "SEO": {
        "meta_generator": {
            "titulo": "Remove WordPress version from meta generator tag",
            "fix": {
                FixMethod.FUNCTIONS_PHP: "add_filter('the_generator', '__return_empty_string');",
            },
            "rollback": {
                FixMethod.FUNCTIONS_PHP: "// Remove: add_filter('the_generator', '__return_empty_string');",
            },
            "riesgo": "Baja",
        },
        "sitemap": {
            "titulo": "Generate XML sitemap",
            "fix": {
                FixMethod.WP_CLI: "wp yoast sitemap generate",
                FixMethod.PLUGIN_WPRECOVER: "wprecover_generate_sitemap()",
            },
            "rollback": {
                FixMethod.WP_CLI: "wp yoast sitemap delete",
            },
            "riesgo": "Baja",
        },
        "robots": {
            "titulo": "Enable indexing via robots.txt",
            "fix": {
                FixMethod.WP_CLI: "wp option update blog_public 1 && wp rewrite flush",
                FixMethod.MANUAL: "Dashboard → Settings → Reading → uncheck 'Discourage search engines'",
            },
            "rollback": {
                FixMethod.WP_CLI: "wp option update blog_public 0",
            },
            "riesgo": "Media",
        },
        "canonicals": {
            "titulo": "Inject canonical tags on all pages",
            "fix": {
                FixMethod.FUNCTIONS_PHP: (
                    "add_action('wp_head', function() {\n"
                    "    if (!is_404()) {\n"
                    "        echo '<link rel=\"canonical\" href=\"' . esc_url(get_permalink()) . '\" />';\n"
                    "    }\n"
                    "});"
                ),
            },
            "rollback": {
                FixMethod.FUNCTIONS_PHP: "// Remove the canonical add_action block added by WPRecover",
            },
            "riesgo": "Baja",
        },
    },
    "Conversion": {
        "tel_clickeable": {
            "titulo": "Wrap phone numbers in tel: links",
            "fix": {
                FixMethod.FUNCTIONS_PHP: (
                    "add_filter('the_content', 'wpr_wrap_phones');\n"
                    "function wpr_wrap_phones($c) {\n"
                    "    return preg_replace(\n"
                    "        '/\\b(\\+?[\\d][\\d\\s\\-\\.\\(\\)]{7,})/',\n"
                    "        '<a href=\"tel:$1\">$1</a>',\n"
                    "        $c\n"
                    "    );\n"
                    "}"
                ),
            },
            "rollback": {
                FixMethod.FUNCTIONS_PHP: "// Remove wpr_wrap_phones filter and function",
            },
            "riesgo": "Baja",
        },
        "CTA": {
            "titulo": "Add sticky CTA button in footer",
            "fix": {
                FixMethod.FUNCTIONS_PHP: (
                    "add_action('wp_footer', 'wpr_sticky_cta');\n"
                    "function wpr_sticky_cta() {\n"
                    "    echo '<div style=\"position:fixed;bottom:20px;right:20px;z-index:9999;\">"
                    "<a href=\"#contact\" class=\"button wpr-cta\">Cont\\u00e1ctanos</a></div>';\n"
                    "}"
                ),
            },
            "rollback": {
                FixMethod.FUNCTIONS_PHP: "// Remove wpr_sticky_cta action and function",
            },
            "riesgo": "Baja",
        },
        "whatsapp": {
            "titulo": "Add WhatsApp floating button",
            "fix": {
                FixMethod.PLUGIN_WPRECOVER: "wprecover_enable_whatsapp_button('{phone}')",
                FixMethod.FUNCTIONS_PHP: (
                    "add_action('wp_footer', 'wpr_whatsapp_btn');\n"
                    "function wpr_whatsapp_btn() {\n"
                    "    $n = get_option('wpr_whatsapp', '{phone}');\n"
                    "    if ($n) echo '<a href=\"https://wa.me/'.esc_attr($n).'\" target=\"_blank\"\n"
                    "        style=\"position:fixed;bottom:80px;right:20px;z-index:9999;\">\n"
                    "        <img src=\"https://cdn.simpleicons.org/whatsapp/25D366\" width=\"50\" alt=\"WhatsApp\"/></a>';\n"
                    "}"
                ),
            },
            "rollback": {
                FixMethod.FUNCTIONS_PHP: "// Remove wpr_whatsapp_btn action and function",
                FixMethod.PLUGIN_WPRECOVER: "wprecover_disable_whatsapp_button()",
            },
            "riesgo": "Baja",
        },
    },
    "Contenido": {
        "links_rotos": {
            "titulo": "Audit broken links",
            "fix": {
                FixMethod.WP_CLI: (
                    "wp post list --post_type=post,page --format=ids | "
                    "xargs -n1 wp broken-link-checker"
                ),
            },
            "rollback": None,
            "riesgo": "Baja",
        },
        "301_redirects": {
            "titulo": "Add 301 redirect for migrated URL",
            "fix": {
                FixMethod.WP_CLI: (
                    "wp redirection add --url='{old_path}' "
                    "--action-url='{new_path}' --action-type=url --status=301"
                ),
                FixMethod.MANUAL: "Add 'Redirect 301 {old_path} {new_path}' to .htaccess",
            },
            "rollback": {
                FixMethod.WP_CLI: "wp redirection delete --url='{old_path}'",
            },
            "riesgo": "Baja",
        },
    },
}

REQUIRES_HUMAN_APPROVAL = {"Critica"}

STAGING_SIGNALS = ["staging", "dev.", "test.", "local", "localhost", "preview", ".local", "wprecover"]


# ---------------------------------------------------------------------------
# StagingGuard
# ---------------------------------------------------------------------------

class StagingGuard:
    """Enforces M4 constraints: staging_obligatorio + aprobacion_humana_criticos."""

    @staticmethod
    def validate_url(staging_url: str) -> Tuple[bool, str]:
        url = staging_url.lower()
        if not url.startswith(("http://", "https://")):
            return False, "staging_url must begin with http:// or https://"
        if not any(s in url for s in STAGING_SIGNALS):
            return False, (
                f"'{staging_url}' does not look like a staging environment. "
                f"URL must contain one of: {', '.join(STAGING_SIGNALS)}"
            )
        return True, "ok"

    @staticmethod
    def requires_approval(prioridad: str) -> bool:
        return prioridad in REQUIRES_HUMAN_APPROVAL


# ---------------------------------------------------------------------------
# FixPayloadBuilder
# ---------------------------------------------------------------------------

def _fill(template: str, params: Dict[str, str]) -> str:
    for k, v in params.items():
        template = template.replace(f"{{{k}}}", v)
    return template


class FixPayloadBuilder:
    """Resolves fix + rollback payloads from FIX_CATALOG for a given check/method."""

    @classmethod
    def build(
        cls,
        categoria: str,
        check_name: str,
        metodo: FixMethod,
        params: Dict[str, str],
    ) -> Tuple[Optional[FixPayload], Optional[FixPayload], str]:
        entry = FIX_CATALOG.get(categoria, {}).get(check_name)
        if not entry:
            return None, None, "Baja"

        fix_map = entry["fix"]
        rollback_map = entry.get("rollback") or {}
        riesgo: str = entry.get("riesgo", "Baja")

        # Pick requested method if available, else fall back to first available
        chosen = metodo if (metodo in fix_map and fix_map[metodo]) else next(
            (m for m in fix_map if fix_map[m]), None
        )
        if not chosen:
            return None, None, riesgo

        fix_payload = cls._build_payload(chosen, _fill(fix_map[chosen], params))

        rollback_payload = None
        if rollback_map:
            rb_method = chosen if chosen in rollback_map else next(iter(rollback_map), None)
            if rb_method and rollback_map[rb_method]:
                rollback_payload = cls._build_payload(
                    rb_method, _fill(rollback_map[rb_method], params)
                )

        return fix_payload, rollback_payload, riesgo

    @staticmethod
    def _build_payload(metodo: Any, content: str) -> FixPayload:
        if metodo in (FixMethod.FUNCTIONS_PHP, FixMethod.PLUGIN_WPRECOVER):
            return FixPayload(php_snippet=content, file_target="functions.php")
        return FixPayload(command=content)


# ---------------------------------------------------------------------------
# RollbackManager
# ---------------------------------------------------------------------------

class RollbackManager:
    """Persists the most recent applied-fix state per ticket for rollback."""

    @staticmethod
    def _path(ticket_id: str) -> Path:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        return _STATE_DIR / f"{ticket_id}.json"

    @classmethod
    def save(cls, entry: FixLogEntry) -> None:
        cls._path(entry.ticket_id).write_text(
            entry.model_dump_json(indent=2), encoding="utf-8"
        )

    @classmethod
    def get(cls, ticket_id: str) -> Optional[FixLogEntry]:
        path = cls._path(ticket_id)
        if not path.exists():
            return None
        return FixLogEntry(**json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def mark_rolled_back(cls, ticket_id: str) -> None:
        path = cls._path(ticket_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = FixStatus.ROLLED_BACK
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# FixLog
# ---------------------------------------------------------------------------

class FixLog:
    """Append-only JSONL audit log per ticket."""

    @staticmethod
    def _path(ticket_id: str) -> Path:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        return _LOGS_DIR / f"{ticket_id}.jsonl"

    @classmethod
    def append(cls, entry: FixLogEntry) -> Path:
        path = cls._path(entry.ticket_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")
        return path

    @classmethod
    def read(cls, ticket_id: str) -> List[FixLogEntry]:
        path = cls._path(ticket_id)
        if not path.exists():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(FixLogEntry(**json.loads(line)))
                except Exception:
                    pass
        return entries

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        if not _LOGS_DIR.exists():
            return []
        result = []
        for f in sorted(_LOGS_DIR.glob("*.jsonl"), reverse=True):
            entries = cls.read(f.stem)
            if entries:
                last = entries[-1]
                result.append(
                    {
                        "ticket_id": last.ticket_id,
                        "check_name": last.check_name,
                        "categoria": last.categoria,
                        "status": last.status,
                        "timestamp": last.timestamp,
                        "total_operations": len(entries),
                    }
                )
        return result


# ---------------------------------------------------------------------------
# FixEngine
# ---------------------------------------------------------------------------

class FixEngine:
    """
    Orchestrates M4 fix application with staging guard, rollback, and audit log.

    M4 constraints (wprecover.modules.json):
      - staging_obligatorio      : staging_url must be a non-production environment
      - aprobacion_humana_criticos: Critica tickets require approved_by
    """

    @classmethod
    def apply(cls, ticket_id: str, req: FixApplyRequest) -> FixResult:
        # Constraint 1: staging URL required
        ok, msg = StagingGuard.validate_url(req.staging_url)
        if not ok:
            raise ValueError(f"staging_guard: {msg}")

        # Constraint 2: Critica tickets need human sign-off
        needs_approval = StagingGuard.requires_approval(req.prioridad)
        if needs_approval and not req.approved_by:
            raise ValueError(
                f"aprobacion_humana_criticos: ticket {ticket_id} has priority "
                f"'{req.prioridad}' — approved_by is required."
            )

        fix_payload, rollback_payload, riesgo = FixPayloadBuilder.build(
            req.categoria, req.check_name, req.metodo, req.params
        )

        ts = datetime.now(timezone.utc).isoformat()
        status = FixStatus.APPLIED if fix_payload else FixStatus.FAILED
        error = (
            f"No fix found for {req.categoria}/{req.check_name} via {req.metodo}"
            if not fix_payload
            else None
        )

        entry = FixLogEntry(
            ticket_id=ticket_id,
            check_name=req.check_name,
            categoria=req.categoria,
            metodo=req.metodo,
            staging_url=req.staging_url,
            timestamp=ts,
            status=status,
            fix_payload=fix_payload,
            rollback_payload=rollback_payload,
            riesgo=riesgo,
            requires_approval=needs_approval,
            approved_by=req.approved_by,
            error=error,
        )

        log_path = FixLog.append(entry)
        if status == FixStatus.APPLIED:
            RollbackManager.save(entry)

        return FixResult(
            ticket_id=ticket_id,
            check_name=req.check_name,
            status=status,
            fix_payload=fix_payload,
            rollback_payload=rollback_payload,
            riesgo=riesgo,
            requires_approval=needs_approval,
            log_file=log_path.name,
            timestamp=ts,
        )

    @classmethod
    def rollback(cls, ticket_id: str, reason: str) -> Dict[str, Any]:
        state = RollbackManager.get(ticket_id)
        if not state:
            raise ValueError(f"No applied fix found for ticket '{ticket_id}'")
        if state.status == FixStatus.ROLLED_BACK:
            raise ValueError(f"Ticket '{ticket_id}' has already been rolled back")

        ts = datetime.now(timezone.utc).isoformat()

        rollback_entry = FixLogEntry(
            ticket_id=ticket_id,
            check_name=state.check_name,
            categoria=state.categoria,
            metodo=state.metodo,
            staging_url=state.staging_url,
            timestamp=ts,
            status=FixStatus.ROLLED_BACK,
            fix_payload=state.rollback_payload,
            rollback_payload=None,
            riesgo=state.riesgo,
            requires_approval=state.requires_approval,
            approved_by=state.approved_by,
            error=None,
        )

        FixLog.append(rollback_entry)
        RollbackManager.mark_rolled_back(ticket_id)

        return {
            "ticket_id": ticket_id,
            "status": FixStatus.ROLLED_BACK,
            "reason": reason,
            "rollback_payload": state.rollback_payload.model_dump() if state.rollback_payload else None,
            "timestamp": ts,
        }
