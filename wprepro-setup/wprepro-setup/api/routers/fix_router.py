from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.wp_agent_client import WPAgentClient

router = APIRouter(prefix="/api/fix", tags=["fixes"])

VALID_FIXES = ["images", "cache", "security", "database", "vitals", "all"]


class FixRequest(BaseModel):
    site_url: str
    api_key: str


@router.get("/status")
async def agent_status(site_url: str, api_key: str):
    """Verifica que el plugin WPRepro Agent está activo en el sitio."""
    client = WPAgentClient(site_url, api_key)
    try:
        return await client.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{fix_type}")
async def apply_fix(fix_type: str, req: FixRequest):
    """
    Aplica un fix remoto en el sitio WordPress.
    fix_type: images | cache | security | database | vitals | all
    """
    if fix_type not in VALID_FIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Fix '{fix_type}' no válido. Opciones: {VALID_FIXES}"
        )

    client = WPAgentClient(req.site_url, req.api_key)
    try:
        fn = getattr(client, f"fix_{fix_type}")
        result = await fn()
        return result
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error del plugin: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
