"""Rebind a diagnostic vertical-handoff campaign into one facility namespace.

The vertical outlet diagnostic was originally generated as a separate campaign
with its own facility id and event namespace.  This module makes the physical
scope merge explicit: event ids, asset/component ids, provider packet ids, and
the facility id are all remapped together.  It never turns the uncomputed area
bins or synthetic handoff into a qualified facility result.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def _event_mapping(event_id: str, *, namespace: str) -> str:
    prefix, separator, suffix = event_id.partition("/")
    if not separator or not suffix:
        raise ValueError(f"vertical campaign event id must contain a suffix: {event_id}")
    return f"{namespace.rstrip('/')}/{suffix}"


def rebind_vertical_handoff_campaign_result(
    result: Mapping[str, Any],
    *,
    facility_id: str,
    namespace: str,
    asset_id: str,
    component_id: str,
    receptor_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a namespaced result suitable for explicit facility merging."""
    output = copy.deepcopy(dict(result))
    events = output.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("vertical campaign result must contain a nonempty events array")
    old_event_ids = [
        row.get("id") for row in events
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    ]
    if len(old_event_ids) != len(events) or len(set(old_event_ids)) != len(old_event_ids):
        raise ValueError("vertical campaign events must have unique string ids")
    event_ids = {old: _event_mapping(old, namespace=namespace) for old in old_event_ids}
    provider_event_ids = {
        old.replace("/terminal-valve/", "/terminal_pipe/", 1):
        new.replace("/terminal-valve/", "/provider/terminal_pipe/", 1)
        for old, new in event_ids.items()
        if "/terminal-valve/" in old
    }

    def map_event(value: Any) -> Any:
        if isinstance(value, str):
            if value in event_ids:
                return event_ids[value]
            if value in provider_event_ids:
                return provider_event_ids[value]
        return value

    def update_row(row: Any) -> None:
        if not isinstance(row, dict):
            return
        if "id" in row:
            row["id"] = map_event(row["id"])
        if "event_id" in row:
            row["event_id"] = map_event(row["event_id"])
        if row.get("asset_id") == "terminal-valve":
            row["asset_id"] = asset_id
        if row.get("model_component_id") == "terminal_pipe":
            row["model_component_id"] = component_id
        if row.get("component_id") == "terminal_pipe":
            row["component_id"] = component_id
        identity = row.get("provider_packet_identity")
        if isinstance(identity, dict):
            identity["event_id"] = map_event(identity.get("event_id"))
            if identity.get("component_id") == "terminal_pipe":
                identity["component_id"] = component_id

    receptor_mapping = dict(receptor_map or {})
    if receptor_mapping:
        risk_atoms = output.get("risk_atoms")
        if not isinstance(risk_atoms, list):
            raise ValueError("vertical campaign receptor mapping requires a risk_atoms array")
        for atom in risk_atoms:
            if not isinstance(atom, dict):
                raise ValueError("vertical campaign risk atoms must be objects")
            harm = atom.get("receptor_harm_low_high")
            if not isinstance(harm, dict):
                raise ValueError("vertical campaign risk atom has no receptor harm map")
            remapped: dict[str, list[float]] = {}
            for source, endpoints in harm.items():
                if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
                    raise ValueError("vertical campaign receptor harm endpoints must have two values")
                target = receptor_mapping.get(str(source), str(source))
                values = [float(endpoints[0]), float(endpoints[1])]
                existing = remapped.get(target)
                if existing is None:
                    remapped[target] = values
                else:
                    # A declared many-to-one map represents one facility
                    # receptor. Use the conservative endpoint maximum instead
                    # of counting the same person several times.
                    remapped[target] = [max(existing[0], values[0]), max(existing[1], values[1])]
            atom["receptor_harm_low_high"] = remapped
            atom["expected_deaths_low_high"] = [
                sum(values[endpoint] for values in remapped.values())
                for endpoint in range(2)
            ]

    for key in ("events", "cases", "uncomputed_cases", "risk_atoms"):
        rows = output.get(key)
        if isinstance(rows, list):
            for row in rows:
                update_row(row)
    coverage = output.get("coverage")
    if isinstance(coverage, dict):
        by_component = coverage.get("by_component")
        if isinstance(by_component, list):
            for row in by_component:
                if isinstance(row, dict) and row.get("component_id") == "terminal_pipe":
                    row["component_id"] = component_id
    output["facility_id"] = facility_id
    output["source_facility_id"] = result.get("facility_id")
    output["source_campaign_digest"] = result.get("campaign_digest")
    output["scope_provenance"] = (
        f"{result.get('scope_provenance', 'vertical handoff campaign')}; "
        f"explicit facility namespace rebind to {facility_id}"
    )
    output["vertical_handoff_rebind"] = {
        "schema_version": "prism.vertical_handoff_campaign_rebind.v1",
        "source_facility_id": result.get("facility_id"),
        "target_facility_id": facility_id,
        "source_campaign_digest": result.get("campaign_digest"),
        "namespace": namespace,
        "event_count": len(events),
        "event_id_map": event_ids,
        "provider_event_id_map": provider_event_ids,
        "asset_id": asset_id,
        "component_id": component_id,
        "receptor_map": receptor_mapping,
        "receptor_collapse_policy": "many_to_one_endpoint_maximum" if receptor_mapping else None,
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "The separate vertical-handoff diagnostic is namespaced as a disjoint facility component. "
            "Only its existing executed cases are merged; pending area bins and synthetic handoff limits remain explicit."
        ),
    }
    return output


__all__ = ["rebind_vertical_handoff_campaign_result"]
