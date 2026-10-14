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
from .hazop_scenario_trace_audit import audit_hazop_scenario_trace
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
    component_count = runtime_result.get("component_count")
    if (
        isinstance(component_count, bool)
        or not isinstance(component_count, int)
        or component_count != len(components_raw)
    ):
        raise HazopFacilityCampaignError(
            "runtime result component_count does not match components"
        )
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
        boundaries = release_path.get("boundaries")
        if not isinstance(boundaries, Sequence) or isinstance(boundaries, (str, bytes)) or not boundaries:
            raise HazopFacilityCampaignError(
                f"component {component_id} provider release path has no explicit boundaries"
            )
        for boundary in boundaries:
            if isinstance(boundary, Mapping) and boundary.get("component_id") not in {
                None,
                component_id,
            }:
                raise HazopFacilityCampaignError(
                    f"component {component_id} provider boundary belongs to another component"
                )
        components[component_id] = {
            "status": "ACCEPTED",
            "component_id": component_id,
            "selection": copy.deepcopy(dict(selection)),
            "selected_hazop_scenario_id": branch.get("scenario_id"),
            "selected_hazop_scenario_family": branch.get("scenario_family"),
            "selected_operating_mode": selection.get("operating_mode"),
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
        selected_mode = components[component_id].get("selected_operating_mode")
        if selected_mode is not None:
            binding_mode = _name(
                raw.get("operating_mode"),
                f"scenario_bindings[{index}].operating_mode",
            )
            if binding_mode != selected_mode:
                raise HazopFacilityCampaignError(
                    f"scenario binding operating_mode does not match selected HAZOP mode for "
                    f"{component_id}: {binding_mode!r} != {selected_mode!r}"
                )
        selected_risk = components[component_id].get("risk")
        selected_atom = selected_risk.get("risk_atom") if isinstance(selected_risk, Mapping) else None
        event_id = _name(raw.get("event_id"), f"scenario_bindings[{index}].event_id")
        asset_id = _name(raw.get("asset_id"), f"scenario_bindings[{index}].asset_id")
        if not isinstance(selected_atom, Mapping):
            raise HazopFacilityCampaignError(
                f"component {component_id} has no risk atom for scenario identity binding"
            )
        if event_id != selected_atom.get("event_id"):
            raise HazopFacilityCampaignError(
                f"scenario binding event_id does not match provider risk atom for {component_id}"
            )
        if asset_id != selected_atom.get("asset_id"):
            raise HazopFacilityCampaignError(
                f"scenario binding asset_id does not match provider risk atom for {component_id}"
            )
        if selected_atom.get("frequency_is_not_inferred") is not True:
            raise HazopFacilityCampaignError(
                f"component {component_id} risk atom does not prove an explicit literature frequency"
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
    scenario_trace_audit = audit_hazop_scenario_trace(
        {
            "schema_version": "prism.hazop_facility_campaign_handoff.v1",
            "status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
            "campaign": campaign,
        }
    )
    if scenario_trace_audit["status"] != "HAZOP_SCENARIO_TRACE_COMPLETE":
        raise HazopFacilityCampaignError(
            "HAZOP campaign scenario identity trace failed: "
            + "; ".join(scenario_trace_audit.get("errors", []))
        )
    return {
        "schema_version": "prism.hazop_facility_campaign_handoff.v1",
        "status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "facility_id": snapshot["facility_id"],
        "runtime_result_digest": snapshot["runtime_result_digest"],
        "snapshot": snapshot,
        "campaign": campaign,
        "facility_ledger": facility_ledger,
        "hazop_scenario_trace_audit": scenario_trace_audit,
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


def _combine_hazop_branch_campaigns(
    campaigns: Sequence[Mapping[str, Any]],
    *,
    facility_id: str,
    expected_component_ids: Sequence[str],
) -> dict[str, Any]:
    """Combine branch campaigns into one ledger input without re-owning assets."""

    if not campaigns:
        raise HazopFacilityCampaignError("at least one HAZOP branch campaign is required")
    events: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    uncomputed: list[dict[str, Any]] = []
    risk_atoms: list[dict[str, Any]] = []
    annual_conditions: dict[str, dict[str, Any]] = {}
    exclusions: dict[str, str] = {}
    component_rows: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    provider_packet_case_count = 0
    qualified_provider_packet_case_count = 0
    synthetic_release_horizon_present = False
    generated_frequency = 0.0
    timing_rows: list[Mapping[str, Any]] = []
    for index, campaign in enumerate(campaigns):
        if not isinstance(campaign, Mapping):
            raise HazopFacilityCampaignError(f"branch campaign {index} is not a mapping")
        if campaign.get("facility_id") != facility_id:
            raise HazopFacilityCampaignError(
                f"branch campaign {index} belongs to another facility"
            )
        for event in campaign.get("events", ()):
            if not isinstance(event, Mapping) or not event.get("id"):
                raise HazopFacilityCampaignError(f"branch campaign {index} has an invalid event")
            event_id = str(event["id"])
            if event_id in seen_event_ids:
                raise HazopFacilityCampaignError(
                    "the same literature event ID appears in multiple HAZOP branches; "
                    "provide distinct event identities or a reviewed shared-event partition: "
                    + event_id
                )
            seen_event_ids.add(event_id)
            events.append(copy.deepcopy(dict(event)))
        for condition in campaign.get("annual_conditions", ()):
            if not isinstance(condition, Mapping) or not condition.get("id"):
                raise HazopFacilityCampaignError(
                    f"branch campaign {index} has an invalid annual condition"
                )
            condition_id = str(condition["id"])
            previous = annual_conditions.get(condition_id)
            normalized = copy.deepcopy(dict(condition))
            if previous is not None and canonical_digest(previous) != canonical_digest(normalized):
                raise HazopFacilityCampaignError(
                    f"annual condition {condition_id} conflicts across HAZOP branches"
                )
            annual_conditions[condition_id] = normalized
        for key in ("cases", "uncomputed_cases", "risk_atoms"):
            values = campaign.get(key, ())
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise HazopFacilityCampaignError(
                    f"branch campaign {index} has invalid {key}"
                )
            target = {
                "cases": cases,
                "uncomputed_cases": uncomputed,
                "risk_atoms": risk_atoms,
            }[key]
            target.extend(copy.deepcopy(list(values)))
        raw_exclusions = campaign.get("excluded_model_components", {})
        if isinstance(raw_exclusions, Mapping):
            for component_id, reason in raw_exclusions.items():
                existing = exclusions.get(str(component_id))
                if existing is not None and existing != str(reason):
                    raise HazopFacilityCampaignError(
                        f"component exclusion conflicts across HAZOP branches: {component_id}"
                    )
                exclusions[str(component_id)] = str(reason)
        coverage = campaign.get("coverage")
        if isinstance(coverage, Mapping):
            generated_frequency += float(coverage.get("generated_initiation_frequency_per_year") or 0.0)
            rows = coverage.get("by_component")
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                component_rows.extend(copy.deepcopy(list(rows)))
        provider_packet_case_count += int(campaign.get("provider_packet_case_count") or 0)
        qualified_provider_packet_case_count += int(
            campaign.get("qualified_provider_packet_case_count") or 0
        )
        synthetic_release_horizon_present |= campaign.get("synthetic_release_horizon_present") is True
        timing = campaign.get("timing")
        if isinstance(timing, Mapping):
            timing_rows.append(timing)
    return {
        "schema_version": "prism.hazop_facility_branch_campaign_result.v1",
        "status": "PARTIAL_DECLARED_SCOPE",
        "facility_id": facility_id,
        "campaign_digest": canonical_digest(
            {"branch_campaign_digests": [c.get("campaign_digest") for c in campaigns]}
        ),
        "scope_provenance": "explicit HAZOP branch partition and annual scenario bindings",
        "events": events,
        "annual_conditions": [annual_conditions[key] for key in sorted(annual_conditions)],
        "cases": cases,
        "uncomputed_cases": uncomputed,
        "risk_atoms": risk_atoms,
        "excluded_model_components": exclusions,
        "coverage": {
            "generated_initiation_frequency_per_year": generated_frequency,
            "fully_executed_case_weighted_frequency_per_year": 0.0,
            "fraction_of_generated_initiation_frequency": None,
            "meaning": "explicit HAZOP branch coverage; qualified facility risk remains closed",
            "by_component": component_rows,
        },
        "declared_scope_numerically_complete": False,
        "synthetic_release_horizon_present": synthetic_release_horizon_present,
        "known_contribution_annual_ir_low_high": None,
        "known_contribution_expected_death_fn_low_high": None,
        "declared_scope_annual_ir_low_high": None,
        "declared_scope_expected_death_fn_low_high": None,
        "total_facility_annual_ir_low_high": None,
        "total_facility_expected_death_fn_low_high": None,
        "timing": {
            "branch_campaign_count": len(campaigns),
            "branch_rows": timing_rows,
            "distribution": "explicit HAZOP branch campaign set; not sustained throughput",
        },
        "provider_packet_case_count": provider_packet_case_count,
        "qualified_provider_packet_case_count": qualified_provider_packet_case_count,
        "provider_packet_promoted": False,
        "provider_packet_missing_evidence_cases": [],
        "physical_validation_claim": False,
        "complete_facility_qra_claim": False,
        "one_hz_fresh_physics_demonstrated": False,
        "semantics": {
            "branch_partition": "branch probability is multiplied into the explicit release-branch probability for each annual binding",
            "facility_promotion": "always withheld until scope, provider qualification and physical validation gates close",
        },
    }


def build_hazop_facility_campaign_branches(
    runtime_result: Mapping[str, Any],
    *,
    annual_conditions: Sequence[Mapping[str, Any]],
    scenario_bindings: Sequence[Mapping[str, Any]],
    branch_probabilities: Mapping[str, Any],
    branch_partition_groups: Mapping[str, Any],
    expected_component_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a facility ledger from multiple HAZOP branches with explicit partitions.

    Each selected HAZOP scenario is evaluated in its own campaign first.  The
    supplied branch probability is multiplied into that scenario's explicit
    release-branch probability.  Probabilities are required to close to one
    within each named partition group; no probability is inferred from sensors,
    HAZOP row order, or equal weighting.
    """
    if not isinstance(runtime_result, Mapping):
        raise TypeError("runtime_result must be a mapping")
    facility_id = _name(runtime_result.get("facility_id"), "runtime_result.facility_id")
    components_raw = runtime_result.get("components")
    if not isinstance(components_raw, Mapping) or not components_raw:
        raise HazopFacilityCampaignError("runtime result components must be nonempty")
    component_ids = tuple(sorted(str(value) for value in components_raw))
    expected = tuple(sorted(_name(value, "expected_component_ids[]") for value in expected_component_ids))
    if expected and set(expected) != set(component_ids):
        raise HazopFacilityCampaignError(
            "expected_component_ids must exactly match the HAZOP runtime component set"
        )
    branch_rows: dict[tuple[str, str], Mapping[str, Any]] = {}
    for component_id in component_ids:
        row = components_raw[component_id]
        if not isinstance(row, Mapping) or row.get("status") != "CONSEQUENCE_BRANCHES_EVALUATED":
            raise HazopFacilityCampaignError(
                f"component {component_id} is not fully HAZOP-evaluated"
            )
        branches = row.get("branches")
        if not isinstance(branches, Sequence) or isinstance(branches, (str, bytes)) or not branches:
            raise HazopFacilityCampaignError(f"component {component_id} has no active HAZOP branches")
        for branch in branches:
            if not isinstance(branch, Mapping):
                raise HazopFacilityCampaignError(f"component {component_id} has an invalid branch")
            scenario_id = _name(branch.get("scenario_id"), f"{component_id}.scenario_id")
            key = (component_id, scenario_id)
            if key in branch_rows:
                raise HazopFacilityCampaignError(f"duplicate HAZOP branch: {component_id}/{scenario_id}")
            branch_rows[key] = branch
    probability_map = {
        _name(key, "branch_probabilities key"): _probability(value, f"branch_probabilities[{key}]")
        for key, value in branch_probabilities.items()
    }
    group_map = {
        _name(key, "branch_partition_groups key"): _name(value, f"branch_partition_groups[{key}]")
        for key, value in branch_partition_groups.items()
    }
    scenario_ids = {scenario_id for _, scenario_id in branch_rows}
    if set(probability_map) != scenario_ids or set(group_map) != scenario_ids:
        raise HazopFacilityCampaignError(
            "branch probabilities and partition groups must cover exactly every selected HAZOP scenario_id"
        )
    partitions: dict[str, float] = {}
    for scenario_id, probability in probability_map.items():
        group = group_map[scenario_id]
        partitions[group] = partitions.get(group, 0.0) + probability
    if any(not math.isclose(value, 1.0, rel_tol=0.0, abs_tol=1.0e-10) for value in partitions.values()):
        raise HazopFacilityCampaignError(
            "each HAZOP branch partition group must close to one"
        )
    binding_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for index, raw in enumerate(scenario_bindings):
        if not isinstance(raw, Mapping):
            raise HazopFacilityCampaignError(f"scenario_bindings[{index}] must be a mapping")
        component_id = _name(raw.get("component_id"), f"scenario_bindings[{index}].component_id")
        scenario_id = _name(raw.get("hazop_scenario_id"), f"scenario_bindings[{index}].hazop_scenario_id")
        key = (component_id, scenario_id)
        if key not in branch_rows:
            raise HazopFacilityCampaignError(
                f"scenario binding references an unselected HAZOP branch: {component_id}/{scenario_id}"
            )
        binding_groups.setdefault(key, []).append(dict(raw))
    if set(binding_groups) != set(branch_rows):
        missing = sorted(set(branch_rows) - set(binding_groups))
        raise HazopFacilityCampaignError(
            "every selected HAZOP branch needs an explicit scenario binding: " + str(missing)
        )
    branch_campaigns: list[dict[str, Any]] = []
    for (component_id, scenario_id), branch in sorted(branch_rows.items()):
        row = components_raw[component_id]
        branch_runtime = dict(runtime_result)
        branch_runtime["component_count"] = 1
        branch_runtime["components"] = {
            component_id: {
                **dict(row),
                "branches": [dict(branch)],
            }
        }
        risk = branch.get("risk")
        annual_ir = risk.get("annual_ir_low_high") if isinstance(risk, Mapping) else None
        branch_runtime["conditional_current_weather_risk"] = {
            "annual_ir_low_high_by_receptor": copy.deepcopy(annual_ir),
        }
        adjusted_bindings: list[dict[str, Any]] = []
        branch_probability = probability_map[scenario_id]
        for binding in binding_groups[(component_id, scenario_id)]:
            release_probability = _probability(
                binding.get("release_branch_probability"),
                f"{component_id}/{scenario_id}.release_branch_probability",
            )
            adjusted = dict(binding)
            adjusted["release_branch_probability"] = release_probability * branch_probability
            adjusted_bindings.append(adjusted)
        handoff = build_hazop_facility_campaign_result(
            branch_runtime,
            annual_conditions=annual_conditions,
            scenario_bindings=adjusted_bindings,
            expected_component_ids=(component_id,),
        )
        branch_campaigns.append(handoff["campaign"])
    combined = _combine_hazop_branch_campaigns(
        branch_campaigns,
        facility_id=facility_id,
        expected_component_ids=component_ids,
    )
    facility_ledger = merge_facility_campaign_results(
        [combined],
        expected_component_ids=component_ids,
    )
    scenario_trace_audit = audit_hazop_scenario_trace(
        {
            "schema_version": "prism.hazop_facility_campaign_branches.v1",
            "status": "HAZOP_BRANCH_CAMPAIGNS_BUILT_OPERATOR_LIMITED",
            "campaign": combined,
        }
    )
    if scenario_trace_audit["status"] != "HAZOP_SCENARIO_TRACE_COMPLETE":
        raise HazopFacilityCampaignError(
            "HAZOP branch campaign scenario identity trace failed: "
            + "; ".join(scenario_trace_audit.get("errors", []))
        )
    return {
        "schema_version": "prism.hazop_facility_campaign_branches.v1",
        "status": "HAZOP_BRANCH_CAMPAIGNS_BUILT_OPERATOR_LIMITED",
        "facility_id": facility_id,
        "branch_probabilities": probability_map,
        "branch_partition_groups": group_map,
        "branch_campaigns": branch_campaigns,
        "campaign": combined,
        "facility_ledger": facility_ledger,
        "hazop_scenario_trace_audit": scenario_trace_audit,
        "policy": {
            "branch_partition_explicit": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
        },
    }


__all__ = [
    "HazopFacilityCampaignError",
    "build_hazop_facility_campaign_result",
    "build_hazop_facility_campaign_branches",
]
