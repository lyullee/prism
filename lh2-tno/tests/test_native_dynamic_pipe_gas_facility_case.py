import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "results" / "20261026" / "native_dynamic_pipe_gas_facility_frequency"


def _load(name: str) -> dict:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_native_gas_packet_is_bound_to_facility_frequency_without_promotion():
    verification = _load("verification.json")
    result = _load("campaign_result.json")
    assessment = _load("facility_assessment.json")

    assert verification["exact_opening_match"] is True
    assert verification["literature_frequency_applied"] is True
    assert verification["frequency_from_provider_packet"] is False
    assert verification["executed_case_count"] == 2
    assert verification["uncomputed_case_count"] == 10
    assert verification["risk_atom_count"] == 8
    assert verification["facility_total_risk_available"] is False
    assert verification["facility_qra_claim"] is False
    assert verification["physical_validation_claim"] is False
    assert result["provider_packet_case_count"] == 2
    assert result["qualified_provider_packet_case_count"] == 0
    assert result["complete_facility_qra_claim"] is False
    assert all(
        atom["scenario_families"] == ["pipe_hole"]
        for atom in result["risk_atoms"]
    )
    assert assessment["conditional_diagnostic_facility_risk_available"] is True
    assert assessment["facility_total_risk_available"] is False
    assert len(assessment["frequency_uncertainty"]["scenarios"]) == 3
