import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "results" / "20261026" / "native_full_scope_frequency_assessment"


def _load(name: str) -> dict:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_native_full_scope_frequency_assessment_preserves_facility_gates():
    verification = _load("verification.json")
    assessment = _load("facility_assessment.json")
    result = _load("campaign_result.json")
    scope = _load("scope_matrix.json")
    worklist = _load("provider_worklist.json")
    audit = _load("ijhe_completion_audit.json")

    assert verification["frequency_event_count"] == 24
    assert verification["campaign_case_count"] == 24
    assert verification["executed_case_count"] == 24
    assert verification["fully_validated_case_count"] == 5
    assert verification["operator_limited_case_count"] == 19
    assert verification["strict_uncomputed_case_count"] == 19
    assert verification["risk_atom_count"] == 96
    assert verification["frequency_scenario_count"] == 3
    assert verification["provider_worklist_event_count"] == 24
    assert verification["provider_worklist_packet_count"] == 0
    assert verification["provider_worklist_alignment_status"] == "ALIGNED"
    assert verification["frequency_checks"]["frequency_is_taken_from_catalogue_event"] is True
    assert verification["frequency_checks"]["risk_atom_frequency_mismatch_count"] == 0
    assert verification["conditional_diagnostic_facility_risk_available"] is True
    assert verification["facility_total_risk_available"] is False
    assert verification["facility_qra_claim"] is False
    assert verification["physical_validation_claim"] is False

    assert assessment["conditional_diagnostic_facility_risk_available"] is True
    assert assessment["facility_total_risk_available"] is False
    assert assessment["qualified_provider_packet_case_count"] == 0
    assert assessment["complete_facility_qra_claim"] is False
    assert assessment["conditional_diagnostic_facility_annual_ir_low_high"]["worker-01"][0] > 0
    assert assessment["conditional_diagnostic_facility_expected_death_fn_low_high"][0][
        "expected_deaths"
    ] == [1.0]

    assert result["provider_packet_case_count"] == 24
    assert result["qualified_provider_packet_case_count"] == 0
    assert result["declared_scope_numerically_complete"] is False
    assert len(result["release_termination_inventory_ledger"]["rows"]) == 24

    rows = {row["family"]: row for row in scope["rows"]}
    assert rows["vent_hole"]["status"] == "EXECUTED"
    assert rows["vertical_handoff"]["status"] == "NO_EVENT_GENERATED"
    assert rows["vessel_hole"]["status"] == "PARTIAL"
    assert rows["pipe_hole"]["status"] == "PARTIAL"
    assert scope["provider_worklist_alignment"]["status"] == "ALIGNED"
    assert scope["provider_worklist_alignment"]["aligned_event_count"] == 24

    assert worklist["generated_event_count"] == 24
    assert worklist["provider_packet_count"] == 0
    assert len(worklist["work_items"]) == 24

    assert audit["status"] == "INCOMPLETE_EVIDENCE"
    assert len(audit["checks"]) == 16
    assert sum(check["status"] == "PASS" for check in audit["checks"]) == 12
    assert sum(check["status"] == "BLOCKED" for check in audit["checks"]) == 4
