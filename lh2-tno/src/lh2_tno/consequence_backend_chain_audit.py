"""Audit the declared LH2 release-to-consequence backend chain.

The facility campaign already stores per-case stage timings and result
digests.  This audit makes the model handoff explicit: equipment release,
DynamicLH2PoolX pool handling, SLABx-LH2 dispersion, cloud observation and
PRISM harm aggregation must all be declared in a contract and present in
every saved case.  A named accident family may only use a path that explicitly
lists that family; otherwise the case remains uncomputed.  It is an accounting
diagnostic; it does not qualify the models, infer frequency, or promote
facility IR/F-N.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.consequence_backend_chain_audit.v1"
CONTRACT_SCHEMA = "prism.consequence_backend_chain_contract.v1"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _has_path(value: Mapping[str, Any], path: str) -> bool:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return current is not None


def audit_consequence_backend_chain(
    campaign_result: Mapping[str, Any],
    backend_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed audit of the declared backend chain."""
    if not isinstance(campaign_result, Mapping):
        raise ValueError("campaign_result must be an object")
    if not isinstance(backend_contract, Mapping):
        raise ValueError("backend_contract must be an object")
    if backend_contract.get("schema_version") != CONTRACT_SCHEMA:
        raise ValueError(f"backend contract schema_version must be {CONTRACT_SCHEMA}")

    stage_rows = _rows(backend_contract.get("stages", []), "backend_contract.stages")
    stage_ids: list[str] = []
    stages: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, stage in enumerate(stage_rows):
        stage_id = str(stage.get("stage_id") or "").strip()
        owner = str(stage.get("owner") or "").strip()
        required_fields = stage.get("required_case_fields", [])
        if not stage_id or not owner:
            blockers.append(f"stage {index + 1} requires stage_id and owner")
        if stage_id in stage_ids:
            blockers.append(f"stage_id is duplicated: {stage_id}")
        stage_ids.append(stage_id)
        if not isinstance(required_fields, Sequence) or isinstance(required_fields, (str, bytes)):
            blockers.append(f"stage {stage_id} required_case_fields must be an array")
            required_fields = []
        required = [str(field).strip() for field in required_fields if str(field).strip()]
        stages.append({
            "stage_id": stage_id,
            "owner": owner,
            "required_case_fields": required,
        })

    expected = {
        "source",
        "pool",
        "near_field_and_dispersion",
        "cloud_observation",
        "fire_explosion_damage_risk",
    }
    missing_declared_stages = sorted(expected - set(stage_ids))
    if missing_declared_stages:
        blockers.append(f"backend contract omits required stage(s): {missing_declared_stages}")
    pool_stage = next((row for row in stages if row["stage_id"] == "pool"), None)
    dispersion_stage = next(
        (row for row in stages if row["stage_id"] == "near_field_and_dispersion"), None
    )
    if pool_stage is not None and "DynamicLH2PoolX" not in pool_stage["owner"]:
        blockers.append("pool stage owner does not declare DynamicLH2PoolX")
    if dispersion_stage is not None and "SLABx" not in dispersion_stage["owner"]:
        blockers.append("near-field/dispersion stage owner does not declare SLABx-LH2")

    campaign_fields_raw = backend_contract.get("required_campaign_fields", [])
    if not isinstance(campaign_fields_raw, Sequence) or isinstance(campaign_fields_raw, (str, bytes)):
        blockers.append("backend_contract.required_campaign_fields must be an array")
        campaign_fields_raw = []
    required_campaign_fields = [
        str(field).strip() for field in campaign_fields_raw if str(field).strip()
    ]
    missing_campaign_fields = [
        field for field in required_campaign_fields
        if not _has_path(campaign_result, field)
    ]
    if missing_campaign_fields:
        blockers.append(
            "campaign result is missing required facility field(s): "
            f"{missing_campaign_fields}"
        )

    path_rows_raw = backend_contract.get("paths")
    if path_rows_raw is None:
        path_rows_raw = [{
            "path_id": "default",
            "stage_ids": stage_ids,
            "required_case_fields": [],
            "required_atom_fields": [],
        }]
    path_rows = _rows(path_rows_raw, "backend_contract.paths")
    paths: list[dict[str, Any]] = []
    for index, path in enumerate(path_rows):
        path_id = str(path.get("path_id") or f"path-{index + 1}").strip()
        path_stage_ids = path.get("stage_ids", stage_ids)
        if not isinstance(path_stage_ids, Sequence) or isinstance(path_stage_ids, (str, bytes)):
            blockers.append(f"path {path_id} stage_ids must be an array")
            path_stage_ids = []
        path_stage_ids = [str(item).strip() for item in path_stage_ids if str(item).strip()]
        unknown_stage_ids = sorted(set(path_stage_ids) - set(stage_ids))
        if unknown_stage_ids:
            blockers.append(f"path {path_id} references unknown stage(s): {unknown_stage_ids}")
        family_values = path.get("scenario_families", [])
        if not isinstance(family_values, Sequence) or isinstance(family_values, (str, bytes)):
            blockers.append(f"path {path_id} scenario_families must be an array")
            family_values = []
        families = [str(item).strip() for item in family_values if str(item).strip()]
        case_fields = path.get("required_case_fields", [])
        atom_fields = path.get("required_atom_fields", [])
        if not isinstance(case_fields, Sequence) or isinstance(case_fields, (str, bytes)):
            blockers.append(f"path {path_id} required_case_fields must be an array")
            case_fields = []
        if not isinstance(atom_fields, Sequence) or isinstance(atom_fields, (str, bytes)):
            blockers.append(f"path {path_id} required_atom_fields must be an array")
            atom_fields = []
        paths.append({
            "path_id": path_id,
            "stage_ids": path_stage_ids,
            "scenario_families": families,
            "required_case_fields": [str(item).strip() for item in case_fields if str(item).strip()],
            "required_atom_fields": [str(item).strip() for item in atom_fields if str(item).strip()],
        })

    cases = _rows(campaign_result.get("cases", []), "campaign_result.cases")
    atoms = _rows(campaign_result.get("risk_atoms", []), "campaign_result.risk_atoms")
    atoms_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for atom in atoms:
        event_id = str(atom.get("event_id") or "").strip()
        if event_id:
            atoms_by_event.setdefault(event_id, []).append(atom)
    stage_coverage = {stage_id: 0 for stage_id in stage_ids if stage_id}
    stage_missing_counts = {stage_id: 0 for stage_id in stage_ids if stage_id}
    missing_field_counts: dict[str, int] = {}
    invalid_timing_count = 0
    missing_digest_count = 0
    closed_case_count = 0
    case_rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        stage_timings = case.get("stage_elapsed_ms")
        case_reasons: list[str] = []
        if not isinstance(stage_timings, Mapping):
            case_reasons.append("stage_elapsed_ms is missing")
            stage_timings = {}
        scenario_families = {
            str(item).strip() for item in case.get("scenario_families", [])
            if str(item).strip()
        } if isinstance(case.get("scenario_families", []), Sequence) and not isinstance(case.get("scenario_families", []), (str, bytes)) else set()
        matching_paths = [
            path for path in paths
            if path["scenario_families"]
            and scenario_families.intersection(path["scenario_families"])
        ]
        # An empty-family path is a default only for a case that declares no
        # scenario family.  Once the campaign has named an accident family,
        # silently routing it through a generic path would turn an unsupported
        # accident into a supported one.  Keep that case explicitly
        # uncomputed until a matching path is declared.
        if not matching_paths and not scenario_families:
            matching_paths = [path for path in paths if not path["scenario_families"]]
        if not matching_paths:
            case_reasons.append("no backend path matches the case scenario family")
            selected_path = {"path_id": None, "stage_ids": [], "required_case_fields": [], "required_atom_fields": []}
        else:
            selected_path = matching_paths[0]
            if len(matching_paths) > 1:
                case_reasons.append("more than one backend path matches the case scenario family")
        selected_stage_ids = set(selected_path["stage_ids"])
        for stage in stages:
            stage_id = stage["stage_id"]
            if stage_id not in selected_stage_ids:
                continue
            elapsed = stage_timings.get(stage_id)
            valid_elapsed = isinstance(elapsed, (int, float)) and math.isfinite(float(elapsed)) and float(elapsed) >= 0
            if valid_elapsed:
                stage_coverage[stage_id] = stage_coverage.get(stage_id, 0) + 1
            else:
                stage_missing_counts[stage_id] = stage_missing_counts.get(stage_id, 0) + 1
                case_reasons.append(f"stage timing missing or invalid: {stage_id}")
            for field in stage["required_case_fields"]:
                if not _has_path(case, field):
                    key = f"{stage_id}:{field}"
                    missing_field_counts[key] = missing_field_counts.get(key, 0) + 1
                    case_reasons.append(f"required case field missing: {field}")
        for field in selected_path["required_case_fields"]:
            if not _has_path(case, field):
                key = f"{selected_path['path_id']}:case:{field}"
                missing_field_counts[key] = missing_field_counts.get(key, 0) + 1
                case_reasons.append(f"required case field missing: {field}")
        event_atoms = atoms_by_event.get(str(case.get("event_id") or ""), [])
        for field in selected_path["required_atom_fields"]:
            if not any(_has_path(atom, field) for atom in event_atoms):
                key = f"{selected_path['path_id']}:atom:{field}"
                missing_field_counts[key] = missing_field_counts.get(key, 0) + 1
                case_reasons.append(f"required risk-atom field missing: {field}")
        if not str(case.get("backend_config_digest") or "").strip() or not str(case.get("adapter_source_digest") or "").strip():
            missing_digest_count += 1
            case_reasons.append("backend_config_digest and adapter_source_digest are required")
        if not _has_path(case, "provider_packet_identity"):
            case_reasons.append("provider_packet_identity is missing")
        if not _has_path(case, "termination"):
            case_reasons.append("termination is missing")
        if not _has_path(case, "mass_ledger"):
            case_reasons.append("mass_ledger is missing")
        if not _has_path(case, "domain_assessment"):
            case_reasons.append("domain_assessment is missing")
        if not case_reasons:
            closed_case_count += 1
        case_rows.append({
            "case_index": index,
            "event_id": case.get("event_id"),
            "path_id": selected_path["path_id"],
            "status": "BACKEND_CHAIN_CLOSED" if not case_reasons else "BACKEND_CHAIN_INCOMPLETE",
            "blocking_reasons": list(dict.fromkeys(case_reasons)),
        })

    if not cases:
        blockers.append("campaign result contains no cases")
    if closed_case_count != len(cases):
        blockers.append(f"{len(cases) - closed_case_count} case(s) do not close the declared backend chain")
    if any(count for count in stage_missing_counts.values()):
        blockers.append("one or more declared backend stages lack valid timing in a case")
    if missing_digest_count:
        blockers.append(f"{missing_digest_count} case(s) lack backend source digests")

    status = (
        "FULL_CONSEQUENCE_BACKEND_CHAIN_DIAGNOSTIC"
        if not blockers
        else "INCOMPLETE_CONSEQUENCE_BACKEND_CHAIN"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "contract_schema": backend_contract.get("schema_version"),
        "contract_id": backend_contract.get("contract_id"),
        "campaign_status": campaign_result.get("status"),
        "case_count": len(cases),
        "closed_case_count": closed_case_count,
        "stage_count": len(stages),
        "stage_ids": stage_ids,
        "stage_coverage": stage_coverage,
        "stage_missing_counts": stage_missing_counts,
        "missing_field_counts": missing_field_counts,
        "required_campaign_fields": required_campaign_fields,
        "missing_campaign_fields": missing_campaign_fields,
        "missing_backend_digest_case_count": missing_digest_count,
        "case_rows": case_rows,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "policy": {
            "diagnostic_only": True,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_ir_fn_promotion": False,
            "provider_packet_promotion": False,
        },
        "stages": stages,
    }


__all__ = ["CONTRACT_SCHEMA", "SCHEMA", "audit_consequence_backend_chain"]
