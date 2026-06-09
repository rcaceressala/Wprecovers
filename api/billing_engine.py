from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, Header, HTTPException

from models import CheckoutRequest, ClientSubscription, UpgradeRequest, UsageRecord

BILLING_DIR = Path(__file__).parent / "billing"
_SUBS_DIR = BILLING_DIR / "subscriptions"
_USAGE_DIR = BILLING_DIR / "usage"

# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------

PLANS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "monthly_usd": 49,
        "limits": {
            "audits_per_month": 10,
            "fixes_per_month": 20,
            "agents_per_month": 25,
            "reports_per_month": 5,
            "sites": 3,
        },
        "features": [
            "M2 Motor de Tickets",
            "M3 QA Automático",
            "M4 Correcciones básicas",
            "M5 Reportes PDF",
            "Soporte por email",
        ],
    },
    "growth": {
        "name": "Growth",
        "monthly_usd": 149,
        "limits": {
            "audits_per_month": 50,
            "fixes_per_month": 100,
            "agents_per_month": 150,
            "reports_per_month": 30,
            "sites": 15,
        },
        "features": [
            "Todo Starter",
            "M6 Agentes IA (7 agentes especializados)",
            "Batch processing",
            "Reportes white-label",
            "Soporte prioritario",
        ],
    },
    "scale": {
        "name": "Scale",
        "monthly_usd": 349,
        "limits": {
            "audits_per_month": 200,
            "fixes_per_month": 500,
            "agents_per_month": 750,
            "reports_per_month": 150,
            "sites": 50,
        },
        "features": [
            "Todo Growth",
            "API acceso completo",
            "Integraciones webhook",
            "SLA 24h",
            "Manager de cuenta dedicado",
        ],
    },
    "elite": {
        "name": "Elite",
        "monthly_usd": 899,
        "limits": {
            "audits_per_month": -1,
            "fixes_per_month": -1,
            "agents_per_month": -1,
            "reports_per_month": -1,
            "sites": -1,
        },
        "features": [
            "Todo Scale",
            "Uso ilimitado en todos los módulos",
            "Integraciones custom",
            "SLA 4h",
            "Onboarding dedicado",
        ],
    },
}


# ---------------------------------------------------------------------------
# SubscriptionStore — JSON persistence per client
# ---------------------------------------------------------------------------

