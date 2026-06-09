from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models import DeltaMetrics, FixApplied, QARecord, SiteMetrics

EVIDENCE_DIR = Path(__file__).parent / "evidence"
_BASELINE_DIR = EVIDENCE_DIR / "_baselines"

# In-process cache: ticket_id -> {timestamp, metrics, captured_at_epoch}
_baselines: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# BaselineCapture
# ---------------------------------------------------------------------------

class BaselineCapture:
    """Captures and persists site metrics before a fix is applied."""

    @staticmethod
    def capture(ticket_id: str, metrics: SiteMetrics) -> Dict[str, Any]:
        _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        import time
        record: Dict[str, Any] = {
            "ticket_id": ticket_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "captured_at_epoch": time.time(),
            "metrics": metrics.model_dump(),
        }
        _baselines[ticket_id] = record
        (_BASELINE_DIR / f"{ticket_id}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        return record

    @staticmethod
    def get(ticket_id: str) -> Optional[Dict[str, Any]]:
        if ticket_id in _baselines:
            return _baselines[ticket_id]
        path = _BASELINE_DIR / f"{ticket_id}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            _baselines[ticket_id] = record
            return record
        return None


# ---------------------------------------------------------------------------
# QAValidator
# ---------------------------------------------------------------------------

class QAValidator:
    """
    Compares post-fix metrics against a baseline.
    PASS  → no regression (recovery_score did not drop)
    FAIL  → recovery_score regressed below baseline
    """

    @classmethod
    def validate(
        cls,
        baseline: SiteMetrics,
        postfix: SiteMetrics,
    ) -> Tuple[str, DeltaMetrics]:
        recovery_delta = postfix.recovery_score - baseline.recovery_score
        pagespeed_delta = postfix.pagespeed_score - baseline.pagespeed_score

        checks_fixed = 0
        checks_regressed = 0
        for cat, post_checks in postfix.checks.items():
            pre_checks = baseline.checks.get(cat, {})
            for name, post_val in post_checks.items():
                pre_val = pre_checks.get(name, post_val)
                if not pre_val and post_val:
                    checks_fixed += 1
                elif pre_val and not post_val:
                    checks_regressed += 1

        improvement_pct = (
            (recovery_delta / baseline.recovery_score * 100)
            if baseline.recovery_score > 0
            else 0.0
        )

        delta = DeltaMetrics(
            recovery_score_delta=round(recovery_delta, 2),
            pagespeed_score_delta=round(pagespeed_delta, 2),
            checks_fixed=checks_fixed,
            checks_regressed=checks_regressed,
            improvement_pct=round(improvement_pct, 2),
        )

        # PASS: improvement >= 10% OR at least no regression
        resultado = "PASS" if recovery_delta >= 0 else "FAIL"
        return resultado, delta


# ---------------------------------------------------------------------------
# EvidenceLogger
# ---------------------------------------------------------------------------

class EvidenceLogger:
    """Writes and reads QA evidence records as JSON files."""

    @staticmethod
    def save(record: QARecord) -> Path:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = EVIDENCE_DIR / f"{record.ticket_id}_{ts}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return path

    @staticmethod
    def load_latest(ticket_id: str) -> Optional[QARecord]:
        """Return the most recent QA record for a given ticket."""
        if not EVIDENCE_DIR.exists():
            return None
        candidates = sorted(
            [f for f in EVIDENCE_DIR.glob(f"{ticket_id}_*.json")],
            reverse=True,
        )
        if not candidates:
            return None
        return QARecord(**json.loads(candidates[0].read_text(encoding="utf-8")))

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        if not EVIDENCE_DIR.exists():
            return []
        result = []
        for f in sorted(
            [f for f in EVIDENCE_DIR.glob("*.json") if not f.name.startswith("_")],
            reverse=True,
        ):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(
                    {
                        "file": f.name,
                        "ticket_id": data.get("ticket_id"),
                        "categoria": data.get("categoria"),
                        "resultado": data.get("resultado"),
                        "timestamp": data.get("timestamp"),
                        "improvement_pct": data.get("delta_metrics", {}).get("improvement_pct"),
                    }
                )
            except Exception:
                pass
        return result


# ---------------------------------------------------------------------------
# QAReport
# ---------------------------------------------------------------------------

class QAReport:
    """Builds a human-readable summary dict from a QA evidence record."""

    @staticmethod
    def build(record: QARecord) -> Dict[str, Any]:
        return {
            "ticket_id": record.ticket_id,
            "categoria": record.categoria,
            "resultado": record.resultado,
            "score_before": record.baseline.recovery_score,
            "score_after": record.post_fix.recovery_score,
            "pagespeed_before": record.baseline.pagespeed_score,
            "pagespeed_after": record.post_fix.pagespeed_score,
            "delta_metrics": record.delta_metrics.model_dump(),
            "fix_applied": record.fix_applied.model_dump(),
            "time_elapsed_sec": record.time_elapsed_sec,
            "timestamp": record.timestamp,
        }
