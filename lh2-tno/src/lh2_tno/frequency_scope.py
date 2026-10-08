"""Fail-closed frequency-scope audit for generic equipment manifests."""
from __future__ import annotations

from .equipment_manifest import EquipmentManifest, audit_manifest
from .frequency import FrequencyPlan, generate_events


def _component_rows(manifest: EquipmentManifest, plan: FrequencyPlan) -> list[dict]:
    selected: dict[str, list] = {}
    for asset in plan.assets:
        selected.setdefault(asset.model_component_id, []).append(asset)
    excluded = plan.excluded_model_components
    rows = []
    for component in manifest.components:
        if component.id in selected:
            assets = selected[component.id]
            rows.append({
                "component_id": component.id,
                "status": "SELECTED",
                "frequency_asset_ids": [asset.id for asset in assets],
                "profiles": [asset.profile for asset in assets],
                "physical_scope_ids": [scope for asset in assets for scope in asset.physical_scope_ids],
                "count": sum(asset.count for asset in assets),
                "provenance": [asset.classification_basis for asset in assets],
            })
        elif component.id in excluded:
            rows.append({
                "component_id": component.id,
                "status": "EXCLUDED",
                "reason": excluded[component.id],
            })
        else:
            rows.append({
                "component_id": component.id,
                "status": "UNCOMPUTED",
                "reason": "component has no selected frequency asset or explicit exclusion",
            })
    return rows


def audit_frequency_scope(manifest: EquipmentManifest, plan: FrequencyPlan) -> dict:
    """Return a frequency-scope report without inventing missing profiles."""

    manifest_audit = audit_manifest(manifest)
    result = {
        "status": "PARTIAL",
        "manifest_status": manifest_audit["status"],
        "facility_id": manifest.facility_id,
        "manifest_digest": manifest.digest(),
        "frequency_plan_id": plan.id,
        "frequency_plan_digest": plan.digest(),
        "component_coverage": _component_rows(manifest, plan),
        "generated_event_count": 0,
        "events": [],
        "blocking_reasons": [],
        "physical_validation_claim": False,
        "promotion_policy": {
            "profiles_are_not_inferred_from_component_kind": True,
            "missing_components_are_not_given_zero_frequency": True,
            "excluded_components_require_a_reason": True,
            "consequence_requests_are_not_created_by_this_audit": True,
            "facility_risk_requires": "EXECUTABLE manifest, complete frequency scope, and executable consequence routes",
        },
    }
    if manifest_audit["status"] != "EXECUTABLE":
        result["blocking_reasons"].append(
            "equipment manifest must be EXECUTABLE before frequency events can be generated"
        )
        result["blocking_reasons"].extend(manifest_audit["blocking_reasons"])
        return result
    missing = [
        row["component_id"] for row in result["component_coverage"]
        if row["status"] == "UNCOMPUTED"
    ]
    if missing:
        result["blocking_reasons"].append(
            "component has no selected frequency asset or explicit exclusion: "
            + ", ".join(missing)
        )
        return result
    try:
        facility = manifest.to_facility()
        events = generate_events(facility, plan)
    except (ValueError, TypeError) as error:
        result["blocking_reasons"].append(str(error))
        return result
    result["events"] = [event.model_dump(mode="json") for event in events]
    result["generated_event_count"] = len(events)
    selected_or_excluded = {
        row["component_id"] for row in result["component_coverage"]
        if row["status"] in {"SELECTED", "EXCLUDED"}
    }
    if len(selected_or_excluded) != len(manifest.components):
        result["blocking_reasons"].append(
            "one or more components remain UNCOMPUTED in the frequency scope"
        )
    if not result["blocking_reasons"]:
        result["status"] = "EXECUTABLE"
    return result
