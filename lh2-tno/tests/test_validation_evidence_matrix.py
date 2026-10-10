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
    sweep = _write(tmp_path / "sweep.json", {
        "status": "SCREENING_ONLY_EXTERNAL_SWEEP",
        "aggregate": {
            "tank_sweep_record_count": 68,
            "tno_policy_record_count": 6,
            "maximum_tank_mass_residual_kg": 1e-11,
            "maximum_tank_energy_residual_J": 1e-7,
            "tno_policy_runtime_s": {"p95": 0.4},
        },
        "promotion_gates": {
            "independent_physical_validation_claim": False,
            "qualified_provider_packet": False,
            "facility_ir_fn_claim": False,
            "frequency_inference": False,
        },
    })
    slabx = _write(tmp_path / "slabx.json", {
        "status": "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE",
        "model": {"name": "SLABx-LH2", "slabx_lh2_version": "0.1.2"},
        "scope": {"supports": ["dispersion"], "excludes": ["facility QRA"]},
        "metrics": {
            "ffi_case_count": 6,
            "flacs_comparison_row_count": 6,
            "pool_radius_median_ratio": 1.03,
            "max_scenario_mass_residual_kg": 1e-12,
            "runtime_repeat_inventory_difference_kg": 0.0,
        },
        "source_results": {"path": "external/results.json", "sha256": "a" * 64},
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
    })
    field = _write(tmp_path / "field.json", {
        "schema_version": "prism.external_field_evidence.v1",
        "status": "RESTRICTED_EXTERNAL_FIELD_EVIDENCE",
        "event_id": "field-trial-01",
        "dataset_id": "dataset-01",
        "source_boundary": {"row_count": 208},
        "weather": {"row_count": 92},
        "receptor_observations": {"row_count": 5053},
        "model_comparison_ready": False,
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
    })
    comparison = _write(tmp_path / "comparison.json", {
        "schema_version": "prism.external_field_model_comparison.v1",
        "status": "RESTRICTED_FIELD_MODEL_COMPARISON",
        "event_id": "field-trial-01",
        "matching": {"matched_row_count": 4, "matched_fraction": 1.0},
        "metrics": {"sample_count": 4, "rmse_vol_pct": 0.02, "mae_vol_pct": 0.01},
        "source_boundary_binding": {"mode": "measured_source_replay"},
        "independent_physical_validation_review_eligible": False,
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
    })
    preslhy_window = _write(tmp_path / "preslhy_window.json", {
        "schema_version": "prism.preslhy_slabx_window_comparison_audit.v1",
        "status": "RESTRICTED_PRESLHY_SLABX_WINDOW_COMPARISON",
        "metrics": {
            "sensor_row_count": 217,
            "evaluable_sensor_row_count": 155,
            "predicted_sensor_row_count": 155,
            "nonzero_prediction_row_count": 105,
            "evaluated_trial_count": 7,
            "refinement_row_count": 21,
            "numerical_gate_trial_count": 7,
            "accepted_numerical_gate_count": 1,
            "mean_absolute_error_of_evaluable_windows_vol_pct": 11.4,
        },
        "provenance": {"trials": [10, 11, 12, 22, 23, 24, 25], "final_level": 640},
        "promotion_policy": {"component_evidence_only": True},
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
    })
    source_gate = _write(tmp_path / "source_gate.json", {
        "schema_version": "prism.slabx_lh2_source_validation_gate_audit.v1",
        "status": "RESTRICTED_SOURCE_VALIDATION_GATES",
        "gate_count": 6,
        "status_counts": {"automated": 1},
        "independent_quantitative_gate_count": 0,
        "casewise_numerical_closure": {
            "row_count": 6,
            "mass_closed_row_count": 6,
            "energy_closed_row_count": 6,
        },
        "physical_validation_claim": False,
        "independent_physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_gates": {"full_chain_physical_validation_allowed": False},
    })
    direct_comparison = _write(tmp_path / "direct_comparison.json", {
        "schema_version": "prism.slabx_lh2_direct_comparison_audit.v1",
        "status": "DIRECT_COMPONENT_COMPARISON_REVIEW_READY",
        "metrics": {
            "row_count": 30,
            "sensor_count": 30,
            "mean_bias_vol_pct": -0.45,
            "MAE_vol_pct": 0.65,
            "RMSE_vol_pct": 1.21,
            "observed_LFL_pairs": 3,
            "predicted_LFL_pairs": 3,
            "TP": 3,
            "FN": 0,
            "FP": 0,
        },
        "claims": {
            "direct_component_comparison_evidence": True,
            "independent_holdout_validation_claim": False,
            "independent_physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "accident_release_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
        "promotion_policy": {
            "component_evidence_does_not_validate_facility_qra": True,
        },
    })
    independent_comparison = _write(tmp_path / "independent_comparison.json", {
        "schema_version": "prism.slabx_lh2_independent_comparison_audit.v1",
        "status": "RESTRICTED_INDEPENDENT_COMPARISON_SOURCE_GATE_OPEN",
        "metrics": {
            "row_count": 30,
            "sensor_count": 30,
            "mean_bias_vol_pct": -1.19,
            "MAE_vol_pct": 1.87,
            "RMSE_vol_pct": 4.54,
            "observed_LFL_pairs": 6,
            "predicted_LFL_pairs": 3,
            "TP": 3,
            "FN": 3,
            "FP": 0,
        },
        "source_gate": {"accepted": False},
        "claims": {
            "independent_comparison_evidence": True,
            "independent_physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "accident_release_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
        "promotion_policy": {
            "open_source_gate_does_not_become_physical_validation": True,
        },
    })
    return {"pool": pool, "equipment": equipment, "facility": facility, "native": native, "ijhe": ijhe, "sweep": sweep, "slabx": slabx, "field": field, "comparison": comparison, "preslhy_window": preslhy_window, "source_gate": source_gate, "direct_comparison": direct_comparison, "independent_comparison": independent_comparison}


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


def test_matrix_records_slabx_component_evidence_without_opening_qra(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        slabx_validation_path=paths["slabx"],
    )
    domain = next(row for row in matrix["evidence_domains"] if row["id"] == "slabx_lh2_consequence_component")
    assert domain["status"] == "RESTRICTED_COMPONENT_EVIDENCE"
    assert domain["ffi_case_count"] == 6
    assert domain["physical_validation_claim"] is False
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_slabx_lh2_consequence_component_evidence"]["allowed"] is True
    assert matrix["facility_qra_claim"] is False


def test_matrix_records_external_field_observation_without_opening_validation_or_qra(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        external_field_path=paths["field"],
    )
    domain = next(row for row in matrix["evidence_domains"] if row["id"] == "external_outdoor_field_observation")
    assert domain["status"] == "RESTRICTED_OBSERVATION_EVIDENCE"
    assert domain["source_row_count"] == 208
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_external_outdoor_field_observation_evidence"]["allowed"] is True
    assert matrix["physical_validation_claim"] is False
    assert matrix["facility_qra_claim"] is False


def test_matrix_records_field_model_comparison_without_opening_validation(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        external_field_comparison_path=paths["comparison"],
    )
    domain = next(row for row in matrix["evidence_domains"] if row["id"] == "external_field_model_comparison")
    assert domain["status"] == "RESTRICTED_COMPARISON_EVIDENCE"
    assert domain["matched_row_count"] == 4
    assert domain["source_boundary_mode"] == "measured_source_replay"
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_external_field_model_comparison_evidence"]["allowed"] is True
    assert matrix["physical_validation_claim"] is False


def test_matrix_records_preslhy_slabx_window_comparison_without_opening_validation(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        preslhy_slabx_window_path=paths["preslhy_window"],
    )
    domain = next(
        row for row in matrix["evidence_domains"]
        if row["id"] == "preslhy_slabx_window_comparison"
    )
    assert domain["status"] == "RESTRICTED_COMPONENT_EVIDENCE"
    assert domain["accepted_numerical_gate_count"] == 1
    assert domain["nonzero_prediction_row_count"] == 105
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_preslhy_slabx_window_comparison_evidence"]["allowed"] is True
    assert matrix["physical_validation_claim"] is False


def test_matrix_records_slabx_source_gate_evidence_without_opening_validation(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        slabx_source_validation_gate_path=paths["source_gate"],
    )
    domain = next(
        row for row in matrix["evidence_domains"]
        if row["id"] == "slabx_lh2_source_validation_gate"
    )
    assert domain["gate_count"] == 6
    assert domain["casewise_mass_closed_row_count"] == 6
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_slabx_lh2_source_validation_gate_evidence"]["allowed"] is True
    assert matrix["physical_validation_claim"] is False


def test_matrix_records_direct_slabx_comparison_without_opening_validation(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        slabx_direct_comparison_path=paths["direct_comparison"],
    )
    domain = next(
        row for row in matrix["evidence_domains"]
        if row["id"] == "slabx_lh2_direct_component_comparison"
    )
    assert domain["status"] == "REVIEW_READY_COMPONENT_EVIDENCE"
    assert domain["row_count"] == 30
    assert domain["false_negative"] == 0
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["review_ready_slabx_lh2_direct_component_comparison"]["allowed"] is True
    assert matrix["physical_validation_claim"] is False
    assert matrix["facility_qra_claim"] is False


def test_matrix_records_independent_slabx_comparison_without_opening_validation(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        slabx_independent_comparison_path=paths["independent_comparison"],
    )
    domain = next(
        row for row in matrix["evidence_domains"]
        if row["id"] == "slabx_lh2_independent_comparison"
    )
    assert domain["status"] == "RESTRICTED_INDEPENDENT_COMPARISON_SOURCE_GATE_OPEN"
    assert domain["source_gate_accepted"] is False
    assert domain["false_negative"] == 3
    claims = {row["claim"]: row for row in matrix["claims"]}
    assert claims["restricted_slabx_lh2_independent_comparison_evidence"]["allowed"] is True
    assert matrix["physical_validation_claim"] is False
    assert matrix["facility_qra_claim"] is False


def test_matrix_rejects_slabx_promotion_claim(tmp_path):
    paths = _records(tmp_path)
    payload = json.loads(paths["slabx"].read_text(encoding="utf-8"))
    payload["physical_validation_claim"] = True
    paths["slabx"].write_text(json.dumps(payload), encoding="utf-8")
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        slabx_validation_path=paths["slabx"],
    )
    assert matrix["status"] == "EVIDENCE_MATRIX_REVIEW_REQUIRED"
    assert any("SLABx-LH2 evidence" in reason for reason in matrix["blocking_reasons"])
    assert matrix["physical_validation_claim"] is False


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


def test_matrix_keeps_external_sweep_as_closure_and_timing_only(tmp_path):
    paths = _records(tmp_path)
    matrix = build_validation_evidence_matrix(
        paths["pool"], paths["equipment"], paths["facility"],
        external_sweep_path=paths["sweep"],
    )
    domain = next(row for row in matrix["evidence_domains"] if row["id"] == "external_lh2_sweep_screening")
    assert domain["status"] == "SCREENING_CLOSURE_AND_TIMING_ONLY"
    assert domain["maximum_tank_mass_residual_kg"] == 1e-11
    assert matrix["physical_validation_claim"] is False
    assert matrix["facility_qra_claim"] is False


def test_matrix_fails_when_an_input_is_missing(tmp_path):
    paths = _records(tmp_path)
    with pytest.raises(ValidationEvidenceMatrixError, match="facility assessment is missing"):
        build_validation_evidence_matrix(paths["pool"], paths["equipment"], tmp_path / "missing.json")
