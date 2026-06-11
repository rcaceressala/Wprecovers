from __future__ import annotations

from typing import Any, Dict, List

import httpx

TIMEOUT = 30.0


class WPAgentClient:
    """Sync HTTP client for the WPRepro Agent WordPress plugin.

    Talks to https://{site}/wp-json/wprepro/v1/* using the X-WPRepro-Key
    header expected by the plugin's auth layer.
    """

    def __init__(self, site_url: str, api_key: str):
        self.site_url = site_url.rstrip("/")
        self.headers = {
            "X-WPRepro-Key": api_key,
            "Content-Type": "application/json",
        }

    def execute(self, commands: List[str]) -> Dict[str, Any]:
        """POST /wp-json/wprepro/v1/execute — run whitelisted WP-CLI commands."""
        url = f"{self.site_url}/wp-json/wprepro/v1/execute"
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(url, headers=self.headers, json={"commands": commands})
            r.raise_for_status()
            return r.json()

    def execute_snippet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /wp-json/wprepro/v1/execute-snippet — create/activate/delete a fix snippet."""
        url = f"{self.site_url}/wp-json/wprepro/v1/execute-snippet"
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(url, headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()