class SubscriptionStore:
    @staticmethod
    def _path(client_id: str) -> Path:
        _SUBS_DIR.mkdir(parents=True, exist_ok=True)
        return _SUBS_DIR / f"{client_id}.json"

    @classmethod
    def save(cls, sub: ClientSubscription) -> None:
        cls._path(sub.client_id).write_text(
            sub.model_dump_json(indent=2), encoding="utf-8"
        )

    @classmethod
    def get(cls, client_id: str) -> Optional[ClientSubscription]:
        path = cls._path(client_id)
        if not path.exists():
            return None
        return ClientSubscription(**json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def list_all(cls) -> List[ClientSubscription]:
        if not _SUBS_DIR.exists():
            return []
        result = []
        for f in _SUBS_DIR.glob("*.json"):
            try:
                result.append(ClientSubscription(**json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                pass
        return result

    @classmethod
    def find_by_stripe_customer(cls, customer_id: str) -> Optional[ClientSubscription]:
        return next(
            (s for s in cls.list_all() if s.stripe_customer_id == customer_id),
            None,
        )


# ---------------------------------------------------------------------------
# UsageTracker — monthly JSON per client, auto-rotates on new month
# ---------------------------------------------------------------------------

class UsageTracker:
    @staticmethod
    def _path(client_id: str, period: str) -> Path:
        client_dir = _USAGE_DIR / client_id
        client_dir.mkdir(parents=True, exist_ok=True)
        return client_dir / f"{period}.json"

    @classmethod
    def _current_period(cls) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    @classmethod
    def get(cls, client_id: str) -> UsageRecord:
        period = cls._current_period()
        path = cls._path(client_id, period)
        if not path.exists():
            return UsageRecord(
                client_id=client_id,
                period=period,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        return UsageRecord(**json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def increment(cls, client_id: str, metric: str, by: int = 1) -> UsageRecord:
        record = cls.get(client_id)
        field = f"{metric}_used"
        setattr(record, field, getattr(record, field, 0) + by)
        record.last_updated = datetime.now(timezone.utc).isoformat()
        path = cls._path(client_id, record.period)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    @classmethod
    def get_with_limits(cls, client_id: str) -> Dict[str, Any]:
        usage = cls.get(client_id)
        sub = SubscriptionStore.get(client_id)
        plan_key = sub.plan if sub else None
        plan_config = PLANS.get(plan_key or "", PLANS["starter"]) if plan_key else None
        limits = plan_config["limits"] if plan_config else {}

        def _fmt(metric: str) -> Dict[str, Any]:
            used = getattr(usage, f"{metric}_used", 0)
            limit = limits.get(f"{metric}_per_month", 0)
            return {
                "used": used,
                "limit": limit if limit != -1 else "unlimited",
                "remaining": "unlimited" if limit == -1 else max(0, limit - used),
            }

        return {
            "client_id": client_id,
            "period": usage.period,
            "plan": plan_key,
            "status": sub.status if sub else "no_subscription",
            "usage": {
                "audits": _fmt("audits"),
                "fixes": _fmt("fixes"),
                "agents": _fmt("agents"),
                "reports": _fmt("reports"),
            },
            "last_updated": usage.last_updated,
        }


# ---------------------------------------------------------------------------
# PlanGuard — FastAPI dependency factory for access control
# ---------------------------------------------------------------------------

def require_plan(metric: str):
    """
    Returns a FastAPI dependency that enforces plan limits for a given metric.

    Usage in endpoints:
        @app.post("/endpoint", dependencies=[Depends(require_plan("audits"))])

    Reads X-Client-Id header. Raises HTTP 402 if no active subscription,
    HTTP 429 if monthly limit is exhausted.
    """
    def _guard(x_client_id: str = Header(..., description="Client ID for plan access control")):
        sub = SubscriptionStore.get(x_client_id)
        if not sub or sub.status != "active":
            raise HTTPException(
                status_code=402,
                detail=(
                    f"No active subscription for client '{x_client_id}'. "
                    f"Subscribe at POST /billing/checkout/{{plan}}"
                ),
            )
        plan_config = PLANS.get(sub.plan, PLANS["starter"])
        limit = plan_config["limits"].get(f"{metric}_per_month", 0)
        if limit == -1:
            return x_client_id  # unlimited plan
        usage = UsageTracker.get(x_client_id)
        used = getattr(usage, f"{metric}_used", 0)
        if used >= limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Monthly limit reached: {used}/{limit} {metric} used. "
                    f"Upgrade at POST /billing/upgrade/{x_client_id}"
                ),
            )
        return x_client_id
    return _guard


# ---------------------------------------------------------------------------
# Stripe helpers
# ---------------------------------------------------------------------------

def _is_stripe_configured() -> bool:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    return bool(key) and not key.startswith("sk_test_placeholder")


def _get_stripe():
    try:
        import stripe as _stripe_mod
    except ImportError as exc:
        raise RuntimeError("stripe package not installed. Run: pip install stripe") from exc
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key or key.startswith("sk_test_placeholder"):
        raise RuntimeError("STRIPE_SECRET_KEY not configured in .env")
    _stripe_mod.api_key = key
    return _stripe_mod


# ---------------------------------------------------------------------------
# BillingService — Stripe operations with mock fallback for development
# ---------------------------------------------------------------------------

class BillingService:

    @staticmethod
    def create_checkout_session(plan: str, req: CheckoutRequest) -> Dict[str, Any]:
        if plan not in PLANS:
            raise ValueError(
                f"Unknown plan '{plan}'. Available: {list(PLANS.keys())}"
            )
        price_id = os.getenv(f"STRIPE_PRICE_{plan.upper()}", "")
        success_url = os.getenv("STRIPE_SUCCESS_URL", req.success_url)
        cancel_url = os.getenv("STRIPE_CANCEL_URL", req.cancel_url)

        if not _is_stripe_configured() or not price_id or price_id.startswith("price_placeholder"):
            return {
                "mode": "mock",
                "plan": plan,
                "client_id": req.client_id,
                "monthly_usd": PLANS[plan]["monthly_usd"],
                "checkout_url": f"https://checkout.stripe.com/mock/{plan}?client={req.client_id}",
                "session_id": f"cs_mock_{plan}_{req.client_id}",
                "note": (
                    "Mock mode: set STRIPE_SECRET_KEY and STRIPE_PRICE_"
                    f"{plan.upper()} in .env for live payments."
                ),
            }

        s = _get_stripe()
        session = s.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"client_id": req.client_id, "plan": plan},
            client_reference_id=req.client_id,
        )
        return {
            "mode": "live",
            "plan": plan,
            "client_id": req.client_id,
            "monthly_usd": PLANS[plan]["monthly_usd"],
            "checkout_url": session.url,
            "session_id": session.id,
        }

    @staticmethod
    def handle_webhook(payload: bytes, sig_header: str) -> Dict[str, Any]:
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret or webhook_secret.startswith("whsec_placeholder"):
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET not configured. Set it in .env to verify Stripe events."
            )
        s = _get_stripe()
        try:
            event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
        except s.error.SignatureVerificationError as exc:
            raise ValueError(f"Invalid webhook signature: {exc}") from exc

        etype = event["type"]
        obj = event["data"]["object"]

        handlers = {
            "checkout.session.completed": BillingService._on_checkout_completed,
            "customer.subscription.updated": BillingService._on_subscription_updated,
            "customer.subscription.deleted": BillingService._on_subscription_deleted,
            "invoice.payment_failed": BillingService._on_payment_failed,
        }
        handler = handlers.get(etype)
        if handler:
            return handler(obj)
        return {"event": etype, "handled": False}

    # -- webhook event handlers --

    @staticmethod
    def _on_checkout_completed(session: Dict) -> Dict[str, Any]:
        client_id = (
            session.get("metadata", {}).get("client_id")
            or session.get("client_reference_id")
        )
        plan = session.get("metadata", {}).get("plan", "starter")
        if not client_id:
            return {"event": "checkout.session.completed", "error": "missing client_id in metadata"}

        now = datetime.now(timezone.utc).isoformat()
        sub = ClientSubscription(
            client_id=client_id,
            plan=plan,
            stripe_customer_id=session.get("customer"),
            stripe_subscription_id=session.get("subscription"),
            status="active",
            created_at=now,
            updated_at=now,
        )
        SubscriptionStore.save(sub)
        return {
            "event": "checkout.session.completed",
            "client_id": client_id,
            "plan": plan,
            "handled": True,
        }

    @staticmethod
    def _on_subscription_updated(subscription: Dict) -> Dict[str, Any]:
        sub = SubscriptionStore.find_by_stripe_customer(subscription.get("customer", ""))
        if not sub:
            return {"event": "subscription.updated", "error": "customer not found", "handled": False}

        items = subscription.get("items", {}).get("data", [])
        new_price_id = items[0]["price"]["id"] if items else None
        new_item_id = items[0]["id"] if items else None

        new_plan = next(
            (
                p for p in PLANS
                if os.getenv(f"STRIPE_PRICE_{p.upper()}") == new_price_id
            ),
            sub.plan,
        )
        sub.plan = new_plan
        sub.status = subscription.get("status", sub.status)
        if new_item_id:
            sub.stripe_subscription_item_id = new_item_id
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        SubscriptionStore.save(sub)
        return {
            "event": "subscription.updated",
            "client_id": sub.client_id,
            "new_plan": new_plan,
            "status": sub.status,
            "handled": True,
        }

    @staticmethod
    def _on_subscription_deleted(subscription: Dict) -> Dict[str, Any]:
        sub = SubscriptionStore.find_by_stripe_customer(subscription.get("customer", ""))
        if not sub:
            return {"event": "subscription.deleted", "error": "customer not found", "handled": False}
        sub.status = "canceled"
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        SubscriptionStore.save(sub)
        return {
            "event": "subscription.deleted",
            "client_id": sub.client_id,
            "handled": True,
        }

    @staticmethod
    def _on_payment_failed(invoice: Dict) -> Dict[str, Any]:
        sub = SubscriptionStore.find_by_stripe_customer(invoice.get("customer", ""))
        if not sub:
            return {"event": "invoice.payment_failed", "error": "customer not found", "handled": False}
        sub.status = "past_due"
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        SubscriptionStore.save(sub)
        return {
            "event": "invoice.payment_failed",
            "client_id": sub.client_id,
            "status": "past_due",
            "handled": True,
        }

    @staticmethod
    def upgrade_subscription(client_id: str, req: UpgradeRequest) -> Dict[str, Any]:
        if req.new_plan not in PLANS:
            raise ValueError(
                f"Unknown plan '{req.new_plan}'. Available: {list(PLANS.keys())}"
            )
        sub = SubscriptionStore.get(client_id)
        if not sub:
            raise ValueError(f"No subscription found for client '{client_id}'")
        if sub.status == "canceled":
            raise ValueError(
                f"Subscription for '{client_id}' is canceled. "
                f"Create a new one at POST /billing/checkout/{req.new_plan}"
            )

        old_plan = sub.plan

        # Live Stripe upgrade when subscription is active and Stripe is configured
        if sub.stripe_subscription_id and _is_stripe_configured():
            new_price_id = os.getenv(f"STRIPE_PRICE_{req.new_plan.upper()}", "")
            if new_price_id and not new_price_id.startswith("price_placeholder"):
                try:
                    s = _get_stripe()
                    stripe_sub = s.Subscription.retrieve(sub.stripe_subscription_id)
                    item_id = (
                        sub.stripe_subscription_item_id
                        or stripe_sub["items"]["data"][0]["id"]
                    )
                    s.Subscription.modify(
                        sub.stripe_subscription_id,
                        items=[{"id": item_id, "price": new_price_id}],
                        proration_behavior="always_invoice",
                    )
                except Exception as exc:
                    raise ValueError(f"Stripe upgrade failed: {exc}") from exc

        sub.plan = req.new_plan
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        SubscriptionStore.save(sub)

        return {
            "client_id": client_id,
            "old_plan": old_plan,
            "new_plan": req.new_plan,
            "status": sub.status,
            "mode": "live" if _is_stripe_configured() else "mock",
            "updated_at": sub.updated_at,
        }
