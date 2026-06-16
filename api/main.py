from __future__ import annotations

# Trigger Render redeploy
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pydantic import BaseModel

from models import (
    AgentRunRequest,
    AuditInput,
    BatchRunRequest,
    CheckoutRequest,
    FixApplyRequest,
    Prioridad,
    ReportRequest,
    RollbackRequest,
    SiteMetrics,
    TicketResponse,
    TicketSummary,
    UpgradeRequest,
    ValidateInput,
)


class AuditRunRequest(BaseModel):
    url: str
from agents_engine import AgentHistoryStore, AgentOrchestrator, PendingFixStore, SCOPE_TO_AGENT
from audit_engine import run_full_audit
from billing_engine import PLANS, BillingService, SubscriptionStore, UsageTracker
from fix_engine import FIX_CATALOG, FixEngine, FixLog, RollbackManager
from qa_engine import BaselineCapture, EvidenceLogger, QARecord, QAReport, QAValidator
from report_engine import GuaranteeEvaluator, ReportStore, build_full_report
from ticket_engine import generate_tickets
from wp_agent_client import WPAgentClient

app = FastAPI(
    title="WPRecover API",
    description=(
        "M2 — Motor de Tickets  |  M3 — QA Automático  |  "
        "M4 — Motor de Correcciones  |  M5 — Reportes Ejecutivos  |  "
        "M6 — Agentes IA  |  M8 — Billing"
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "modules": [
        "M1 — Auditoría Real (PSI + HTML)",
        "M2 — Motor de Tickets",
        "M3 — QA Automático",
        "M4 — Motor de Correcciones",
        "M5 — Reportes Ejecutivos",
        "M6 — Agentes IA",
        "M8 — Billing",
    ]}


@app.get("/status", tags=["System"])
def status():
    return {"status": "ok", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# M1 — Real Site Audit
# ---------------------------------------------------------------------------

@app.post("/audit/run", response_model=TicketResponse, tags=["M1 Audit"])
async def run_audit(req: AuditRunRequest):
    """
    Full real-site audit: PageSpeed Insights + HTML analysis → tickets.

    Fetches PSI (mobile strategy) and HTML concurrently.
    Runs 31 checks across SEO / Performance / Conversion / Seguridad / WooCommerce,
    calculates the Recovery Score, and returns prioritized tickets.

    Falls back gracefully if PSI or HTML fetch fails.
    """
    try:
        return await run_full_audit(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {e}")


# ---------------------------------------------------------------------------
# M2 — Motor de Tickets
# ---------------------------------------------------------------------------

@app.post("/api/v1/tickets/generate", response_model=TicketResponse, tags=["M2 Tickets"])
def generate(audit: AuditInput):
    """
    Receives M1 audit output and returns prioritized tickets.

    Priority rules (wprecover.modules.json M2):
    - Critica : sitio_caido | error_500 | checkout_roto
    - Alta    : indexacion (SEO) | conversiones | seguridad
    - Media   : performance
    - Baja    : cosmético
    """
    tickets = generate_tickets(audit)

    summary = TicketSummary(
        total=len(tickets),
        criticos=sum(1 for t in tickets if t.prioridad == Prioridad.Critica),
        altos=sum(1 for t in tickets if t.prioridad == Prioridad.Alta),
        medios=sum(1 for t in tickets if t.prioridad == Prioridad.Media),
        bajos=sum(1 for t in tickets if t.prioridad == Prioridad.Baja),
        estimacion_total_min=sum(t.estimacion for t in tickets),
    )

    return TicketResponse(
        url=audit.url,
        recovery_score=audit.recovery_score,
        resumen=summary,
        tickets=tickets,
    )


# ---------------------------------------------------------------------------
# M3 — QA Automático
# ---------------------------------------------------------------------------

@app.post("/qa/baseline/{ticket_id}", tags=["M3 QA"])
def capture_baseline(ticket_id: str, metrics: SiteMetrics):
    """
    Capture site metrics BEFORE applying a fix.
    Must be called before /qa/validate/{ticket_id}.
    """
    record = BaselineCapture.capture(ticket_id, metrics)
    return {
        "ticket_id": ticket_id,
        "status": "baseline_captured",
        "timestamp": record["timestamp"],
        "recovery_score": metrics.recovery_score,
        "pagespeed_score": metrics.pagespeed_score,
    }


@app.post("/qa/validate/{ticket_id}", tags=["M3 QA"])
def validate(ticket_id: str, payload: ValidateInput):
    """
    Compare post-fix metrics against the stored baseline.
    Returns PASS if no regression; FAIL if recovery_score dropped.
    Persists an evidence JSON file in /evidence/.
    """
    baseline_data = BaselineCapture.get(ticket_id)
    if not baseline_data:
        raise HTTPException(
            status_code=404,
            detail=f"No baseline found for ticket {ticket_id}. Call POST /qa/baseline/{ticket_id} first.",
        )

    baseline = SiteMetrics(**baseline_data["metrics"])
    elapsed = round(time.time() - baseline_data.get("captured_at_epoch", time.time()), 2)

    resultado, delta = QAValidator.validate(baseline, payload.post_fix_metrics)

    record = QARecord(
        ticket_id=ticket_id,
        categoria=payload.categoria,
        timestamp=baseline_data["timestamp"],
        baseline=baseline,
        post_fix=payload.post_fix_metrics,
        fix_applied=payload.fix_applied,
        resultado=resultado,
        delta_metrics=delta,
        time_elapsed_sec=elapsed,
    )

    evidence_path = EvidenceLogger.save(record)

    return {
        "ticket_id": ticket_id,
        "resultado": resultado,
        "delta_metrics": delta.model_dump(),
        "evidence_file": evidence_path.name,
    }


@app.get("/qa/report/{ticket_id}", tags=["M3 QA"])
def get_report(ticket_id: str):
    """
    Retrieve the QA report for a ticket (most recent validation run).
    """
    record = EvidenceLogger.load_latest(ticket_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No QA evidence found for ticket {ticket_id}.",
        )
    return QAReport.build(record)


@app.get("/qa/evidence/", tags=["M3 QA"])
def list_evidence():
    """
    List all QA evidence records stored in the /evidence/ folder.
    """
    return {"evidence": EvidenceLogger.list_all()}


# ---------------------------------------------------------------------------
# M4 — Motor de Correcciones
# ---------------------------------------------------------------------------

@app.post("/fix/apply/{ticket_id}", tags=["M4 Fixes"])
def apply_fix(ticket_id: str, req: FixApplyRequest):
    """
    Generate and log a fix prescription for a ticket.

    M4 constraints enforced automatically:
    - staging_obligatorio      : staging_url must contain 'staging', 'dev.', 'local', etc.
    - aprobacion_humana_criticos: prioridad=Critica requires approved_by field.

    Returns the WP-CLI command or PHP snippet to apply on staging.
    """
    try:
        result = FixEngine.apply(ticket_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/fix/rollback/{ticket_id}", tags=["M4 Fixes"])
def rollback_fix(ticket_id: str, req: RollbackRequest):
    """
    Roll back the most recently applied fix for a ticket.
    Returns the inverse payload (WP-CLI undo command or PHP removal instruction).
    """
    try:
        result = FixEngine.rollback(ticket_id, req.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.get("/fix/log/{ticket_id}", tags=["M4 Fixes"])
def get_fix_log(ticket_id: str):
    """
    Return the full audit log for a ticket (all apply + rollback operations).
    """
    entries = FixLog.read(ticket_id)
    if not entries:
        raise HTTPException(status_code=404, detail=f"No fix log found for ticket '{ticket_id}'")
    return {
        "ticket_id": ticket_id,
        "total_operations": len(entries),
        "log": [e.model_dump() for e in entries],
    }


@app.get("/fix/status/{ticket_id}", tags=["M4 Fixes"])
def get_fix_status(ticket_id: str):
    """
    Return the current fix state for a ticket (PENDING / APPLIED / ROLLED_BACK / FAILED).
    """
    state = RollbackManager.get(ticket_id)
    if not state:
        return {"ticket_id": ticket_id, "status": "PENDING", "detail": "No fix applied yet"}
    return {
        "ticket_id": ticket_id,
        "status": state.status,
        "check_name": state.check_name,
        "categoria": state.categoria,
        "metodo": state.metodo,
        "riesgo": state.riesgo,
        "timestamp": state.timestamp,
        "rollback_available": state.rollback_payload is not None and state.status == "APPLIED",
    }


@app.get("/fix/catalog/", tags=["M4 Fixes"])
def get_fix_catalog():
    """
    List all available fixes by category (derived from M4.fixes_permitidos).
    """
    catalog = {}
    for cat, checks in FIX_CATALOG.items():
        catalog[cat] = [
            {
                "check_name": name,
                "titulo": entry["titulo"],
                "riesgo": entry["riesgo"],
                "metodos": list(entry["fix"].keys()),
            }
            for name, entry in checks.items()
        ]
    return {"catalog": catalog}


# ---------------------------------------------------------------------------
# M5 — Reportes Ejecutivos
# ---------------------------------------------------------------------------

@app.post("/report/generate/{ticket_id}", tags=["M5 Reports"])
def generate_report(ticket_id: str, req: ReportRequest):
    """
    Generate a full executive report for a ticket.

    Computes:
    - RecoveryScore (SEO 30% + Perf 20% + Conv 20% + Seg 15% + Woo 15%)
    - Before/after per-category breakdown
    - Guarantee evaluation (>= 15 pts improvement)
    - Client-facing non-technical summary
    - PDF (requires reportlab; skipped gracefully if not installed)

    Persists record to reports/{ticket_id}.json.
    """
    try:
        record = build_full_report(ticket_id, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "ticket_id": ticket_id,
        "score_before": record.score_before,
        "score_after": record.score_after,
        "improvement_points": record.improvement_points,
        "improvement_pct": record.improvement_pct,
        "guarantee_met": record.guarantee_met,
        "pdf_available": record.pdf_path is not None,
        "timestamp": record.timestamp,
    }


@app.get("/report/{ticket_id}", tags=["M5 Reports"])
def get_report_full(ticket_id: str):
    """
    Return the full report record: scores, chart data, client sections, checks fixed.
    """
    record = ReportStore.load(ticket_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No report found for ticket '{ticket_id}'")
    return record


@app.get("/report/guarantee/{ticket_id}", tags=["M5 Reports"])
def get_guarantee(ticket_id: str):
    """
    Return guarantee status for a ticket.
    PASS if improvement >= 15 points.
    """
    record = ReportStore.load(ticket_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No report found for ticket '{ticket_id}'")
    return GuaranteeEvaluator.evaluate(record.score_before, record.score_after)


@app.get("/report/summary/", tags=["M5 Reports"])
def report_summary():
    """
    List all generated reports with their recovery scores and guarantee status.
    """
    return {"reports": ReportStore.list_all()}


@app.get("/report/download/{ticket_id}", tags=["M5 Reports"])
def download_pdf(ticket_id: str):
    """
    Download the PDF report for a ticket.
    Returns 404 if PDF was not generated (reportlab not installed).
    """
    record = ReportStore.load(ticket_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No report found for ticket '{ticket_id}'")
    if not record.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not available — install reportlab to enable PDF generation")
    pdf = Path(record.pdf_path)
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    return FileResponse(str(pdf), media_type="application/pdf", filename=pdf.name)


class DiagnosticoReportRequest(BaseModel):
    client_name: str
    site_url: str
    client_logo_url: Optional[str] = None
    notas: Optional[str] = None


@app.post("/report/diagnostico/{ticket_id}", tags=["M5 Reports"])
async def generate_diagnostico_report(ticket_id: str, req: DiagnosticoReportRequest):
    """
    Generate an initial diagnostic report for a NEW prospect — no QA baseline required.

    Runs a fresh M1 audit on `site_url` and uses its result as BOTH `baseline`
    and `post_fix` (improvement = 0, status = EN PROGRESO). This is the correct
    report to send a prospect before any work has started — it shows the
    Recovery Score and per-category breakdown found today, without the
    "0.0 -> 0.0" bug that occurs when baseline/post_fix are sent empty.

    Once real fixes are applied and validated via /qa/baseline + /qa/validate,
    use POST /report/generate/{ticket_id} instead to show real before/after.
    """
    try:
        audit_result = await run_full_audit(req.site_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {e}")

    if audit_result.checks is None:
        raise HTTPException(status_code=500, detail="Audit did not return checks data")

    metrics = SiteMetrics(
        pagespeed_score=audit_result.pagespeed_score or 0.0,
        recovery_score=audit_result.recovery_score,
        checks=audit_result.checks,
    )

    report_req = ReportRequest(
        client_name=req.client_name,
        site_url=req.site_url,
        client_logo_url=req.client_logo_url,
        baseline=metrics,
        post_fix=metrics,
        tickets_completados=[],
        notas=req.notas,
    )

    try:
        record = build_full_report(ticket_id, report_req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "ticket_id": ticket_id,
        "recovery_score": record.score_before,
        "per_category": record.per_category_before,
        "pdf_available": record.pdf_path is not None,
        "timestamp": record.timestamp,
    }


# ---------------------------------------------------------------------------
# M6 — Agentes IA
# ---------------------------------------------------------------------------

@app.post("/agents/run/{ticket_id}", tags=["M6 Agents"])
def run_agent(ticket_id: str, req: AgentRunRequest):
    """
    Route a single ticket to its specialized AI agent (SEOAgent, PerfAgent, etc.)
    based on ticket.categoria. Persists the response to agents/history/{ticket_id}.jsonl.

    Requires ANTHROPIC_API_KEY environment variable.
    """
    if req.ticket.id != ticket_id:
        req.ticket.id = ticket_id
    try:
        response = AgentOrchestrator.run_for_ticket(
            req.ticket, req.site_context, req.historial
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")
    return response


@app.post("/agents/batch", tags=["M6 Agents"])
def batch_agents(req: BatchRunRequest):
    """
    Run specialized AI agents for a list of tickets in sequence.
    Each ticket is routed to its agent by categoria.
    Individual failures are captured in the response (agent='ErrorAgent') without
    stopping the rest of the batch.

    Requires ANTHROPIC_API_KEY environment variable.
    """
    responses = AgentOrchestrator.batch(req.tickets, req.site_context, req.historial)
    total_tokens = sum(r.tokens_used for r in responses)
    errors = [r for r in responses if r.agent == "ErrorAgent"]
    return {
        "total_tickets": len(req.tickets),
        "processed": len(responses),
        "errors": len(errors),
        "total_tokens_used": total_tokens,
        "responses": [r.model_dump() for r in responses],
    }


@app.get("/agents/history/{ticket_id}", tags=["M6 Agents"])
def get_agent_history(ticket_id: str):
    """
    Return the full AI agent interaction history for a ticket.
    """
    entries = AgentHistoryStore.load(ticket_id)
    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"No agent history found for ticket '{ticket_id}'",
        )
    return {
        "ticket_id": ticket_id,
        "total_interactions": len(entries),
        "history": [e.model_dump() for e in entries],
    }


@app.get("/agents/", tags=["M6 Agents"])
def list_agents():
    """
    List all available AI agents and the tickets they have processed.
    """
    return {
        "agents": [
            {"nombre": agent.NOMBRE, "scope": agent.SCOPE, "model": agent.MODEL}
            for agent in SCOPE_TO_AGENT.values()
        ],
        "processed_tickets": AgentHistoryStore.list_all(),
    }


# ---------------------------------------------------------------------------
# M6 — Fix Approval (pending fixes staged by AI agents)
# ---------------------------------------------------------------------------

@app.post("/fixes/approve/{ticket_id}", tags=["M6 Agents"])
def approve_fix(ticket_id: str):
    """
    Apply a pending fix: activates its PHP snippet (if any) and runs any
    staged WP-CLI commands against the live WordPress site.
    """
    record = PendingFixStore.get(ticket_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No hay fix pendiente para el ticket '{ticket_id}'")
    if record.get("status") != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"El fix del ticket '{ticket_id}' no está pendiente (status={record.get('status')})",
        )

    site_url = record.get("site_url")
    if not site_url:
        raise HTTPException(
            status_code=400,
            detail=f"El ticket '{ticket_id}' no tiene 'site_url' definido. "
                   f"No se puede determinar a qué sitio aplicar el fix.",
        )
    api_key = os.getenv("WPREPRO_API_KEY", "")
    client = WPAgentClient(site_url, api_key)

    try:
        results = {}
        if record.get("snippet_id") is not None:
            data = client.execute_snippet({"action": "activate", "snippet_id": record["snippet_id"]})
            record["snippet_status"] = data.get("status")
            results["snippet"] = data
        if record.get("wp_cli_commands"):
            data = client.execute(record["wp_cli_commands"])
            results["wp_cli"] = data.get("results", [])

        record["status"] = "applied"
        record["applied_at"] = datetime.now(timezone.utc).isoformat()
        record["approval_results"] = results
        record["error"] = None
        PendingFixStore.save(ticket_id, record)
        return record
    except Exception as exc:
        record["status"] = "error"
        record["error"] = str(exc)
        PendingFixStore.save(ticket_id, record)
        raise HTTPException(status_code=502, detail=f"Error aplicando el fix: {exc}")


@app.post("/fixes/reject/{ticket_id}", tags=["M6 Agents"])
def reject_fix(ticket_id: str):
    """
    Discard a pending fix: removes its PHP snippet from WordPress (if any) and
    deletes the local pending record.
    """
    record = PendingFixStore.get(ticket_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No hay fix pendiente para el ticket '{ticket_id}'")

    if record.get("snippet_id") is not None:
        site_url = record.get("site_url")
        api_key = os.getenv("WPREPRO_API_KEY", "")
        if site_url:
            try:
                client = WPAgentClient(site_url, api_key)
                client.execute_snippet({"action": "delete", "snippet_id": record["snippet_id"]})
            except Exception:
                pass

    PendingFixStore.delete(ticket_id)
    return {"ticket_id": ticket_id, "status": "rejected"}


@app.get("/fixes/pending/", tags=["M6 Agents"])
def list_pending_fixes():
    """
    List all fixes awaiting human approval.
    """
    return {"pending": [r for r in PendingFixStore.list_all() if r.get("status") == "pending"]}


# ---------------------------------------------------------------------------
# M8 — Billing
# ---------------------------------------------------------------------------

@app.get("/billing/plans/", tags=["M8 Billing"])
def list_plans():
    """
    List all available subscription plans with limits and features.
    """
    return {
        "plans": [
            {
                "plan_id": key,
                "name": cfg["name"],
                "monthly_usd": cfg["monthly_usd"],
                "limits": cfg["limits"],
                "features": cfg["features"],
            }
            for key, cfg in PLANS.items()
        ]
    }


@app.post("/billing/checkout/{plan}", tags=["M8 Billing"])
def create_checkout(plan: str, req: CheckoutRequest):
    """
    Create a Stripe checkout session for the requested plan.

    In development (STRIPE_SECRET_KEY not set), returns a mock session with a
    placeholder checkout_url. In production, returns the live Stripe hosted URL.

    Plans: starter ($49) | growth ($149) | scale ($349) | elite ($899)
    """
    try:
        result = BillingService.create_checkout_session(plan, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/billing/webhook", tags=["M8 Billing"])
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint. Must receive raw body — do not wrap in JSON.

    Handled events:
    - checkout.session.completed  → activates subscription
    - customer.subscription.updated → syncs plan changes
    - customer.subscription.deleted → marks subscription canceled
    - invoice.payment_failed → marks subscription past_due

    Configure in Stripe Dashboard: Webhooks → Add endpoint → /billing/webhook
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        result = BillingService.handle_webhook(payload, sig_header)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.get("/billing/usage/{client_id}", tags=["M8 Billing"])
def get_usage(client_id: str):
    """
    Return current-month usage for a client, compared against their plan limits.
    Includes remaining quota for audits, fixes, agents, and reports.
    """
    return UsageTracker.get_with_limits(client_id)


@app.post("/billing/upgrade/{client_id}", tags=["M8 Billing"])
def upgrade_plan(client_id: str, req: UpgradeRequest):
    """
    Upgrade (or downgrade) a client's subscription to a different plan.

    In production with Stripe configured, immediately modifies the Stripe
    subscription with always_invoice proration. In mock mode, updates local state only.
    """
    try:
        result = BillingService.upgrade_subscription(client_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
