"""Audit external LH2 equipment validation evidence without promoting claims.

The equipment project contains a useful closed-operation observation dataset and
an independent-validation release gate.  Those records can support a restricted
model-evidence statement, but they do not contain an accidental release,
discharge history, or a full source-to-consequence comparison.  This module
keeps those scopes separate and never creates a provider release packet,
frequency, or facility validation claim from observation data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "prism.equipment_validation_audit.v1"


class EquipmentValidationAuditError(ValueError):
    """Raised when a validation evidence package is malformed or unsafe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise EquipmentValidationAuditError(f"cannot read evidence file: {path}") from error
    return digest.hexdigest()


def _object(path: str | Path) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise EquipmentValidationAuditError(f"validation evidence file is missing: {resolved}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EquipmentValidationAuditError(f"invalid validation evidence JSON: {resolved}") from error
    if not isinstance(value, dict):
        raise EquipmentValidationAuditError(f"validation evidence must be a JSON object: {resolved}")
    return resolved, value


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EquipmentValidationAuditError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EquipmentValidationAuditError(f"{label} must be a list")
    return value


def _date_prefix(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return value[:10]


def _audit_dataset(manifest: dict[str, Any]) -> dict[str, Any]:
    cases = _require_list(manifest.get("cases"), "dataset cases")
    if not cases:
        raise EquipmentValidationAuditError("dataset cases must not be empty")
    case_ids: set[str] = set()
    fit_cases: list[dict[str, Any]] = []
    holdout_cases: list[dict[str, Any]] = []
    for index, raw in enumerate(cases):
        row = _require_mapping(raw, f"dataset cases[{index}]")
        case_id = str(row.get("case_id", ""))
        split = str(row.get("split", ""))
        if not case_id or case_id in case_ids:
            raise EquipmentValidationAuditError("dataset case IDs must be present and unique")
        if split not in {"fit_candidate", "holdout_validation"}:
            raise EquipmentValidationAuditError(
                f"dataset cases[{index}] has unsupported split {split!r}"
            )
        case_ids.add(case_id)
        (fit_cases if split == "fit_candidate" else holdout_cases).append(row)

    fit_dates = {_date_prefix(row.get("start")) for row in fit_cases}
    holdout_dates = {_date_prefix(row.get("start")) for row in holdout_cases}
    fit_dates.discard(None)
    holdout_dates.discard(None)
    if fit_dates & holdout_dates:
        raise EquipmentValidationAuditError(
            "fit and holdout dataset dates must be disjoint"
        )
    fit_policy = _require_mapping(manifest.get("fit_policy"), "dataset fit_policy")
    cleaning_policy = _require_mapping(manifest.get("cleaning_policy"), "dataset cleaning_policy")
    blockers: list[str] = []
    if fit_policy.get("default_physics_model") != "no_fit":
        blockers.append("dataset default physics model is not declared no_fit")
    if fit_policy.get("holdout_refit") is not False:
        blockers.append("dataset holdout_refit policy is not false")
    if fit_policy.get("fitted_values_modify_component_library") is not False:
        blockers.append("dataset fit is allowed to modify the component library")
    if cleaning_policy.get("interpolation") is not False:
        blockers.append("dataset cleaning policy allows interpolation")
    declared_fit_count = manifest.get("fit_candidate_row_count")
    declared_holdout_count = manifest.get("holdout_row_count")
    if declared_fit_count is not None and declared_fit_count != sum(
        int(row.get("complete_primary_bins", 0)) for row in fit_cases
    ):
        blockers.append("fit_candidate_row_count does not close over case bins")
    if declared_holdout_count is not None and declared_holdout_count != sum(
        int(row.get("complete_primary_bins", 0)) for row in holdout_cases
    ):
        blockers.append("holdout_row_count does not close over case bins")
    return {
        "schema_version": manifest.get("schema_version"),
        "purpose": manifest.get("purpose"),
        "model_class": manifest.get("model_class"),
        "case_count": len(cases),
        "fit_case_count": len(fit_cases),
        "holdout_case_count": len(holdout_cases),
        "fit_dates": sorted(fit_dates),
        "holdout_dates": sorted(holdout_dates),
        "row_count": manifest.get("row_count"),
        "channel_count": manifest.get("channel_count"),
        "policy": {
            "no_fit_default": fit_policy.get("default_physics_model") == "no_fit",
            "holdout_refit_forbidden": fit_policy.get("holdout_refit") is False,
            "component_library_unchanged": fit_policy.get(
                "fitted_values_modify_component_library"
            ) is False,
            "interpolation_forbidden": cleaning_policy.get("interpolation") is False,
        },
        "blocking_reasons": blockers,
    }


def _audit_release_gate(gate: dict[str, Any]) -> dict[str, Any]:
    summary = _require_mapping(gate.get("summary"), "independent validation summary")
    checks = _require_mapping(gate.get("checks"), "independent validation checks")
    scenarios = _require_list(gate.get("scenarios"), "independent validation scenarios")
    blockers: list[str] = []
    if summary.get("scenario_count") != len(scenarios):
        blockers.append("independent validation scenario_count does not close")
    if summary.get("released_scenario_count") != 0:
        blockers.append("independent validation released scenarios are present")
    if summary.get("simulator_invocation_count") != 0:
        blockers.append("independent validation simulator invocations are present")
    if summary.get("official_score") is not None:
        blockers.append("independent validation contains an official score")
    if summary.get("official_score_status") != "blocked_until_explicit_raw_historian_dcs_plc_export":
        blockers.append("independent validation raw-data release gate is not closed explicitly")
    for field in ("all_scenarios_audited", "closed_raw_gate_prevented_simulation", "no_score_promoted", "no_fitting"):
        if checks.get(field) is not True:
            blockers.append(f"independent validation check {field} is not true")
    scenario_rows = []
    for index, raw in enumerate(scenarios):
        row = _require_mapping(raw, f"independent validation scenarios[{index}]")
        if row.get("status") != "blocked":
            blockers.append(f"independent validation scenario {row.get('scenario_id', index)} is not blocked")
        if row.get("simulator_invoked") is True or row.get("score_promoted") is True:
            blockers.append(
                f"independent validation scenario {row.get('scenario_id', index)} has promoted execution evidence"
            )
        scenario_rows.append({
            "scenario_id": row.get("scenario_id"),
            "status": row.get("status"),
            "simulator_invoked": row.get("simulator_invoked"),
            "score_promoted": row.get("score_promoted"),
            "blocker_count": row.get("blocker_count"),
        })
    return {
        "scope": gate.get("scope"),
        "execution_type": gate.get("execution_type"),
        "summary": {
            "scenario_count": len(scenarios),
            "released_scenario_count": summary.get("released_scenario_count"),
            "simulator_invocation_count": summary.get("simulator_invocation_count"),
            "official_score": summary.get("official_score"),
            "official_score_status": summary.get("official_score_status"),
        },
        "checks": {field: checks.get(field) for field in (
            "all_scenarios_audited", "closed_raw_gate_prevented_simulation",
            "no_score_promoted", "no_fitting",
        )},
        "scenarios": scenario_rows,
        "blocking_reasons": blockers,
    }


def audit_equipment_validation_evidence(
    dataset_manifest_path: str | Path,
    independent_validation_path: str | Path,
    *,
    topology_chain_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a restricted validation record for an external LH2 model.

    The input files are evidence ledgers, not model inputs.  A successful audit
    means that the closed-operation observation set and the independent release
    gate are internally consistent.  It never means that an accidental release
    was validated or that PRISM can claim a complete facility QRA.
    """

    dataset_path, dataset = _object(dataset_manifest_path)
    gate_path, gate = _object(independent_validation_path)
    dataset_audit = _audit_dataset(dataset)
    release_gate_audit = _audit_release_gate(gate)
    files = {
        "dataset_manifest": {
            "path": str(dataset_path),
            "sha256": _sha256(dataset_path),
        },
        "independent_validation": {
            "path": str(gate_path),
            "sha256": _sha256(gate_path),
        },
    }
    topology_audit: dict[str, Any] | None = None
    if topology_chain_path is not None:
        topology_path, topology = _object(topology_chain_path)
        topology_audit = {
            "path": str(topology_path),
            "sha256": _sha256(topology_path),
            "status": topology.get("status"),
            "screening_only": topology.get("screening_only"),
            "center_binding_ready": topology.get("center_binding_ready"),
            "forward_comparison_allowed": topology.get("forward_comparison_allowed"),
            "node_count": topology.get("topology_node_count"),
            "edge_count": topology.get("topology_edge_count"),
            "constructable_node_count": topology.get("node_constructable_count"),
            "constructable_edge_count": topology.get("edge_constructable_count"),
        }
        if topology.get("screening_only") not in {True, "screening_only"} and topology.get("status") != "screening_only":
            topology_audit["blocking_reason"] = "topology evidence is not explicitly screening_only"
    blockers = list(dataset_audit["blocking_reasons"])
    blockers.extend(release_gate_audit["blocking_reasons"])
    if topology_audit and topology_audit.get("blocking_reason"):
        blockers.append(str(topology_audit["blocking_reason"]))
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE" if not blockers else "INVALID_EQUIPMENT_EVIDENCE",
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "scope": {
            "included": [
                "closed-operation observation dataset integrity",
                "independent validation release-gate bookkeeping",
                "screening topology provenance when supplied",
            ],
            "excluded": [
                "accidental release packet",
                "release duration/isolation/inventory depletion validation",
                "SLABx-LH2 atmospheric consequence validation",
                "facility IR/F-N validation",
                "frequency inference or sensor-based failure learning",
            ],
        },
        "files": files,
        "dataset": dataset_audit,
        "independent_validation": release_gate_audit,
        "topology": topology_audit,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "promotion_policy": {
            "observation_data_is_not_a_release_packet": True,
            "screening_topology_is_not_a_facility": True,
            "no_frequency_inference": True,
            "full_chain_claim_requires_independent_release_and_consequence_validation": True,
        },
    }


__all__ = ["EquipmentValidationAuditError", "audit_equipment_validation_evidence"]
