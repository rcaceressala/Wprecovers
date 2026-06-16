"""Sanity-check which WordPress project WPRecover/WPRepro Agent is wired to.

Compares WPREPRO_SITE_URL (the project the deployed agent will apply fixes
to) against a target site, and verifies the WPRepro Agent plugin is
installed and the API key works on that target.

Usage:
    python check_project.py https://globalklima.cl

Config source:
    By default reads api/.env via python-dotenv. If RENDER_API_KEY and
    RENDER_SERVICE_ID are set (env or .env), reads the live env vars from
    the deployed Render service instead via the Render API:
    https://api.render.com/v1/services/{service_id}/env-vars
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

# Windows consoles default stdout to cp1252, which can't encode the
# ✅/❌/⚠️ markers below — force UTF-8 so output doesn't crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ENV_PATH = Path(__file__).parent / ".env"
RENDER_API = "https://api.render.com/v1"
TIMEOUT = 15.0


def load_config() -> dict[str, str | None]:
    render_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")

    if render_key and service_id:
        try:
            return _load_from_render(render_key, service_id)
        except Exception as e:
            print(f"No se pudo leer la config desde la API de Render ({e}); usando .env local\n")

    return _load_from_dotenv()


def _load_from_render(render_key: str, service_id: str) -> dict[str, str | None]:
    url = f"{RENDER_API}/services/{service_id}/env-vars"
    headers = {"Authorization": f"Bearer {render_key}", "Accept": "application/json"}
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(url, headers=headers)
        r.raise_for_status()
        env_vars = {item["envVar"]["key"]: item["envVar"]["value"] for item in r.json()}
    return {
        "source": "Render API",
        "WPREPRO_SITE_URL": env_vars.get("WPREPRO_SITE_URL"),
        "WPREPRO_API_KEY": env_vars.get("WPREPRO_API_KEY"),
        "FIX_AUTO_APPROVE": env_vars.get("FIX_AUTO_APPROVE"),
    }


def _load_from_dotenv() -> dict[str, str | None]:
    load_dotenv(ENV_PATH, override=True)
    return {
        "source": f".env ({ENV_PATH})",
        "WPREPRO_SITE_URL": os.getenv("WPREPRO_SITE_URL"),
        "WPREPRO_API_KEY": os.getenv("WPREPRO_API_KEY"),
        "FIX_AUTO_APPROVE": os.getenv("FIX_AUTO_APPROVE"),
    }


def mask_key(key: str | None) -> str:
    if not key:
        return "(no configurada)"
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


def normalize_host(url: str) -> str:
    """Scheme/www/trailing-slash-insensitive host for comparison."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def check_plugin_installed(target_url: str) -> tuple[bool, str]:
    url = target_url.rstrip("/") + "/wp-json/wprepro/v1"
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(url)
        return r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def check_api_key(target_url: str, api_key: str | None) -> tuple[bool, str]:
    if not api_key:
        return False, "WPREPRO_API_KEY no configurada"
    url = target_url.rstrip("/") + "/wp-json/wprepro/v1/execute"
    headers = {"X-WPRepro-Key": api_key, "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            # "wp plugin status" is read-only — used purely as an auth ping.
            r = c.post(url, headers=headers, json={"commands": ["wp plugin status"]})
        if r.status_code == 200:
            return True, "HTTP 200"
        return False, f"HTTP {r.status_code} — {r.text[:160]}"
    except Exception as e:
        return False, str(e)


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python check_project.py <target_url>")
        sys.exit(1)

    target_url = sys.argv[1]
    if "://" not in target_url:
        target_url = "https://" + target_url

    config = load_config()
    site_url = config.get("WPREPRO_SITE_URL")
    api_key = config.get("WPREPRO_API_KEY")
    auto_approve = config.get("FIX_AUTO_APPROVE")

    print(f"Fuente de configuración: {config['source']}")
    print(f"WPREPRO_SITE_URL = {site_url or '(no configurada)'}")
    print(f"WPREPRO_API_KEY  = {mask_key(api_key)}")
    print(f"FIX_AUTO_APPROVE = {auto_approve or '(no configurada)'}")
    print()

    site_matches = bool(site_url) and normalize_host(site_url) == normalize_host(target_url)

    if not site_matches:
        print(f"⚠️ ADVERTENCIA: WPREPRO_SITE_URL apunta a {site_url or '(vacío)'}")
        print(f"Los fixes se aplicarán en {site_url or '(vacío)'}, no en {target_url}")
        print("Cambia la variable en Render antes de continuar")
        sys.exit(1)

    plugin_ok, plugin_detail = check_plugin_installed(target_url)
    if plugin_ok:
        key_ok, key_detail = check_api_key(target_url, api_key)
    else:
        key_ok, key_detail = False, "Plugin no disponible — omitido"

    print(f"PROYECTO ACTIVO: {target_url}")
    print(f"{'✅' if site_matches else '❌'} WPREPRO_SITE_URL coincide")
    print(f"{'✅' if plugin_ok else '❌'} Plugin instalado y respondiendo ({plugin_detail})")
    print(f"{'✅' if key_ok else '❌'} API Key válida ({key_detail})")
    print()

    if site_matches and plugin_ok and key_ok:
        print("LISTO PARA TRABAJAR EN ESTE PROYECTO")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
