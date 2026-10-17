"""Build a fail-closed matrix of PRISM validation evidence.

The project has several useful, but deliberately different, evidence ledgers:
the DynamicLH2PoolX component replay, closed-operation equipment observations,
native external-model contract audits, and conditional facility diagnostics.
This module puts those ledgers next to one another without merging their
claims.  In particular, a passing component or interface audit can never open
the facility-QRA or full-chain physical-validation gates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


MATRIX_SCHEMA = "prism.validation_evidence_matrix.v1"


class ValidationEvidenceMatrixError(ValueError):
    """Raised when an evidence ledger is missing or makes an unsafe claim."""


def _read_object(path: str | Path, label: str) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise ValidationEvidenceMatrixError(f"{label} is missing: {resolved}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationEvidenceMatrixError(f"{label} is not valid JSON: {resolved}") from error
    if not isinstance(value, dict):
        raise ValidationEvidenceMatrixError(f"{label} must be a JSON object")
    return resolved, value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source(path: Path, label: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "sha256": _sha256(path),
        "status": payload.get("status") or payload.get("provenance_status") or payload.get("decision"),
    }


def _require_false(payload: Mapping[str, Any], field: str, label: str, blockers: list[str]) -> None:
    if payload.get(field) is True:
        blockers.append(f"{label} asserts prohibited {field}=true")


def _pool_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    if payload.get("decision") != "PASS_RESTRICTED_STAGE_C_COMPONENT_SCOPE":
        blockers.append("DynamicLH2PoolX evidence is not the accepted restricted Stage-C decision")
    _require_false(payload, "physical_validation_claim", "DynamicLH2PoolX evidence", blockers)
    _require_false(payload, "full_chain_validation_claim", "DynamicLH2PoolX evidence", blockers)
    return {
        "id": "dynamiclh2poolx_pool_spreading",
        "status": "RESTRICTED_COMPONENT_EVIDENCE",
        "supports": [
            "ground-reaching inflow to horizontal unconfined pool/spreading terms",
            "limited hold-out radius and mass-ledger checks",
        ],
        "does_not_support": [
            "equipment accident release",
            "atmospheric dispersion",
            "ignition, fire, explosion, IR/F-N",
            "facility-QRA physical validation",
        ],
        "provenance_status": payload.get("provenance_status"),
        "hash_mismatch_count": len(payload.get("hash_mismatches", [])) if isinstance(payload.get("hash_mismatches"), list) else 0,
        "source": _source(path, "DynamicLH2PoolX restricted component record", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
    }


def _equipment_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    if payload.get("status") != "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE":
        blockers.append("equipment evidence is not the restricted observation status")
    for field in (
        "physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "facility_qra_claim",
        "frequency_inference_performed",
    ):
        _require_false(payload, field, "equipment evidence", blockers)
    dataset = payload.get("dataset") if isinstance(payload.get("dataset"), Mapping) else {}
    independent = payload.get("independent_validation") if isinstance(payload.get("independent_validation"), Mapping) else {}
    summary = independent.get("summary") if isinstance(independent.get("summary"), Mapping) else {}
    return {
        "id": "equipment_observation",
        "status": "RESTRICTED_OBSERVATION_EVIDENCE",
        "supports": [
            "closed-operation observation and fit/holdout bookkeeping",
            "independent-validation release-gate bookkeeping",
        ],
        "does_not_support": [
            "accident release packet",
            "release duration, isolation, or inventory depletion validation",
            "frequency inference",
            "SLABx-LH2 or facility IR/F-N validation",
        ],
        "case_count": dataset.get("case_count"),
        "fit_case_count": dataset.get("fit_case_count"),
        "holdout_case_count": dataset.get("holdout_case_count"),
        "released_scenario_count": summary.get("released_scenario_count"),
        "simulator_invocation_count": summary.get("simulator_invocation_count"),
        "source": _source(path, "equipment observation validation audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
    }


def _native_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    for field in ("provider_packet_promoted", "physical_validation_claim", "facility_qra_claim", "frequency_inference_performed"):
        _require_false(payload, field, "native contract audit", blockers)
    return {
        "id": "native_external_model_contract",
        "status": "DIAGNOSTIC_INTERFACE_ONLY",
        "supports": [
            "static presence of native export_accident_history methods",
            "diagnostic adapter contract inspection",
        ],
        "does_not_support": [
            "qualified provider packet",
            "physical validation",
            "frequency inference",
            "facility QRA",
        ],
        "binding_count": payload.get("binding_count"),
        "native_accident_export_component_count": payload.get("native_accident_export_component_count"),
        "diagnostic_adapter_contract_verified_count": payload.get("diagnostic_adapter_contract_verified_count"),
        "source": _source(path, "native external-model contract audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
    }


def _slabx_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    """Record SLABx-LH2 component validation without opening facility gates.

    SLABx-LH2 is the consequence component used by the conditional chain.  Its
    external comparison and repeat-runtime evidence are useful for an IJHE
    evidence table, but they do not validate the equipment release boundary,
    initiating frequency, ignition model, or the complete facility QRA.  Keep
    this distinction explicit in the machine-readable matrix.
    """
    if payload.get("status") != "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE":
        blockers.append("SLABx-LH2 evidence is not the restricted consequence-evidence status")
    for field in (
        "physical_validation_claim",
        "full_chain_validation_claim",
        "frequency_inference_performed",
        "facility_qra_claim",
    ):
        _require_false(payload, field, "SLABx-LH2 evidence", blockers)
    scope = payload.get("scope") if isinstance(payload.get("scope"), Mapping) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), Mapping) else {}
    return {
        "id": "slabx_lh2_consequence_component",
        "status": "RESTRICTED_COMPONENT_EVIDENCE",
        "supports": [
            "declared outdoor hydrogen dispersion and LFL comparison cases",
            "cryogenic pool-radius and evaporation comparison cases",
            "mass-closure and repeat-runtime checks for the external consequence model",
        ],
        "does_not_support": [
            "equipment accident release, isolation, or inventory-depletion validation",
            "initiating-event frequency or sensor-frequency learning",
            "ignition, fire, explosion, IR/F-N, or facility-QRA validation",
            "indoor, detonation/DDT, obstacle, or terrain cases outside declared applicability",
        ],
        "model": payload.get("model"),
        "declared_scope": scope,
        "ffi_case_count": metrics.get("ffi_case_count"),
        "flacs_comparison_row_count": metrics.get("flacs_comparison_row_count"),
        "pool_radius_median_ratio": metrics.get("pool_radius_median_ratio"),
        "max_scenario_mass_residual_kg": metrics.get("max_scenario_mass_residual_kg"),
        "runtime_repeat_inventory_difference_kg": metrics.get("runtime_repeat_inventory_difference_kg"),
        "source_results": source_results,
        "source": _source(path, "SLABx-LH2 restricted consequence component record", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _dynamiclh2poolx_domain(
    path: Path, payload: Mapping[str, Any], blockers: list[str]
) -> dict[str, Any]:
    """Record the separately audited DynamicLH2PoolX source evidence.

    This domain is intentionally separate from the generic pool record.  It
    captures the current external source replay, hold-out observations, and
    hash drift without opening any PRISM facility-QRA promotion gate.
    """
    status = str(payload.get("status", ""))
    if not status.startswith("RESTRICTED_COMPONENT_EVIDENCE"):
        blockers.append("DynamicLH2PoolX source evidence is not a restricted component status")
    claims = payload.get("claims") if isinstance(payload.get("claims"), Mapping) else {}
    for field in (
        "independent_physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "frequency_inference_performed",
        "facility_qra_claim",
    ):
        if claims.get(field) is True:
            blockers.append(f"DynamicLH2PoolX source evidence asserts prohibited {field}=true")
    observations = payload.get("observations") if isinstance(payload.get("observations"), Mapping) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    protocol = payload.get("protocol") if isinstance(payload.get("protocol"), Mapping) else {}
    return {
        "id": "dynamiclh2poolx_source_evidence_audit",
        "status": "RESTRICTED_COMPONENT_EVIDENCE",
        "supports": [
            "JUEL hold-out pool-radius comparisons",
            "HSE Test 6 limited radius and mass-ledger assessment",
            "current-source hash and provenance-drift bookkeeping",
        ],
        "does_not_support": [
            "equipment accident release, isolation, or inventory depletion",
            "atmospheric concentration or LFL-distance validation",
            "ignition, fire, explosion, IR/F-N, or facility-QRA validation",
            "frequency inference or sensor-frequency learning",
        ],
        "audit_status": status,
        "hash_mismatch_count": payload.get("hash_mismatch_count"),
        "protocol_identifiers_match": protocol.get("identifiers_match"),
        "juel_holdout_row_count": observations.get("holdout_row_count"),
        "holdout_trials": observations.get("holdout_trials"),
        "holdout_is_disjoint": observations.get("holdout_is_disjoint"),
        "water_trial_4_radius_rmse_m": metrics.get("water_trial_4_radius_rmse_m"),
        "aluminium_trial_6_radius_rmse_m": metrics.get("aluminium_trial_6_radius_rmse_m"),
        "hse_test6_max_absolute_unledgered_residual_kg": metrics.get(
            "hse_test6_max_absolute_unledgered_residual_kg"
        ),
        "source": _source(path, "DynamicLH2PoolX current-source evidence audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _facility_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    for field in ("facility_total_risk_available", "qualified_facility_qra_available", "complete_facility_qra_claim"):
        _require_false(payload, field, "facility assessment", blockers)
    coverage = payload.get("conditional_diagnostic_facility_coverage")
    if not isinstance(coverage, Mapping):
        blockers.append("facility assessment has no conditional diagnostic coverage object")
        coverage = {}
    return {
        "id": "facility_conditional_diagnostic_chain",
        "status": "CONDITIONAL_DIAGNOSTIC_ONLY",
        "supports": [
            "conditional source-to-consequence-to-facility diagnostic execution",
            "conditional IR/F-N bookkeeping under declared screening assumptions",
        ],
        "does_not_support": [
            "qualified facility QRA",
            "independent full-chain physical validation",
            "complete accident-family coverage",
        ],
        "conditional_case_count": coverage.get("conditional_case_count"),
        "conditional_executed_case_count": coverage.get("conditional_executed_case_count"),
        "conditional_uncomputed_case_count": coverage.get("conditional_uncomputed_case_count"),
        "strict_uncomputed_case_count": coverage.get("strict_uncomputed_case_count"),
        "source": _source(path, "facility assessment", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _external_sweep_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    """Keep external tank/PSV/TNO outputs as closure and timing evidence only."""

    if payload.get("status") != "SCREENING_ONLY_EXTERNAL_SWEEP":
        blockers.append("external LH2 sweep is not the screening-only status")
    gates = payload.get("promotion_gates")
    if not isinstance(gates, Mapping):
        blockers.append("external LH2 sweep has no promotion gate object")
        gates = {}
    for field in (
        "independent_physical_validation_claim",
        "qualified_provider_packet",
        "facility_ir_fn_claim",
        "frequency_inference",
    ):
        if gates.get(field) is True:
            blockers.append(f"external LH2 sweep asserts prohibited {field}=true")
    aggregate = payload.get("aggregate") if isinstance(payload.get("aggregate"), Mapping) else {}
    return {
        "id": "external_lh2_sweep_screening",
        "status": "SCREENING_CLOSURE_AND_TIMING_ONLY",
        "supports": [
            "internal mass/energy closure bookkeeping",
            "external-model processing-time range",
            "failed-case preservation and engineering-judgement proxy labeling",
        ],
        "does_not_support": [
            "independent physical validation",
            "qualified accident release packet",
            "frequency inference",
            "facility IR/F-N",
        ],
        "tank_sweep_record_count": aggregate.get("tank_sweep_record_count"),
        "tno_policy_record_count": aggregate.get("tno_policy_record_count"),
        "maximum_tank_mass_residual_kg": aggregate.get("maximum_tank_mass_residual_kg"),
        "maximum_tank_energy_residual_J": aggregate.get("maximum_tank_energy_residual_J"),
        "tno_policy_runtime_s": aggregate.get("tno_policy_runtime_s"),
        "source": _source(path, "external LH2 sweep screening audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _external_provider_validation_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record external provider-validation evidence without qualifying a provider.

    Public LH2 outflow reports, gas-nozzle comparisons and facility screening
    gates are useful for an IJHE traceability table.  They remain separate from
    the exact PRISM accident-release packet and its qualification sidecar.
    """
    if payload.get("schema_version") != "prism.external_provider_validation_intake.v1":
        blockers.append("external provider validation intake has an unexpected schema")
    if payload.get("status") != "RESTRICTED_PROVIDER_COMPONENT_EVIDENCE":
        blockers.append("external provider validation intake is not restricted component status")
    for field in (
        "provider_qualification_claim",
        "accident_release_validation_claim",
        "independent_physical_validation_claim",
        "full_chain_validation_claim",
        "frequency_inference_performed",
        "facility_qra_claim",
    ):
        _require_false(payload, field, "external provider validation intake", blockers)
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    if not evidence:
        blockers.append("external provider validation intake contains no evidence rows")
    invalid_rows = []
    for index, row in enumerate(evidence):
        if not isinstance(row, Mapping):
            invalid_rows.append(index)
            continue
        promotion = row.get("promotion") if isinstance(row.get("promotion"), Mapping) else {}
        if promotion.get("provider_packet_match") is True:
            invalid_rows.append(index)
        if promotion.get("promotion_status") != "PROMOTION_BLOCKED":
            invalid_rows.append(index)
    if invalid_rows:
        blockers.append(
            "external provider validation intake has rows without explicit promotion blockers: "
            + ",".join(str(item) for item in sorted(set(invalid_rows)))
        )
    provider_artifacts = payload.get("provider_artifacts") if isinstance(payload.get("provider_artifacts"), Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return {
        "id": "external_provider_validation_component_evidence",
        "status": "RESTRICTED_COMPONENT_EVIDENCE",
        "supports": [
            "traceable review of public LH2 boundary and component evidence",
            "explicit separation of gaseous-nozzle, LH2 thermodynamic and facility-screening scopes",
            "provider-artifact origin and exact-match readiness accounting",
        ],
        "does_not_support": [
            "qualified provider accident release",
            "release duration, isolation or inventory-depletion qualification",
            "initiating frequency or sensor-frequency learning",
            "independent full-chain physical validation or facility IR/F-N",
        ],
        "evidence_count": summary.get("evidence_count", len(evidence)),
        "promotion_blocked_count": summary.get("promotion_blocked_count"),
        "provider_packet_match_count": summary.get("provider_packet_match_count"),
        "actual_origin_provider_artifact_count": summary.get("actual_origin_provider_artifact_count"),
        "synthetic_or_model_prediction_provider_artifact_count": summary.get(
            "synthetic_or_model_prediction_provider_artifact_count"
        ),
        "provider_artifact_count": provider_artifacts.get("artifact_file_count"),
        "provider_qualification_sidecar_count": summary.get("provider_qualification_sidecar_count"),
        "source": _source(path, "external provider validation intake", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _external_field_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Keep measured outdoor field observations separate from model claims."""

    if payload.get("status") != "RESTRICTED_EXTERNAL_FIELD_EVIDENCE":
        blockers.append("external field evidence is not in restricted verified status")
    for field in (
        "physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "facility_qra_claim",
        "frequency_inference_performed",
    ):
        if payload.get(field) is True:
            blockers.append(f"external field evidence asserts prohibited {field}=true")
    source = payload.get("source_boundary") if isinstance(payload.get("source_boundary"), Mapping) else {}
    weather = payload.get("weather") if isinstance(payload.get("weather"), Mapping) else {}
    receptors = payload.get("receptor_observations") if isinstance(payload.get("receptor_observations"), Mapping) else {}
    return {
        "id": "external_outdoor_field_observation",
        "status": "RESTRICTED_OBSERVATION_EVIDENCE",
        "supports": [
            "machine-readable outdoor LH2 source-boundary observations",
            "measured weather and receptor concentration time series",
            "common-clock and file-hash provenance for later model comparison",
        ],
        "does_not_support": [
            "provider accident-release qualification",
            "initiating frequency or sensor frequency learning",
            "ignition, fire, explosion, IR/F-N, or facility-QRA validation",
        ],
        "event_id": payload.get("event_id"),
        "dataset_id": payload.get("dataset_id"),
        "source_row_count": source.get("row_count"),
        "weather_row_count": weather.get("row_count"),
        "receptor_row_count": receptors.get("row_count"),
        "coordinate_reference": (
            payload.get("obstacle_geometry", {}).get("coordinate_reference")
            if isinstance(payload.get("obstacle_geometry"), Mapping)
            else None
        ),
        "model_comparison_ready": payload.get("model_comparison_ready"),
        "source": _source(path, "external outdoor field observation evidence", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _external_field_comparison_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record a matched field/model comparison without opening validation."""

    status = payload.get("status")
    if status not in {
        "RESTRICTED_FIELD_MODEL_COMPARISON",
        "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT",
    }:
        blockers.append("external field model comparison is blocked or malformed")
    for field in (
        "physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "facility_qra_claim",
        "frequency_inference_performed",
    ):
        _require_false(payload, field, "external field model comparison", blockers)
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    matching = payload.get("matching") if isinstance(payload.get("matching"), Mapping) else {}
    binding = payload.get("source_boundary_binding") if isinstance(payload.get("source_boundary_binding"), Mapping) else {}
    return {
        "id": "external_field_model_comparison",
        "status": (
            "RESTRICTED_COMPARISON_EVIDENCE"
            if status == "RESTRICTED_FIELD_MODEL_COMPARISON"
            else "RESTRICTED_COMPARISON_HASH_DRIFT"
            if status == "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT"
            else "BLOCKED_COMPARISON"
        ),
        "supports": [
            "declared-clock, geometry-matched field/model concentration error metrics",
            "explicit measured-source replay versus independent-model provenance",
        ],
        "does_not_support": [
            "automatic independent physical-validation promotion",
            "accident-release or initiating-frequency validation",
            "ignition, IR/F-N, or facility-QRA validation",
        ],
        "event_id": payload.get("event_id"),
        "sample_count": metrics.get("sample_count"),
        "matched_row_count": matching.get("matched_row_count"),
        "matched_fraction": matching.get("matched_fraction"),
        "rmse_vol_pct": metrics.get("rmse_vol_pct"),
        "mae_vol_pct": metrics.get("mae_vol_pct"),
        "source_boundary_mode": binding.get("mode"),
        "independent_physical_validation_review_eligible": payload.get(
            "independent_physical_validation_review_eligible"
        ),
        "source": _source(path, "external field/model comparison", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _preslhy_slabx_window_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record the native PRESLHY/SLABx window comparison as component evidence."""

    if payload.get("status") != "RESTRICTED_PRESLHY_SLABX_WINDOW_COMPARISON":
        blockers.append("PRESLHY-SLABx window evidence is not in restricted comparison status")
    for field in (
        "physical_validation_claim",
        "full_chain_validation_claim",
        "facility_qra_claim",
        "frequency_inference_performed",
    ):
        _require_false(payload, field, "PRESLHY-SLABx window evidence", blockers)
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), Mapping) else {}
    policy = payload.get("promotion_policy") if isinstance(payload.get("promotion_policy"), Mapping) else {}
    if policy.get("component_evidence_only") is not True:
        blockers.append("PRESLHY-SLABx window evidence must remain component evidence only")
    return {
        "id": "preslhy_slabx_window_comparison",
        "status": "RESTRICTED_COMPONENT_EVIDENCE",
        "supports": [
            "native SLABx sensor-window comparison against public PRESLHY trials",
            "trial-level numerical refinement and LFL-state traceability",
        ],
        "does_not_support": [
            "full time-history or independent end-to-end physical validation",
            "equipment release qualification or initiating-event frequency",
            "ignition, fire, explosion, IR/F-N, or facility-QRA validation",
        ],
        "sensor_row_count": metrics.get("sensor_row_count"),
        "evaluable_sensor_row_count": metrics.get("evaluable_sensor_row_count"),
        "predicted_sensor_row_count": metrics.get("predicted_sensor_row_count"),
        "nonzero_prediction_row_count": metrics.get("nonzero_prediction_row_count"),
        "evaluated_trial_count": metrics.get("evaluated_trial_count"),
        "refinement_row_count": metrics.get("refinement_row_count"),
        "numerical_gate_trial_count": metrics.get("numerical_gate_trial_count"),
        "accepted_numerical_gate_count": metrics.get("accepted_numerical_gate_count"),
        "mean_absolute_error_of_evaluable_windows_vol_pct": metrics.get(
            "mean_absolute_error_of_evaluable_windows_vol_pct"
        ),
        "trials": provenance.get("trials"),
        "final_level": provenance.get("final_level"),
        "source": _source(path, "PRESLHY-SLABx restricted window comparison", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _slabx_source_validation_gate_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record source-term gate evidence without calling it full-chain validation."""

    if payload.get("status") != "RESTRICTED_SOURCE_VALIDATION_GATES":
        blockers.append("SLABx-LH2 source validation gate audit is not restricted status")
    for field in (
        "physical_validation_claim",
        "independent_physical_validation_claim",
        "full_chain_validation_claim",
        "frequency_inference_performed",
        "facility_qra_claim",
    ):
        _require_false(payload, field, "SLABx-LH2 source validation gates", blockers)
    promotion = payload.get("promotion_gates") if isinstance(payload.get("promotion_gates"), Mapping) else {}
    if promotion.get("full_chain_physical_validation_allowed") is not False:
        blockers.append("SLABx-LH2 source validation gates must keep full-chain validation closed")
    closure = payload.get("casewise_numerical_closure") if isinstance(payload.get("casewise_numerical_closure"), Mapping) else {}
    return {
        "id": "slabx_lh2_source_validation_gate",
        "status": "RESTRICTED_COMPONENT_EVIDENCE",
        "supports": [
            "source-term HEM/HNEM, mass-flow envelope and numerical closure bookkeeping",
            "explicit separation of published, reproduced and non-transferable operators",
        ],
        "does_not_support": [
            "independent full-chain physical validation",
            "equipment release, isolation or inventory-depletion validation",
            "initiating frequency, ignition, IR/F-N or facility-QRA validation",
        ],
        "gate_count": payload.get("gate_count"),
        "status_counts": payload.get("status_counts"),
        "independent_quantitative_gate_count": payload.get("independent_quantitative_gate_count"),
        "casewise_row_count": closure.get("row_count"),
        "casewise_mass_closed_row_count": closure.get("mass_closed_row_count"),
        "casewise_energy_closed_row_count": closure.get("energy_closed_row_count"),
        "source": _source(path, "SLABx-LH2 source validation gate audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _slabx_direct_comparison_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record the accepted same-operator FFI Test 4 comparison."""

    if payload.get("status") != "DIRECT_COMPONENT_COMPARISON_REVIEW_READY":
        blockers.append("SLABx-LH2 direct comparison is not review-ready")
    claims = payload.get("claims") if isinstance(payload.get("claims"), Mapping) else {}
    for field in (
        "independent_physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "frequency_inference_performed",
        "facility_qra_claim",
    ):
        _require_false(claims, field, "SLABx-LH2 direct comparison", blockers)
    if claims.get("direct_component_comparison_evidence") is not True:
        blockers.append("SLABx-LH2 direct comparison does not assert its component evidence")
    policy = payload.get("promotion_policy") if isinstance(payload.get("promotion_policy"), Mapping) else {}
    if policy.get("component_evidence_does_not_validate_facility_qra") is not True:
        blockers.append("SLABx-LH2 direct comparison must keep facility-QRA promotion closed")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    return {
        "id": "slabx_lh2_direct_component_comparison",
        "status": "REVIEW_READY_COMPONENT_EVIDENCE",
        "supports": [
            "same-operator FFI Test 4 native-SLABx concentration comparison",
            "30 matched sensors over the declared 275 s observation window",
            "320/32 to 640/64 numerical refinement and LFL classification closure",
        ],
        "does_not_support": [
            "independent holdout physical validation",
            "equipment release, isolation or inventory-depletion validation",
            "initiating frequency, ignition, IR/F-N or facility-QRA validation",
        ],
        "row_count": metrics.get("row_count"),
        "sensor_count": metrics.get("sensor_count"),
        "mean_bias_vol_pct": metrics.get("mean_bias_vol_pct"),
        "mae_vol_pct": metrics.get("MAE_vol_pct"),
        "rmse_vol_pct": metrics.get("RMSE_vol_pct"),
        "observed_lfl_pairs": metrics.get("observed_LFL_pairs"),
        "predicted_lfl_pairs": metrics.get("predicted_LFL_pairs"),
        "true_positive": metrics.get("TP"),
        "false_negative": metrics.get("FN"),
        "false_positive": metrics.get("FP"),
        "independent_holdout_validation_claim": claims.get("independent_holdout_validation_claim"),
        "source": _source(path, "SLABx-LH2 direct component comparison audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _slabx_independent_comparison_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record an independent trial while respecting its open source gate."""

    allowed_statuses = {
        "RESTRICTED_INDEPENDENT_COMPARISON_SOURCE_GATE_OPEN",
        "INDEPENDENT_COMPARISON_REVIEW_READY",
    }
    if payload.get("status") not in allowed_statuses:
        blockers.append("SLABx-LH2 independent comparison is structurally blocked")
    claims = payload.get("claims") if isinstance(payload.get("claims"), Mapping) else {}
    for field in (
        "independent_physical_validation_claim",
        "full_chain_validation_claim",
        "accident_release_validation_claim",
        "frequency_inference_performed",
        "facility_qra_claim",
    ):
        _require_false(claims, field, "SLABx-LH2 independent comparison", blockers)
    if claims.get("independent_comparison_evidence") is not True:
        blockers.append("SLABx-LH2 independent comparison does not assert its restricted evidence")
    policy = payload.get("promotion_policy") if isinstance(payload.get("promotion_policy"), Mapping) else {}
    if policy.get("open_source_gate_does_not_become_physical_validation") is not True:
        blockers.append("SLABx-LH2 independent comparison must keep physical-validation promotion closed")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    source_gate = payload.get("source_gate") if isinstance(payload.get("source_gate"), Mapping) else {}
    return {
        "id": "slabx_lh2_independent_comparison",
        "status": str(payload.get("status", "UNKNOWN")),
        "supports": [
            "independent FFI Test 6 SLABx sensor comparison",
            "published-source/no-fitting provenance and LFL classification accounting",
        ],
        "does_not_support": [
            "independent physical validation while the source/numerical gate is open",
            "equipment release, isolation or inventory-depletion validation",
            "initiating frequency, ignition, IR/F-N or facility-QRA validation",
        ],
        "row_count": metrics.get("row_count"),
        "sensor_count": metrics.get("sensor_count"),
        "mean_bias_vol_pct": metrics.get("mean_bias_vol_pct"),
        "mae_vol_pct": metrics.get("MAE_vol_pct"),
        "rmse_vol_pct": metrics.get("RMSE_vol_pct"),
        "observed_lfl_pairs": metrics.get("observed_LFL_pairs"),
        "predicted_lfl_pairs": metrics.get("predicted_LFL_pairs"),
        "true_positive": metrics.get("TP"),
        "false_negative": metrics.get("FN"),
        "false_positive": metrics.get("FP"),
        "source_gate_accepted": source_gate.get("accepted"),
        "independent_physical_validation_claim": claims.get("independent_physical_validation_claim"),
        "source": _source(path, "SLABx-LH2 independent comparison audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _nasa_d4171_domain(
    path: Path,
    payload: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    """Record the public NASA tank benchmark as restricted component evidence."""

    if payload.get("source_report") != "NASA TN D-4171":
        blockers.append("NASA D-4171 benchmark has an unexpected source report")
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        blockers.append("NASA D-4171 benchmark contains no test points")
        points = []
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list):
        blockers.append("NASA D-4171 benchmark has no explicit assumptions")
        assumptions = []
    if not any("fitted" in str(item).casefold() for item in assumptions):
        blockers.append("NASA D-4171 benchmark does not state its no-fitting boundary")
    overall = payload.get("overall") if isinstance(payload.get("overall"), Mapping) else {}
    by_mode = payload.get("by_heating_mode") if isinstance(payload.get("by_heating_mode"), Mapping) else {}
    return {
        "id": "lh2dt_nasa_d4171_component_benchmark",
        "status": "RESTRICTED_COMPONENT_BENCHMARK",
        "supports": [
            "public NASA TN D-4171 self-pressurisation baseline for a closed LH2 tank",
            "unfitted homogeneous-equilibrium mass/energy state-model comparison",
        ],
        "does_not_support": [
            "equipment accident release, isolation, or inventory-depletion validation",
            "SLABx-LH2 dispersion or pool-fire validation",
            "initiating frequency, ignition, IR/F-N, or facility-QRA validation",
            "site-specific tank accuracy without a declared geometry and boundary match",
        ],
        "source_report": payload.get("source_report"),
        "source_url": payload.get("source_url"),
        "model": payload.get("model"),
        "test_point_count": len(points),
        "overall": dict(overall),
        "by_heating_mode": {
            str(key): dict(value)
            for key, value in by_mode.items()
            if isinstance(value, Mapping)
        },
        "assumption_count": len(assumptions),
        "source": _source(path, "NASA TN D-4171 restricted component benchmark", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def _audit_domain(path: Path, payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    if payload.get("status") == "COMPLETE_EVIDENCE":
        blockers.append("IJHE audit reports complete evidence; promotion must be reviewed instead of inferred")
    for field in ("physical_validation_claim", "facility_qra_claim", "complete_facility_qra_claim"):
        _require_false(payload, field, "IJHE audit", blockers)
    return {
        "id": "ijhe_scope_audit",
        "status": str(payload.get("status", "UNKNOWN")),
        "supports": ["explicit accounting of evidence blockers and diagnostic scope"],
        "does_not_support": ["automatic promotion of facility QRA"],
        "check_count": len(payload.get("checks", [])) if isinstance(payload.get("checks"), list) else None,
        "source": _source(path, "IJHE completion audit", payload),
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
    }


def build_validation_evidence_matrix(
    pool_record_path: str | Path,
    equipment_audit_path: str | Path,
    facility_assessment_path: str | Path,
    *,
    native_contract_path: str | Path | None = None,
    slabx_validation_path: str | Path | None = None,
    ijhe_audit_path: str | Path | None = None,
    external_sweep_path: str | Path | None = None,
    external_field_path: str | Path | None = None,
    external_field_comparison_path: str | Path | None = None,
    preslhy_slabx_window_path: str | Path | None = None,
    slabx_source_validation_gate_path: str | Path | None = None,
    slabx_direct_comparison_path: str | Path | None = None,
    slabx_independent_comparison_path: str | Path | None = None,
    nasa_d4171_benchmark_path: str | Path | None = None,
    dynamiclh2poolx_evidence_path: str | Path | None = None,
    external_provider_validation_path: str | Path | None = None,
) -> dict[str, Any]:
    """Combine evidence ledgers while keeping every promotion gate closed."""
    blockers: list[str] = []
    pool_path, pool = _read_object(pool_record_path, "pool validation record")
    equipment_path, equipment = _read_object(equipment_audit_path, "equipment validation audit")
    facility_path, facility = _read_object(facility_assessment_path, "facility assessment")
    domains = [
        _pool_domain(pool_path, pool, blockers),
        _equipment_domain(equipment_path, equipment, blockers),
        _facility_domain(facility_path, facility, blockers),
    ]
    if native_contract_path is not None:
        native_path, native = _read_object(native_contract_path, "native contract audit")
        domains.insert(2, _native_domain(native_path, native, blockers))
    if slabx_validation_path is not None:
        slabx_path, slabx = _read_object(slabx_validation_path, "SLABx-LH2 validation evidence")
        domains.append(_slabx_domain(slabx_path, slabx, blockers))
    if dynamiclh2poolx_evidence_path is not None:
        dynamic_path, dynamic = _read_object(
            dynamiclh2poolx_evidence_path, "DynamicLH2PoolX evidence audit"
        )
        domains.append(_dynamiclh2poolx_domain(dynamic_path, dynamic, blockers))
    if ijhe_audit_path is not None:
        audit_path, audit = _read_object(ijhe_audit_path, "IJHE audit")
        domains.append(_audit_domain(audit_path, audit, blockers))
    if external_sweep_path is not None:
        sweep_path, sweep = _read_object(external_sweep_path, "external LH2 sweep audit")
        domains.append(_external_sweep_domain(sweep_path, sweep, blockers))
    if external_provider_validation_path is not None:
        provider_path, provider = _read_object(
            external_provider_validation_path, "external provider validation intake"
        )
        domains.append(_external_provider_validation_domain(provider_path, provider, blockers))
    if external_field_path is not None:
        field_path, field = _read_object(external_field_path, "external field evidence")
        domains.append(_external_field_domain(field_path, field, blockers))
    if external_field_comparison_path is not None:
        comparison_path, comparison = _read_object(
            external_field_comparison_path, "external field model comparison"
        )
        domains.append(_external_field_comparison_domain(comparison_path, comparison, blockers))
    if preslhy_slabx_window_path is not None:
        window_path, window = _read_object(
            preslhy_slabx_window_path, "PRESLHY-SLABx window comparison"
        )
        domains.append(_preslhy_slabx_window_domain(window_path, window, blockers))
    if slabx_source_validation_gate_path is not None:
        gate_path, gate = _read_object(
            slabx_source_validation_gate_path, "SLABx-LH2 source validation gate audit"
        )
        domains.append(_slabx_source_validation_gate_domain(gate_path, gate, blockers))
    if slabx_direct_comparison_path is not None:
        direct_path, direct = _read_object(
            slabx_direct_comparison_path, "SLABx-LH2 direct comparison audit"
        )
        domains.append(_slabx_direct_comparison_domain(direct_path, direct, blockers))
    if slabx_independent_comparison_path is not None:
        independent_path, independent = _read_object(
            slabx_independent_comparison_path, "SLABx-LH2 independent comparison audit"
        )
        domains.append(
            _slabx_independent_comparison_domain(independent_path, independent, blockers)
        )
    if nasa_d4171_benchmark_path is not None:
        nasa_path, nasa = _read_object(
            nasa_d4171_benchmark_path, "NASA TN D-4171 benchmark"
        )
        domains.append(_nasa_d4171_domain(nasa_path, nasa, blockers))

    unique_blockers = list(dict.fromkeys(blockers))
    claims = [
        {
            "claim": "restricted_pool_spreading_component_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("DynamicLH2PoolX evidence" in item for item in unique_blockers),
            "basis": "dynamiclh2poolx_pool_spreading",
        },
        {
            "claim": "closed_operation_equipment_observation_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("equipment evidence" in item for item in unique_blockers),
            "basis": "equipment_observation",
        },
        {
            "claim": "conditional_source_to_facility_diagnostic_chain",
            "status": "CONDITIONAL_ONLY",
            "allowed": not any("facility assessment" in item for item in unique_blockers),
            "basis": "facility_conditional_diagnostic_chain",
        },
        {
            "claim": "restricted_slabx_lh2_consequence_component_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("SLABx-LH2 evidence" in item for item in unique_blockers),
            "basis": "slabx_lh2_consequence_component",
        },
        {
            "claim": "restricted_dynamiclh2poolx_source_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("DynamicLH2PoolX source evidence" in item for item in unique_blockers),
            "basis": "dynamiclh2poolx_source_evidence_audit",
        },
        {
            "claim": "restricted_external_outdoor_field_observation_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("external field evidence" in item for item in unique_blockers),
            "basis": "external_outdoor_field_observation",
        },
        {
            "claim": "restricted_external_field_model_comparison_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("external field model comparison" in item for item in unique_blockers),
            "basis": "external_field_model_comparison",
        },
        {
            "claim": "restricted_external_provider_component_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("external provider validation intake" in item for item in unique_blockers),
            "basis": "external_provider_validation_component_evidence",
        },
        {
            "claim": "restricted_preslhy_slabx_window_comparison_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("PRESLHY-SLABx window evidence" in item for item in unique_blockers),
            "basis": "preslhy_slabx_window_comparison",
        },
        {
            "claim": "restricted_slabx_lh2_source_validation_gate_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("SLABx-LH2 source validation gates" in item for item in unique_blockers),
            "basis": "slabx_lh2_source_validation_gate",
        },
        {
            "claim": "review_ready_slabx_lh2_direct_component_comparison",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("SLABx-LH2 direct comparison" in item for item in unique_blockers),
            "basis": "slabx_lh2_direct_component_comparison",
        },
        {
            "claim": "restricted_slabx_lh2_independent_comparison_evidence",
            "status": "SUPPORTED_WITH_RESTRICTIONS",
            "allowed": not any("SLABx-LH2 independent comparison" in item for item in unique_blockers),
            "basis": "slabx_lh2_independent_comparison",
        },
        {
            "claim": "independent_full_chain_physical_validation",
            "status": "WITHHELD",
            "allowed": False,
            "basis": "restricted_component_and_observation_evidence_only",
        },
        {
            "claim": "qualified_facility_qra",
            "status": "WITHHELD",
            "allowed": False,
            "basis": "facility promotion gate remains closed",
        },
    ]
    return {
        "schema_version": MATRIX_SCHEMA,
        "status": "RESTRICTED_EVIDENCE_MATRIX" if not unique_blockers else "EVIDENCE_MATRIX_REVIEW_REQUIRED",
        "decision": "FACILITY_QRA_WITHHELD",
        "evidence_domains": domains,
        "claims": claims,
        "blocking_reasons": unique_blockers,
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "component_evidence_does_not_validate_full_chain": True,
            "normal_observation_does_not_become_accident_release": True,
            "diagnostic_chain_does_not_become_qualified_facility_qra": True,
            "frequency_is_not_inferred_from_sensor_or_observation_data": True,
        },
    }


__all__ = ["MATRIX_SCHEMA", "ValidationEvidenceMatrixError", "build_validation_evidence_matrix"]
