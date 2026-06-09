import httpx
from typing import Optional

TIMEOUT = 30


class WPAgentClient:
    """Cliente HTTP para comunicarse con el plugin WPRepro Agent."""

    def __init__(self, site_url: str, api_key: str):
        self.site_url = site_url.rstrip("/")
        self.headers = {
            "X-WPRepro-Key": api_key,
            "Content-Type": "application/json",
        }

    async def _get(self, endpoint: str) -> dict:
        url = f"{self.site_url}/wp-json/wprepro/v1/{endpoint}"
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=False) as client:
            r = await client.get(url, headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def _post(self, endpoint: str, body: dict = {}) -> dict:
        url = f"{self.site_url}/wp-json/wprepro/v1/{endpoint}"
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=False) as client:
            r = await client.post(url, headers=self.headers, json=body)
            r.raise_for_status()
            return r.json()

    async def get_status(self) -> dict:
        return await self._get("status")

    async def fix_images(self) -> dict:
        return await self._post("fix/images")

    async def fix_cache(self) -> dict:
        return await self._post("fix/cache")

    async def fix_security(self) -> dict:
        return await self._post("fix/security")

    async def fix_database(self) -> dict:
        return await self._post("fix/database")

    async def fix_vitals(self) -> dict:
        return await self._post("fix/vitals")

    async def fix_all(self) -> dict:
        return await self._post("fix/all")

    async def fix_plugins(self, action: str, plugins: list) -> dict:
        return await self._post("fix/plugins", {"action": action, "plugins": plugins})
