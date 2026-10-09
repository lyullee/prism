import json
from pathlib import Path

import pytest

from lh2_tno.validation_evidence_matrix import (
    ValidationEvidenceMatrixError,
    build_validation_evidence_matrix,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _records(tmp_path: Path) -> dict[str, Path]:
    pool = _write(tmp_path / "pool.json", {
        "decision": "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE",
        "provenance_status": "RESTRICTED_COMPONENT_EVIDENCE_CURRENT_SOURCE_REPLAY_WITH_EXTERNAL_EVIDENCE_DRIFT",
        "hash_mismatches": ["protocol"],
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
    })
    equipment = _write(tmp_path / "equipment.json", {
        "status": "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE",
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "dataset": {"case_count": 4, "fit_case_count": 2, "holdout_case_count": 2},
        "independent_validation": {"summary": {"released_scenario_count": 0, "simulator_invocation_count": 0}},
    })
    facility = _write(tmp_path / "facility.json", {
        "status": "PARTIAL_FACILITY_SCOPE",
        "facility_total_risk_available": False,
        "qualified_facility_qra_available": False,
        "complete_facility_qra_claim": False,
        "conditional_diagnostic_facility_coverage": {
            "conditional_case_count": 80,
            "conditional_executed_case_count": 78,
            "conditional_uncomputed_case_count": 2,
            "strict_uncomputed_case_count": 37,
        },
    })
    native = _write(tmp_path / "native.json", {
        "status": "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND",
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "binding_count": 8,
        "native_accident_export_component_count": 7,
        "diagnostic_adapter_contract_verified_count": 7,
    })
    ijhe = _write(tmp_path / "ijhe.json", {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"name": "facility", "status": "BLOCKED"}],
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    })
    return {"pool": pool, "equipment": equipment, "facility": facility, "native": native, "ijhe": ijhe}


def test_matrix_keeps_component_and_diagnostic_evidence_separate(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        native_contract_path=paths["native"], ijhe_audit_path=paths["ijhe"],
    )
    assert matrix["status"] == "RESTRICTED_EVIDENCE_MATRIX"
    assert matrix["decision"] == "FACILITY_QRA_WITHHELD"
    assert matrix["physical_validation_claim"] is False
    assert matrix["facility_qra_claim"] is False
    assert len(matrix["evidence_domains"]) == 5
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_pool_spreading_component_evidence"]["allowed"] is True
    assert claims["conditional_source_to_facility_diagnostic_chain"]["status"] == "CONDITIONAL_ONLY"
    assert claims["qualified_facility_qra"]["allowed"] is False


def test_matrix_rejects_an_upstream_claim_that_would_open_promotion(tmp_path):
    paths = _records(tmp_path)
    payload = json.loads(paths["equipment"].read_text(encoding="utf-8"))
    payload["facility_qra_claim"] = True
    paths["equipment"].write_text(json.dumps(payload), encoding="utf-8")
    matrix = build_validation_evidence_matrix(paths["pool"], paths["equipment"], paths["facility"])
    assert matrix["status"] == "EVIDENCE_MATRIX_REVIEW_REQUIRED"
    assert any("prohibited facility_qra_claim=true" in reason for reason in matrix["blocking_reasons"])
    assert matrix["facility_qra_claim"] is False


def test_matrix_requires_conditional_facility_coverage(tmp_path):
    paths = _records(tmp_path)
    payload = json.loads(paths["facility"].read_text(encoding="utf-8"))
    payload.pop("conditional_diagnostic_facility_coverage")
    paths["facility"].write_text(json.dumps(payload), encoding="utf-8")
    matrix = build_validation_evidence_matrix(paths["pool"], paths["equipment"], paths["facility"])
    assert matrix["status"] == "EVIDENCE_MATRIX_REVIEW_REQUIRED"
    assert any("no conditional diagnostic coverage" in reason for reason in matrix["blocking_reasons"])


def test_matrix_fails_when_an_input_is_missing(tmp_path):
    paths = _records(tmp_path)
    with pytest.raises(ValidationEvidenceMatrixError, match="facility assessment is missing"):
        build_validation_evidence_matrix(paths["pool"], paths["equipment"], tmp_path / "missing.json")
