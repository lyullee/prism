"""Join equipment state/HAZOP selection to the quantitative facility campaign.

The equipment twin and the quantitative campaign use different identifiers in
many real integrations.  This module makes that translation explicit instead
of silently assuming that a HAZOP row and a provider scenario refer to the
same accident.  A campaign is dispatched only after the equipment manifest,
runtime operating modes, qualitative HAZOP selections, and quantitative
scenario identities agree.

This is an integration boundary, not a physics solver.  Release duration,
inventory termination, frequency, SLABx-LH2, weather, population, ignition,
and facility IR/F-N values still come from their explicit downstream
contracts.  Missing or contradictory evidence is returned as a blocked
diagnostic result and is never replaced by a guessed event.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from typing import Any

from .equipment_hazop_handoff import build_equipment_hazop_mode_handoff
from .hazop_campaign import (
    HazopFacilityCampaignError,
    build_hazop_facility_campaign_branches_from_manifest,
)


SCHEMA = "prism.equipment_hazop_quantitative_campaign.v1"


class EquipmentHazopCampaignError(ValueError):
    """Raised when the integration manifest is malformed."""


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EquipmentHazopCampaignError(f"{label} must be a nonempty string")
    return value.strip()


def _sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EquipmentHazopCampaignError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise EquipmentHazopCampaignError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _quantitative_scenarios(runtime_result: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    components = runtime_result.get("components")
    if not isinstance(components, Mapping) or not components:
        raise EquipmentHazopCampaignError("runtime_result.components must be a nonempty object")
    result: dict[str, list[Mapping[str, Any]]] = {}
    for raw_component_id, raw_component in components.items():
        component_id = _name(raw_component_id, "runtime_result component id")
        if not isinstance(raw_component, Mapping):
            raise EquipmentHazopCampaignError(f"runtime_result.components[{component_id}] must be an object")
        branches = _sequence(raw_component.get("branches"), f"{component_id}.branches")
        result[component_id] = branches
    return result


def _qualitative_scenarios(handoff: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    audit = handoff.get("hazop_runtime_audit")
    if not isinstance(audit, Mapping):
        raise EquipmentHazopCampaignError("equipment HAZOP handoff has no runtime audit")
    rows = _sequence(audit.get("rows"), "hazop_runtime_audit.rows")
    result: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        component_id = _name(row.get("component_id"), "hazop_runtime_audit row component_id")
        selected = row.get("selected_scenarios", [])
        result[component_id] = _sequence(selected, f"{component_id}.selected_scenarios")
    return result


def _audit_identity_crosswalk(
    *,
    handoff: Mapping[str, Any],
    runtime_result: Mapping[str, Any],
    crosswalk: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check every selected qualitative row against one quantitative branch."""

    qualitative = _qualitative_scenarios(handoff)
    quantitative = _quantitative_scenarios(runtime_result)
    rows = [dict(row) for row in crosswalk]
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    errors: list[str] = []
    for index_number, row in enumerate(rows):
        component_id = _name(row.get("component_id"), f"scenario_identity_crosswalk[{index_number}].component_id")
        qualitative_id = _name(
            row.get("qualitative_scenario_id"),
            f"scenario_identity_crosswalk[{index_number}].qualitative_scenario_id",
        )
        quantitative_id = _name(
            row.get("quantitative_scenario_id"),
            f"scenario_identity_crosswalk[{index_number}].quantitative_scenario_id",
        )
        key = (component_id, qualitative_id)
        if key in index:
            errors.append(f"duplicate scenario identity crosswalk: {component_id}/{qualitative_id}")
            continue
        index[key] = row
        selected_ids = {
            str(item.get("scenario_id"))
            for item in qualitative.get(component_id, [])
            if isinstance(item.get("scenario_id"), str)
        }
        if qualitative_id not in selected_ids:
            errors.append(
                f"{component_id}: qualitative scenario is not selected by the runtime HAZOP table: {qualitative_id}"
            )
        branch_ids = {
            str(item.get("scenario_id"))
            for item in quantitative.get(component_id, [])
            if isinstance(item.get("scenario_id"), str)
        }
        if quantitative_id not in branch_ids:
            errors.append(
                f"{component_id}: quantitative runtime result has no scenario branch: {quantitative_id}"
            )
    expected: set[tuple[str, str]] = set()
    for component_id, selected in qualitative.items():
        for item in selected:
            scenario_id = item.get("scenario_id")
            if isinstance(scenario_id, str) and scenario_id.strip():
                expected.add((component_id, scenario_id))
    if set(index) != expected:
        missing = sorted(expected - set(index))
        extra = sorted(set(index) - expected)
        if missing:
            errors.append("missing scenario identity crosswalk rows: " + repr(missing))
        if extra:
            errors.append("scenario identity crosswalk contains unselected rows: " + repr(extra))
    return {
        "schema_version": "prism.equipment_hazop_scenario_identity_crosswalk.v1",
        "status": "SCENARIO_IDENTITY_CROSSWALK_ALIGNED" if not errors else "SCENARIO_IDENTITY_CROSSWALK_BLOCKED",
        "selected_qualitative_scenario_count": len(expected),
        "crosswalk_row_count": len(rows),
        "matched_row_count": len(rows) - len([error for error in errors if error.startswith("duplicate")]),
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(errors)),
        "policy": {
            "qualitative_scenario_identity_inferred": False,
            "quantitative_scenario_identity_inferred": False,
            "component_identity_inferred": False,
            "mode_identity_inferred": False,
        },
    }


