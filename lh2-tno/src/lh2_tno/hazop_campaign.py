"""Bridge HAZOP-gated runtime results into the facility campaign ledger.

The HAZOP runtime coordinator deliberately stops at one current-weather
consequence result per component.  This module is the explicit handoff to the
existing annual-condition/facility ledger.  It does not invent weather,
population, ignition, release, termination, or frequency data: those values
must be supplied in ``scenario_bindings`` and ``annual_conditions``.

The bridge accepts one selected HAZOP branch per component.  Multiple active
branches remain a separate dispatch problem because their event identities and
frequencies require an explicit branch partition before a facility total can
be calculated.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import math
from typing import Any

from .contracts import canonical_digest
from .facility_ledger import merge_facility_campaign_results
from .realtime_campaign import (
    IGNITION_BRANCHES,
    build_realtime_facility_campaign_result,
)


class HazopFacilityCampaignError(ValueError):
    """Raised when a HAZOP runtime result cannot cross the campaign boundary."""


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HazopFacilityCampaignError(f"{label} must be a nonempty string")
    return value


def _probability(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise HazopFacilityCampaignError(
            f"{label} must be a finite probability in [0, 1]"
        )
    return float(value)


def _selected_single_branch(
    runtime_result: Mapping[str, Any], component_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    """Return branch metadata, consequence, risk and selection for one component."""

    components = runtime_result.get("components")
    if not isinstance(components, Mapping):
        raise HazopFacilityCampaignError("runtime result components must be a mapping")
    row = components.get(component_id)
    if not isinstance(row, Mapping):
        raise HazopFacilityCampaignError(
            f"HAZOP runtime result has no component row: {component_id}"
        )
    if row.get("status") != "CONSEQUENCE_BRANCHES_EVALUATED":
        raise HazopFacilityCampaignError(
            f"component {component_id} is not fully HAZOP-evaluated: {row.get('status')}"
        )
    branches = row.get("branches")
    if not isinstance(branches, Sequence) or isinstance(branches, (str, bytes)):
        raise HazopFacilityCampaignError(
            f"component {component_id} has no branch list"
        )
    if len(branches) != 1:
        raise HazopFacilityCampaignError(
            f"component {component_id} has {len(branches)} active HAZOP branches; "
            "explicit branch probabilities are required before campaign aggregation"
        )
    branch = branches[0]
    if not isinstance(branch, Mapping):
        raise HazopFacilityCampaignError(
            f"component {component_id} branch is not a mapping"
        )
    result = branch.get("result")
    if not isinstance(result, Mapping) or result.get("status") != "CONSEQUENCE_EVALUATED":
        raise HazopFacilityCampaignError(
            f"component {component_id} HAZOP branch consequence is not evaluated"
        )
    consequence = result.get("consequence")
    if not isinstance(consequence, Mapping):
        raise HazopFacilityCampaignError(
            f"component {component_id} has no consequence payload"
        )
    risk = branch.get("risk")
    if not isinstance(risk, Mapping) or risk.get("status") != "AVAILABLE_CURRENT_WEATHER_IR":
        raise HazopFacilityCampaignError(
            f"component {component_id} has no explicit current-weather IR/frequency binding"
        )
    risk_atom = risk.get("risk_atom")
    if not isinstance(risk_atom, Mapping):
        raise HazopFacilityCampaignError(
            f"component {component_id} has no explicit literature risk atom"
        )
    selection = row.get("selection")
    if not isinstance(selection, Mapping):
        raise HazopFacilityCampaignError(
            f"component {component_id} has no HAZOP selection record"
        )
    return branch, consequence, risk, selection


def _validate_ignition(consequence: Mapping[str, Any], component_id: str) -> dict[str, Any]:
    data = consequence.get("data")
    reported = data.get("ignition_branch_probabilities") if isinstance(data, Mapping) else None
    if not isinstance(reported, Mapping) or set(reported) != set(IGNITION_BRANCHES):
        raise HazopFacilityCampaignError(
            f"component {component_id} consequence lacks the complete outdoor ignition branch set"
        )
    probabilities = {
        branch: _probability(
            reported[branch],
            f"{component_id}.ignition_branch_probabilities[{branch}]",
        )
        for branch in IGNITION_BRANCHES
    }
    if not math.isclose(sum(probabilities.values()), 1.0, rel_tol=0.0, abs_tol=1.0e-10):
        raise HazopFacilityCampaignError(
            f"component {component_id} ignition branch probabilities do not close to one"
        )
    return {
        "status": "AVAILABLE_IGNITION_BRANCHES",
        "branch_probabilities": probabilities,
        "frequency_inference_performed": False,
        "reason": "provider consequence ignition branches passed through HAZOP campaign bridge",
    }


def _snapshot_from_hazop_runtime(
    runtime_result: Mapping[str, Any],
    *,
    expected_component_ids: Sequence[str],
) -> dict[str, Any]:
    if runtime_result.get("status") != "FACILITY_HAZOP_RUNTIME_EVALUATED":
        raise HazopFacilityCampaignError(
            "an evaluated HAZOP facility runtime result is required"
        )
    facility_id = _name(runtime_result.get("facility_id"), "runtime_result.facility_id")
    components_raw = runtime_result.get("components")
    if not isinstance(components_raw, Mapping) or not components_raw:
        raise HazopFacilityCampaignError("runtime result components must be nonempty")
    component_ids = tuple(sorted(str(component_id) for component_id in components_raw))
    expected = tuple(sorted(_name(value, "expected_component_ids[]") for value in expected_component_ids))
    if expected and set(expected) != set(component_ids):
        raise HazopFacilityCampaignError(
            "expected_component_ids must exactly match the HAZOP runtime component set"
        )
    components: dict[str, Any] = {}
    for component_id in component_ids:
        branch, consequence, risk, selection = _selected_single_branch(runtime_result, component_id)
        release_path = consequence.get("equipment_release_path")
        if not isinstance(release_path, Mapping) or release_path.get("status") != "AVAILABLE_PROVIDER_RELEASE_PATH":
            raise HazopFacilityCampaignError(
                f"component {component_id} has no accepted provider release path"
            )
        components[component_id] = {
            "status": "ACCEPTED",
            "component_id": component_id,
            "selection": copy.deepcopy(dict(selection)),
            "selected_hazop_scenario_id": branch.get("scenario_id"),
            "selected_hazop_scenario_family": branch.get("scenario_family"),
            "equipment_release_path": copy.deepcopy(dict(release_path)),
            "ignition": _validate_ignition(consequence, component_id),
            "risk": copy.deepcopy(dict(risk)),
            # The consequence monitor's service timing is retained when it is
            # present.  Missing timing stays missing; it is never replaced by
            # an invented zero-duration measurement.
            "result": copy.deepcopy(dict(consequence)),
        }
    conditional = runtime_result.get("conditional_current_weather_risk")
    conditional = conditional if isinstance(conditional, Mapping) else {}
    return {
        "schema": "prism.hazop_facility_realtime_snapshot.v1",
        "facility_id": facility_id,
        "status": "ACCEPTED",
        "component_count": len(components),
        "components": components,
        "aggregate": {
            "current_weather_ir_available": bool(conditional.get("annual_ir_low_high_by_receptor")),
            "current_weather_annual_ir_low_high": copy.deepcopy(
                conditional.get("annual_ir_low_high_by_receptor")
            ),
            "conditional_current_weather_expected_death_fn_available": False,
            "current_weather_frequency_sensitivity_ir_low_high": None,
            "release_inference": False,
            "frequency_learning": False,
            "facility_annual_risk_promotion": False,
            "processing_time": {
                "status": "REPORTED_BY_HAZOP_RUNTIME_COMPONENTS_WHEN_PRESENT",
                "measurement_policy": (
                    "timing is copied from the consequence monitor when present; "
                    "missing timing remains unavailable"
                ),
            },
        },
        "runtime_result_digest": canonical_digest(dict(runtime_result)),
    }


def build_hazop_facility_campaign_result(
    runtime_result: Mapping[str, Any],
    *,
    annual_conditions: Sequence[Mapping[str, Any]],
    scenario_bindings: Sequence[Mapping[str, Any]],
    expected_component_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Join one HAZOP-selected runtime branch per component to the facility ledger.

    ``scenario_bindings`` uses the existing realtime-campaign contract and adds
    one required field, ``hazop_scenario_id``.  That field prevents a reviewed
    annual consequence or frequency row from being attached to a different
    mode-specific HAZOP branch.
    """
    if not isinstance(runtime_result, Mapping):
        raise TypeError("runtime_result must be a mapping")
    snapshot = _snapshot_from_hazop_runtime(
        runtime_result,
        expected_component_ids=expected_component_ids,
    )
    components = snapshot["components"]
    if not isinstance(scenario_bindings, Sequence) or isinstance(scenario_bindings, (str, bytes)):
        raise HazopFacilityCampaignError("scenario_bindings must be a sequence")
    normalized_bindings: list[dict[str, Any]] = []
    binding_components: set[str] = set()
    for index, raw in enumerate(scenario_bindings):
        if not isinstance(raw, Mapping):
            raise HazopFacilityCampaignError(f"scenario_bindings[{index}] must be a mapping")
        component_id = _name(raw.get("component_id"), f"scenario_bindings[{index}].component_id")
        if component_id not in components:
            raise HazopFacilityCampaignError(
                f"scenario binding references component absent from HAZOP runtime: {component_id}"
            )
        scenario_id = _name(
            raw.get("hazop_scenario_id"),
            f"scenario_bindings[{index}].hazop_scenario_id",
        )
        selected_id = components[component_id].get("selected_hazop_scenario_id")
        if scenario_id != selected_id:
            raise HazopFacilityCampaignError(
                f"scenario binding HAZOP id does not match selected branch for {component_id}: "
                f"{scenario_id!r} != {selected_id!r}"
            )
        selected_family = components[component_id].get("selected_hazop_scenario_family")
        families = raw.get("scenario_families")
        if not isinstance(families, Sequence) or isinstance(families, (str, bytes)) or selected_family not in families:
            raise HazopFacilityCampaignError(
                f"scenario binding for {component_id} does not declare the selected HAZOP family"
            )
        binding_components.add(component_id)
        normalized_bindings.append(dict(raw))
    required_components = set(components)
    if binding_components != required_components:
        missing = sorted(required_components - binding_components)
        raise HazopFacilityCampaignError(
            "every HAZOP-evaluated component needs an explicit scenario binding; "
            f"missing={missing}"
        )
    campaign = build_realtime_facility_campaign_result(
        snapshot,
        annual_conditions=annual_conditions,
        scenario_bindings=normalized_bindings,
        expected_component_ids=tuple(sorted(required_components)),
    )
    # Build the existing facility ledger immediately so the HAZOP handoff
    # exposes component-to-facility IR/F-N aggregation in one auditable result.
    # The ledger itself retains operator-limited/provider/validation blockers;
    # this call never turns a conditional diagnostic sum into qualified QRA.
    facility_ledger = merge_facility_campaign_results(
        [campaign],
        expected_component_ids=tuple(sorted(required_components)),
    )
    return {
        "schema_version": "prism.hazop_facility_campaign_handoff.v1",
        "status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "facility_id": snapshot["facility_id"],
        "runtime_result_digest": snapshot["runtime_result_digest"],
        "snapshot": snapshot,
        "campaign": campaign,
        "facility_ledger": facility_ledger,
        "policy": {
            "hazop_scenario_id_bound": True,
            "one_active_hazop_branch_per_component": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created_by_prism": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
        },
    }


__all__ = [
    "HazopFacilityCampaignError",
    "build_hazop_facility_campaign_result",
]
