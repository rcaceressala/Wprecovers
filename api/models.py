from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Categoria(str, Enum):
    SEO = "SEO"
    Performance = "Performance"
    Conversion = "Conversion"
    Seguridad = "Seguridad"
    WooCommerce = "WooCommerce"


class Prioridad(str, Enum):
    Critica = "Critica"
    Alta = "Alta"
    Media = "Media"
    Baja = "Baja"


class EstadoTicket(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAIL = "FAIL"


class Ticket(BaseModel):
    id: str
    categoria: Categoria
    titulo: str
    prioridad: Prioridad
    impacto: str
    agente: str
    estimacion: int = Field(..., description="Estimated fix time in minutes")
    dependencias: List[str] = []
    estado: EstadoTicket = EstadoTicket.OPEN


class AuditInput(BaseModel):
    checks: Dict[str, Dict[str, bool]] = Field(
        ...,
        description="Map of category → check_name → passed (true) / failed (false)",
        example={
            "SEO": {"title": False, "meta_desc": False, "canonical": True},
            "Performance": {"LCP": False, "CLS": True},
            "Conversion": {"tel_clickeable": False, "whatsapp": False},
            "Seguridad": {"ssl": True, "headers": False},
            "WooCommerce": {"pasarelas": True, "productos_sin_img": False},
        },
    )
    errores: List[str] = Field(
        default=[],
        description="Critical site errors: sitio_caido | error_500 | checkout_roto",
    )
    recovery_score: float = Field(..., ge=0, le=100)
    url: Optional[str] = None


class TicketSummary(BaseModel):
    total: int
    criticos: int
    altos: int
    medios: int
    bajos: int
    estimacion_total_min: int


class TicketResponse(BaseModel):
    url: Optional[str]
    recovery_score: float
    resumen: TicketSummary
    tickets: List[Ticket]
    checks: Optional[Dict[str, Dict[str, bool]]] = Field(
        default=None,
        description="Raw category -> check_name -> passed map from the audit. "
                    "Used to build SiteMetrics for /report endpoints.",
    )
    pagespeed_score: Optional[float] = Field(
        default=None,
        description="PageSpeed Insights performance score (0-100), if available.",
    )


# ---------------------------------------------------------------------------
# M3 — QA Automático models
# ---------------------------------------------------------------------------

class SiteMetrics(BaseModel):
    pagespeed_score: float = Field(..., ge=0, le=100, description="PageSpeed Insights score 0–100")
    recovery_score: float = Field(..., ge=0, le=100, description="WPRecover composite score")
    checks: Dict[str, Dict[str, bool]] = Field(
        ..., description="category → check_name → passed"
    )


class FixApplied(BaseModel):
    metodo: Literal["WP-CLI", "functions.php", "plugin_wprecover", "manual"] = "manual"
    descripcion: str
    archivos_modificados: List[str] = []


class DeltaMetrics(BaseModel):
    recovery_score_delta: float
    pagespeed_score_delta: float
    checks_fixed: int
    checks_regressed: int
    improvement_pct: float


class QARecord(BaseModel):
    ticket_id: str
    categoria: str
    timestamp: str
    baseline: SiteMetrics
    post_fix: SiteMetrics
    fix_applied: FixApplied
    resultado: Literal["PASS", "FAIL"]
    delta_metrics: DeltaMetrics
    time_elapsed_sec: float


class ValidateInput(BaseModel):
    post_fix_metrics: SiteMetrics
    fix_applied: FixApplied
    categoria: str = Field(default="SEO", description="Ticket category for the evidence record")


# ---------------------------------------------------------------------------
# M4 — Motor de Correcciones models
# ---------------------------------------------------------------------------

class FixMethod(str, Enum):
    WP_CLI = "WP-CLI"
    FUNCTIONS_PHP = "functions.php"
    PLUGIN_WPRECOVER = "plugin_wprecover"
    MANUAL = "manual"


class FixStatus(str, Enum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class FixPayload(BaseModel):
    command: Optional[str] = None
    php_snippet: Optional[str] = None
    file_target: Optional[str] = None


class FixApplyRequest(BaseModel):
    check_name: str = Field(..., description="Check key from FIX_CATALOG e.g. 'meta_generator'")
    categoria: str = Field(..., description="SEO | Conversion | Contenido")
    metodo: FixMethod = FixMethod.WP_CLI
    staging_url: str = Field(..., description="Required: must be a staging/dev URL, never production")
    prioridad: str = Field(default="Alta", description="Ticket priority — Critica requires approved_by")
    approved_by: Optional[str] = Field(None, description="Required for Critica tickets")
    params: Dict[str, str] = Field(default_factory=dict, description="Template params e.g. {phone: '123'}")


class FixLogEntry(BaseModel):
    ticket_id: str
    check_name: str
    categoria: str
    metodo: str
    staging_url: str
    timestamp: str
    status: FixStatus
    fix_payload: Optional[FixPayload] = None
    rollback_payload: Optional[FixPayload] = None
    riesgo: str
    requires_approval: bool
    approved_by: Optional[str] = None
    error: Optional[str] = None


class FixResult(BaseModel):
    ticket_id: str
    check_name: str
    status: FixStatus
    fix_payload: Optional[FixPayload]
    rollback_payload: Optional[FixPayload]
    riesgo: str
    requires_approval: bool
    log_file: str
    timestamp: str


class RollbackRequest(BaseModel):
    reason: str = "Manual rollback requested"


# ---------------------------------------------------------------------------
# M5 — Reportes Ejecutivos models
# ---------------------------------------------------------------------------

class ChartData(BaseModel):
    labels: List[str]
    before: List[float]
    after: List[float]
    weights: List[float]


class ClientReportSection(BaseModel):
    categoria: str
    nombre_simple: str
    descripcion: str
    score_antes: float
    score_despues: float
    delta: float
    checks_arreglados: List[str]


class GuaranteeResult(BaseModel):
    guarantee_met: bool
    improvement_points: float
    improvement_pct: float
    threshold: float
    score_before: float
    score_after: float


class ReportRequest(BaseModel):
    client_name: str
    site_url: str
    client_logo_url: Optional[str] = None
    baseline: SiteMetrics
    post_fix: SiteMetrics
    tickets_completados: List[str] = Field(default_factory=list)
    notas: Optional[str] = None


class ReportRecord(BaseModel):
    ticket_id: str
    client_name: str
    site_url: str
    timestamp: str
    score_before: float
    score_after: float
    improvement_points: float
    improvement_pct: float
    guarantee_met: bool
    guarantee_threshold: float
    pdf_path: Optional[str]
    per_category_before: Dict[str, float]
    per_category_after: Dict[str, float]
    checks_fixed_labels: List[str]
    checks_regressed_labels: List[str]
    chart_data: ChartData
    client_sections: List[ClientReportSection]
    notas: Optional[str]


# ---------------------------------------------------------------------------
# M6 — Agentes IA models
# ---------------------------------------------------------------------------

class SiteContext(BaseModel):
    url: str
    platform: str = "WordPress"
    recovery_score: Optional[float] = None
    pagespeed_score: Optional[float] = None
    sector: Optional[str] = None
    notas: Optional[str] = None


class PendingFix(BaseModel):
    ticket_id: str
    categoria: str
    agent: str
    titulo: str
    wp_cli_commands: List[str] = Field(default_factory=list)
    php_snippet: Optional[str] = None
    site_url: str
    snippet_id: Optional[int] = None
    snippet_status: Optional[str] = None
    auto_approve: bool = False
    status: Literal["pending", "applied", "error"] = "pending"
    error: Optional[str] = None
    created_at: str
    applied_at: Optional[str] = None
    approval_results: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    agent: str
    scope: str
    ticket_id: str
    recomendaciones: List[str]
    fix_sugerido: Optional[str] = None
    mensaje_cliente: str
    prioridad: str
    estimacion_impacto: str = ""
    tokens_used: int = 0
    timestamp: str
    pending_fix: Optional[PendingFix] = None


class AgentRunRequest(BaseModel):
    ticket: Ticket
    site_context: SiteContext
    historial: List[Dict[str, Any]] = Field(default_factory=list)


class BatchRunRequest(BaseModel):
    tickets: List[Ticket]
    site_context: SiteContext
    historial: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# M8 — Billing models
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    client_id: str
    success_url: str = "http://localhost:3000/billing/success"
    cancel_url: str = "http://localhost:3000/billing/cancel"


class ClientSubscription(BaseModel):
    client_id: str
    plan: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_subscription_item_id: Optional[str] = None
    status: str = "active"  # active | canceled | past_due
    created_at: str
    updated_at: str


class UsageRecord(BaseModel):
    client_id: str
    period: str  # YYYY-MM
    audits_used: int = 0
    fixes_used: int = 0
    agents_used: int = 0
    reports_used: int = 0
    last_updated: str


class UpgradeRequest(BaseModel):
    new_plan: str = Field(..., description="Target plan: starter | growth | scale | elite")