def build_equipment_hazop_quantitative_campaign(
    *,
    equipment_manifest: Mapping[str, Any] | Any,
    runtime_frames: Mapping[str, Any],
    hazop_table_set: Mapping[str, Any],
    runtime_result: Mapping[str, Any],
    annual_conditions: Sequence[Mapping[str, Any]],
    scenario_bindings: Sequence[Mapping[str, Any]],
    branch_probabilities: Mapping[str, Any],
    branch_partition_groups: Mapping[str, Any],
    scenario_identity_crosswalk: Sequence[Mapping[str, Any]],
    now_s: float,
    expected_component_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a quantitative campaign only after the equipment/HAZOP join closes.

    The returned ``campaign`` is the existing PRISM facility campaign result.
    When the boundary is blocked, it is omitted and the caller receives the
    exact mismatch reasons needed to repair the digital-twin export.
    """

    handoff = build_equipment_hazop_mode_handoff(
        equipment_manifest,
        runtime_frames,
        hazop_table_set,
        now_s=now_s,
    )
    facility_id = handoff.get("facility_id")
    reasons = list(handoff.get("blocking_reasons", []))
    if runtime_result.get("facility_id") != facility_id:
        reasons.append("runtime_result.facility_id does not match equipment manifest")
    if runtime_result.get("status") != "FACILITY_HAZOP_RUNTIME_EVALUATED":
        reasons.append("runtime_result is not an evaluated HAZOP facility result")

    crosswalk_audit: dict[str, Any] | None = None
    if not reasons:
        try:
            crosswalk_rows = _sequence(
                scenario_identity_crosswalk,
                "scenario_identity_crosswalk",
            )
            crosswalk_audit = _audit_identity_crosswalk(
                handoff=handoff,
                runtime_result=runtime_result,
                crosswalk=crosswalk_rows,
            )
            reasons.extend(crosswalk_audit.get("blocking_reasons", []))
        except EquipmentHazopCampaignError as error:
            reasons.append(str(error))

    if reasons:
        return {
            "schema_version": SCHEMA,
            "status": "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BLOCKED",
            "facility_id": facility_id,
            "equipment_hazop_handoff": handoff,
            "scenario_identity_crosswalk": crosswalk_audit,
            "blocking_reasons": list(dict.fromkeys(reasons)),
            "policy": {
                "dispatch_performed": False,
                "release_created_by_prism": False,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "slabx_lh2_executed": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
            },
        }

    campaign_manifest = {
        "schema_version": "prism.hazop.facility_campaign_manifest.v1",
        "runtime_result": copy.deepcopy(dict(runtime_result)),
        "annual_conditions": copy.deepcopy(list(annual_conditions)),
        "scenario_bindings": copy.deepcopy(list(scenario_bindings)),
        "branch_probabilities": copy.deepcopy(dict(branch_probabilities)),
        "branch_partition_groups": copy.deepcopy(dict(branch_partition_groups)),
        "expected_component_ids": list(expected_component_ids),
    }
    try:
        campaign_result = build_hazop_facility_campaign_branches_from_manifest(campaign_manifest)
    except (HazopFacilityCampaignError, TypeError, ValueError) as error:
        return {
            "schema_version": SCHEMA,
            "status": "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BLOCKED",
            "facility_id": facility_id,
            "equipment_hazop_handoff": handoff,
            "scenario_identity_crosswalk": crosswalk_audit,
            "blocking_reasons": [f"quantitative campaign boundary: {error}"],
            "policy": {
                "dispatch_performed": False,
                "release_created_by_prism": False,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "slabx_lh2_executed": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
            },
        }

    return {
        "schema_version": SCHEMA,
        "status": "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "facility_id": facility_id,
        "equipment_hazop_handoff": handoff,
        "scenario_identity_crosswalk": crosswalk_audit,
        "campaign_manifest": campaign_manifest,
        "campaign_result": campaign_result,
        "campaign": campaign_result.get("campaign"),
        "facility_ledger": campaign_result.get("facility_ledger"),
        "policy": {
            "dispatch_performed": True,
            "release_created_by_prism": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "slabx_lh2_executed": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "downstream_values_are_explicit_provider_and_literature_inputs": True,
        },
    }


__all__ = [
    "SCHEMA",
    "EquipmentHazopCampaignError",
    "build_equipment_hazop_quantitative_campaign",
]
