"""Bind an isolation success/failure campaign into the current LH2 ledger.

The current v0.6 union already contains inventory-depletion and vertical-handoff
extensions, while the explicit isolation-success/failure campaign was stored as
a separate diagnostic result.  This module performs a namespace-safe merge so
reviewers can inspect a single facility chain with both branch outcomes.  It
does not qualify the synthetic barrier probability or promote facility QRA.
"""
from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any

from .campaign_namespace import rebind_campaign_result
from .contracts import canonical_digest
from .equipment_state_release_audit import build_equipment_state_release_audit
from .facility_aggregate_closure_audit import build_facility_aggregate_closure_audit
from .facility_component_contribution_audit import (
    build_facility_component_contribution_audit,
)
from .facility_ledger import merge_facility_campaign_results
from .facility_scope_matrix import (
    build_scope_matrix_from_facility_ledger,
    repair_facility_ledger_scenario_families,
)
from .risk_atom_chain_audit import build_risk_atom_chain_audit
from .state_snapshot import EquipmentStateSnapshot


ISOLATION_EXTENSION_SCHEMA = "prism.isolation_union_extension.v1"
ISOLATION_EXTENSION_NAMESPACE = "isolation-response"
ISOLATION_EXTENSION_ASSET_ID = "isolation-response-pipe"
ISOLATION_EXTENSION_COMPONENT_ID = "isolation-response-pipe-01"
REQUIRED_ACCIDENT_FAMILIES = (
    "vessel_hole",
    "pipe_hole",
    "valve_hole",
    "vent_hole",
    "pump_hole",
    "vaporizer_hole",
    "reliquefier_hole",
    "liquid_two_phase",
    "inventory_depletion",
    "inventory_over_600s",
    "two_sided_rupture",
    "vertical_handoff",
)


def _namespace_conditions(result: dict[str, Any], namespace: str) -> dict[str, Any]:
    """Namespace condition IDs so independent campaigns cannot collide."""
    output = deepcopy(result)
    conditions = output.get("annual_conditions", [])
    if not isinstance(conditions, list):
        raise ValueError("isolation campaign annual_conditions must be an array")
    mapping: dict[str, str] = {}
    for condition in conditions:
        if not isinstance(condition, dict) or not condition.get("id"):
            raise ValueError("isolation annual condition must have an id")
        old = str(condition["id"])
        new = f"{namespace.rstrip('/')}/{old}"
        mapping[old] = new
        condition["id"] = new
    for key in ("cases", "uncomputed_cases", "risk_atoms"):
        rows = output.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"isolation campaign {key} must be an array")
        for row in rows:
            if isinstance(row, dict) and row.get("annual_condition_id"):
                row["annual_condition_id"] = mapping.get(
                    str(row["annual_condition_id"]), str(row["annual_condition_id"])
                )
    output["condition_namespace_rebind"] = {
        "schema_version": "prism.condition_namespace_rebind.v1",
        "mapping": mapping,
        "diagnostic_only": True,
        "frequency_inference": False,
    }
    return output


def _as_campaign_input(result: Mapping[str, Any]) -> dict[str, Any]:
    """Expose a merged facility ledger as a campaign-compatible input."""
    output = deepcopy(dict(result))
    coverage_rows = output.get("component_coverage")
    if not isinstance(coverage_rows, Mapping):
        raise ValueError("base facility result lacks component_coverage")
    output["coverage"] = {
        "by_component": [
            dict(row)
            for row in coverage_rows.values()
            if isinstance(row, Mapping) and row.get("component_id")
        ],
        "meaning": "rebinding a prior facility ledger for diagnostic extension only",
    }
    # The prior merged ledger already has provider counts.  Keep them explicit
    # so the generic facility merger cannot mistake absent fields for evidence.
    output["provider_packet_case_count"] = int(
        output.get("provider_packet_case_count", 0) or 0
    )
    output["qualified_provider_packet_case_count"] = int(
        output.get("qualified_provider_packet_case_count", 0) or 0
    )
    output["provider_packet_promoted"] = bool(output.get("provider_packet_promoted"))
    return output


