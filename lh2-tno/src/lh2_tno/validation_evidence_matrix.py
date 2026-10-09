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
    if ijhe_audit_path is not None:
        audit_path, audit = _read_object(ijhe_audit_path, "IJHE audit")
        domains.append(_audit_domain(audit_path, audit, blockers))
    if external_sweep_path is not None:
        sweep_path, sweep = _read_object(external_sweep_path, "external LH2 sweep audit")
        domains.append(_external_sweep_domain(sweep_path, sweep, blockers))

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
