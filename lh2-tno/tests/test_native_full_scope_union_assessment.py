import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "results" / "20261026" / "native_full_scope_union_assessment"


def _load(name: str) -> dict:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_native_full_scope_union_adds_vertical_handoff_without_qra_promotion():
    verification = _load("verification.json")
    result = _load("campaign_result.json")
    scope = _load("scope_matrix.json")
    assessment = _load("facility_assessment.json")
    rebound = _load("vertical_handoff_rebound_result.json")
    audit = _load("ijhe_completion_audit.json")

    assert verification["base_event_count"] == 24
    assert verification["vertical_event_count"] == 5
    assert verification["merged_event_count"] == 29
    assert verification["merged_case_count"] == 34
    assert verification["merged_risk_atom_count"] == 136
    assert verification["vertical_handoff_status"] == "PARTIAL"
    assert verification["vertical_handoff_conditional_status"] == "EXECUTED"
    assert verification["vertical_handoff_conditional_executed_case_count"] == 10
    assert verification["vertical_handoff_operator_limited_case_count"] == 10
    assert verification["facility_total_risk_available"] is False
    assert verification["complete_facility_qra_claim"] is False
    assert verification["qualified_provider_packet_case_count"] == 0
    assert verification["physical_validation_claim"] is False

    assert result["event_count"] == 29
    assert result["case_count"] == 34
    assert len(result["risk_atoms"]) == 136
    assert result["facility_id"] == "generic-lh2-near-receptor-diagnostic"
    assert rebound["vertical_handoff_rebind"]["diagnostic_only"] is True
    assert rebound["vertical_handoff_rebind"]["facility_qra_claim"] is False

    rows = {row["family"]: row for row in scope["rows"]}
    assert rows["vertical_handoff"]["status"] == "PARTIAL"
    assert rows["vertical_handoff"]["conditional_status"] == "EXECUTED"
    assert rows["vertical_handoff"]["generated_event_count"] == 5
    assert rows["vertical_handoff"]["case_count"] == 10
    assert assessment["conditional_diagnostic_facility_risk_available"] is True
    assert assessment["facility_total_risk_available"] is False
    assert assessment["complete_facility_qra_claim"] is False
    assert audit["status"] == "INCOMPLETE_EVIDENCE"
    assert len(audit["checks"]) == 17
    assert sum(check["status"] == "PASS" for check in audit["checks"]) == 13
    assert sum(check["status"] == "BLOCKED" for check in audit["checks"]) == 4
    vertical_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_vertical_handoff_evidence"
    )
    assert vertical_check["status"] == "PASS"