def _prepare_isolation_campaign(
    isolation_result: Mapping[str, Any],
    *,
    facility_id: str,
    provider_response: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_facility_id = str(isolation_result.get("facility_id", "")).strip()
    if not source_facility_id:
        raise ValueError("isolation campaign has no facility_id")
    namespace = f"{facility_id}/{ISOLATION_EXTENSION_NAMESPACE}"
    rebound = rebind_campaign_result(
        isolation_result,
        source_facility_id=source_facility_id,
        facility_id=facility_id,
        namespace=namespace,
        source_asset_id="terminal_pipe_asset",
        asset_id=ISOLATION_EXTENSION_ASSET_ID,
        source_component_id="terminal_pipe",
        component_id=ISOLATION_EXTENSION_COMPONENT_ID,
        receptor_map={
            "worker-01": "worker-01",
            "near_worker": "worker-01",
            "downwind_worker": "worker-01",
            "side_worker": "worker-01",
            "distant_worker": "worker-01",
        },
    )
    rebound = _namespace_conditions(rebound, namespace)
    # The stand-alone campaign has no qualified packet identity.  Keep the
    # count explicit and fail closed while preserving its numerical atoms.
    rebound["provider_packet_case_count"] = 0
    rebound["qualified_provider_packet_case_count"] = 0
    rebound["provider_packet_promoted"] = False
    rebound["provider_packet_missing_evidence_cases"] = len(rebound.get("cases", []))
    # The legacy isolation campaign predates the facility case contract.  Keep
    # a case-level diagnostic identity and a domain-assessment marker so the
    # release-to-risk chain can be audited without pretending that a qualified
    # provider packet was supplied.  A provider response can optionally add a
    # state-only snapshot below; that binding remains diagnostic.
    for case in rebound.get("cases", []):
        if not isinstance(case, dict):
            continue
        termination = case.get("termination")
        basis = termination.get("basis") if isinstance(termination, Mapping) else None
        case["provider_packet_identity"] = {
            "event_id": case.get("event_id"),
            "component_id": ISOLATION_EXTENSION_COMPONENT_ID,
            "provider_export_schema": "diagnostic-isolation-response",
            "provider_source_digests": [],
            "provider_result_digests": [case["result_digest"]]
            if case.get("result_digest")
            else [],
            "termination_bases": [basis] if basis else [],
            "termination_provenances": [
                termination.get("provenance")
            ]
            if isinstance(termination, Mapping) and termination.get("provenance")
            else [],
            "diagnostic_identity_only": True,
            "qualified_provider_packet": False,
        }
        case["domain_assessment"] = {
            "assessment_status": "not_exported_by_legacy_isolation_campaign",
            "diagnostic_only": True,
            "physical_validation_claim": False,
        }
        if provider_response is None:
            continue
        area_id = next(
            (part for part in str(case.get("event_id", "")).split("/") if part.startswith("AREA_")),
            None,
        )
        branch_id = str(case.get("release_branch_id", ""))
        branch_name = {
            "provider-isolation-success": "success",
            "provider-isolation-failure": "failure",
        }.get(branch_id)
        if not area_id or branch_name is None:
            raise ValueError(
                f"isolation case cannot map provider response: {case.get('event_id')} / {branch_id}"
            )
        area_row = provider_response.get(area_id)
        if not isinstance(area_row, Mapping) or not isinstance(area_row.get(branch_name), Mapping):
            raise ValueError(f"provider response branch is missing: {area_id}/{branch_name}")
        provider_row = area_row[branch_name]
        data = provider_row.get("data")
        if not isinstance(data, Mapping):
            raise ValueError(f"provider response data is missing: {area_id}/{branch_name}")
        steps = data.get("steps")
        if not isinstance(steps, list) or not steps or not isinstance(steps[0], Mapping):
            raise ValueError(f"provider response initial state is missing: {area_id}/{branch_name}")
        initial = steps[0]
        try:
            source_digest = str(provider_row["adapter_source_digest"])
            worker_digest = str(provider_row["worker_sha256"])
            pressure = float(initial["upstream_pressure_pa_abs"])
            temperature = float(initial["upstream_temperature_k"])
            available_mass = float(data["available_mass_kg"])
            captured_at = float(initial.get("time_s", 0.0))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"provider response initial state is invalid: {area_id}/{branch_name}") from error
        snapshot = EquipmentStateSnapshot.model_validate(
            {
                "schema_version": "prism.equipment_state_snapshot.v1",
                "component_id": ISOLATION_EXTENSION_COMPONENT_ID,
                "captured_at_s": captured_at,
                "origin": "model_prediction",
                "pressure_pa_abs": pressure,
                "temperature_k": temperature,
                "mass_kg": available_mass,
                "phase": "vapour",
                "measurements": {
                    "provider_upstream_pressure": {
                        "quantity": "pressure",
                        "value_si": pressure,
                        "sensor_location": "isolation-response-pipe-01.upstream",
                        "quality": "valid",
                    },
                    "provider_upstream_temperature": {
                        "quantity": "temperature",
                        "value_si": temperature,
                        "sensor_location": "isolation-response-pipe-01.upstream",
                        "quality": "valid",
                    },
                    "provider_available_mass": {
                        "quantity": "mass",
                        "value_si": available_mass,
                        "sensor_location": "isolation-response-pipe-01.inventory",
                        "quality": "valid",
                    },
                },
                "source_digest": source_digest,
                "quality": "valid",
            }
        )
        snapshot_mapping = snapshot.to_mapping()
        snapshot_digest = snapshot.digest()
        identity = case["provider_packet_identity"]
        identity.update(
            {
                "provider_source_digests": [source_digest, worker_digest],
                "provider_result_digests": [case["result_digest"]],
                "provider_boundary_references": [str(data.get("provider_link_id", "isolation_valve"))],
                "state_snapshot": snapshot_mapping,
                "state_snapshot_digest": snapshot_digest,
                "provider_state_snapshot_digest": snapshot_digest,
                "provider_state_snapshot_digests": [snapshot_digest],
                "termination_bases": [basis] if basis else [],
                "termination_provenances": [
                    termination.get("provenance")
                ]
                if isinstance(termination, Mapping) and termination.get("provenance")
                else [],
                "diagnostic_state_snapshot_derivation": (
                    "copied from provider_response.data.steps[0] upstream state; "
                    "model-prediction diagnostic only"
                ),
            }
        )
    # The stand-alone campaign predates the facility contribution contract and
    # therefore did not repeat component identity inside every risk atom.  Add
    # a transparent diagnostic identity shim from the already stored case
    # digest; it is deliberately not a qualified provider packet.
    case_identity: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for case in rebound.get("cases", []):
        if not isinstance(case, Mapping):
            continue
        key = (
            str(case.get("event_id", "")),
            str(case.get("annual_condition_id", "")),
            str(case.get("release_branch_id", "")),
        )
        case_identity[key] = case
    for atom in rebound.get("risk_atoms", []):
        if not isinstance(atom, dict):
            continue
        key = (
            str(atom.get("event_id", "")),
            str(atom.get("annual_condition_id", "")),
            str(atom.get("release_branch_id", "")),
        )
        case = case_identity.get(key, {})
        result_digest = case.get("result_digest")
        termination_basis = (case.get("termination") or {}).get("basis")
        atom["provider_packet_identity"] = {
            "component_id": ISOLATION_EXTENSION_COMPONENT_ID,
            "event_id": atom.get("event_id"),
            "provider_source_digests": [],
            "provider_result_digests": [result_digest] if result_digest else [],
            "termination_bases": [termination_basis] if termination_basis else [],
            "diagnostic_identity_only": True,
            "qualified_provider_packet": False,
        }
    rebound["campaign_digest"] = canonical_digest(
        {
            "source_campaign_digest": isolation_result.get("campaign_digest"),
            "namespace": namespace,
            "event_ids": [row.get("id") for row in rebound.get("events", [])],
            "condition_ids": [
                row.get("id") for row in rebound.get("annual_conditions", [])
            ],
        }
    )
    rebound["isolation_extension_rebind"] = {
        "schema_version": ISOLATION_EXTENSION_SCHEMA,
        "source_facility_id": source_facility_id,
        "target_facility_id": facility_id,
        "namespace": namespace,
        "asset_id": ISOLATION_EXTENSION_ASSET_ID,
        "component_id": ISOLATION_EXTENSION_COMPONENT_ID,
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
    }
    return rebound


