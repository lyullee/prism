from lh2_tno.provider_dynamic_closure_reclassification import (
    build_dynamic_closure_reclassification_audit,
)
from pathlib import Path
import json


def _row(event_id: str, status: str, *, ready=None, mode="receiving"):
    return {
        "event_id": event_id,
        "annual_condition_id": "weather-D",
        "operating_mode": mode,
        "status": status,
        "dynamic_state_closure_status": (
            "READY" if ready is True else "BLOCKED" if ready is False else None
        ),
        "dynamic_state_closure_ready": ready,
        "dynamic_state_closure_blocking_reasons": [] if ready else ["missing closure"],
    }


def test_ready_candidate_is_reported_without_promotion():
    report = build_dynamic_closure_reclassification_audit(
        {"cases": [_row("tank/A", "EXECUTED_OPERATOR_LIMITED", ready=None)]},
        {"cases": [_row("tank/A", "EXECUTED", ready=True)]},
    )
    assert report["status"] == "ADVISORY_RECLASSIFICATION_CANDIDATES"
    assert report["candidate_eligible_case_count"] == 1
    assert report["promotion_allowed"] is False
    assert report["reclassification_applied"] is False
    assert report["rows"][0]["candidate_eligible_for_reclassification"] is True


def test_blocked_or_missing_candidate_is_not_eligible():
    report = build_dynamic_closure_reclassification_audit(
        {"cases": [_row("tank/A", "EXECUTED_OPERATOR_LIMITED", ready=None)]},
        {
            "cases": [
                _row("tank/A", "EXECUTED_OPERATOR_LIMITED", ready=False),
                _row("tank/B", "EXECUTED_OPERATOR_LIMITED", ready=None),
            ]
        },
    )
    assert report["candidate_eligible_case_count"] == 0
    assert report["matched_case_count"] == 1
    assert report["unmatched_candidate_case_count"] == 1
    assert all(not row["candidate_eligible_for_reclassification"] for row in report["rows"])


def test_persisted_current_union_audit_keeps_promotion_closed():
    root = Path(__file__).parents[1]
    path = root / (
        "results/20261115/native_full_scope_union_assessment_"
        "vertical_inventory_handoff_port_bound_isolation_current/"
        "dynamic_closure_reclassification_audit.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["status"] == "ADVISORY_RECLASSIFICATION_CANDIDATES"
    assert record["current_case_count"] == 44
    assert record["candidate_case_count"] == 24
    assert record["candidate_eligible_case_count"] == 13
    assert record["new_reclassification_candidate_count"] == 9
    assert record["promotion_allowed"] is False
    assert record["reclassification_applied"] is False