def build_isolation_union_extension(
    base_result: Mapping[str, Any],
    base_scope_matrix: Mapping[str, Any],
    isolation_result: Mapping[str, Any],
    isolation_provider_response: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge the current facility ledger with explicit isolation branches."""
    if not isinstance(base_result, Mapping):
        raise ValueError("base_result must be an object")
    if not isinstance(base_scope_matrix, Mapping):
        raise ValueError("base_scope_matrix must be an object")
    if not isinstance(isolation_result, Mapping):
        raise ValueError("isolation_result must be an object")
    facility_id = str(base_result.get("facility_id", "")).strip()
    if not facility_id:
        raise ValueError("base facility result has no facility_id")
    base_input = _as_campaign_input(base_result)
    isolation = _prepare_isolation_campaign(
        isolation_result,
        facility_id=facility_id,
        provider_response=isolation_provider_response,
    )
    expected_components = sorted(
        {
            str(component_id)
            for component_id in base_result.get("component_coverage", {})
        }
        | {ISOLATION_EXTENSION_COMPONENT_ID}
    )
    merged = merge_facility_campaign_results(
        [base_input, isolation],
        expected_component_ids=expected_components,
        scope_matrices=[base_scope_matrix],
        required_accident_families=REQUIRED_ACCIDENT_FAMILIES,
    )
    merged = repair_facility_ledger_scenario_families(merged)
    scope = build_scope_matrix_from_facility_ledger(
        merged,
        required_families=REQUIRED_ACCIDENT_FAMILIES,
    )
    chain = build_risk_atom_chain_audit(merged)
    state_release = build_equipment_state_release_audit(merged)
    aggregate = build_facility_aggregate_closure_audit(merged)
    contributions = build_facility_component_contribution_audit(merged)
    isolation_branch_counts = {
        "success": sum(
            row.get("release_branch_id") == "provider-isolation-success"
            for row in isolation.get("cases", [])
            if isinstance(row, Mapping)
        ),
        "failure": sum(
            row.get("release_branch_id") == "provider-isolation-failure"
            for row in isolation.get("cases", [])
            if isinstance(row, Mapping)
        ),
    }
    return {
        "schema": ISOLATION_EXTENSION_SCHEMA,
        "status": "ISOLATION_UNION_EXTENSION_DIAGNOSTIC",
        "facility_id": facility_id,
        "base_event_count": len(base_result.get("events", [])),
        "base_case_count": len(base_result.get("cases", [])),
        "base_risk_atom_count": len(base_result.get("risk_atoms", [])),
        "isolation_event_count": len(isolation.get("events", [])),
        "isolation_case_count": len(isolation.get("cases", [])),
        "isolation_risk_atom_count": len(isolation.get("risk_atoms", [])),
        "isolation_branch_case_counts": isolation_branch_counts,
        "isolation_provider_response_consumed": isolation_provider_response is not None,
        "isolation_state_snapshot_bound_case_count": sum(
            isinstance(row, Mapping)
            and isinstance(row.get("provider_packet_identity"), Mapping)
            and isinstance(row["provider_packet_identity"].get("state_snapshot"), Mapping)
            for row in isolation.get("cases", [])
        ),
        "merged_event_count": merged["event_count"],
        "merged_case_count": merged["case_count"],
        "merged_risk_atom_count": len(merged.get("risk_atoms", [])),
        "merged_provider_packet_case_count": merged["provider_packet_case_count"],
        "merged_qualified_provider_packet_case_count": merged[
            "qualified_provider_packet_case_count"
        ],
        "merged_facility_total_risk_available": merged["facility_total_risk_available"],
        "merged_complete_facility_qra_claim": merged["complete_facility_qra_claim"],
        "scope_status": scope.get("status"),
        "scope_matrix": scope,
        "merged_campaign_result": merged,
        "isolation_rebound_result": isolation,
        "risk_atom_chain_audit": chain,
        "equipment_state_release_audit": state_release,
        "facility_aggregate_closure_audit": aggregate,
        "facility_component_contribution_audit": contributions,
        "policy": {
            "diagnostic_only": True,
            "synthetic_isolation_barrier_probability_not_inferred": True,
            "provider_packet_promotion": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_ir_fn_promotion": False,
        },
        "limitations": [
            "The isolation campaign is a namespaced synthetic diagnostic extension.",
            "The optional isolation state snapshot is copied from the provider response's first upstream state row and remains model-prediction diagnostic evidence.",
            "Success/failure branch probability is not promoted to plant reliability.",
            "Existing 34-event/44-case union remains the primary current-status ledger.",
            "Merged conditional IR/F-N is diagnostic and facility QRA remains withheld.",
        ],
    }


__all__ = [
    "ISOLATION_EXTENSION_SCHEMA",
    "ISOLATION_EXTENSION_COMPONENT_ID",
    "REQUIRED_ACCIDENT_FAMILIES",
    "build_isolation_union_extension",
]
