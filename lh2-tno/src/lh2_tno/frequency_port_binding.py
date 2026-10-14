"""Bind reviewed accident-port identities to literature frequency events.

Component-level frequency rows are useful for screening, but a facility
campaign must identify the reviewed outlet that owns the rate.  This module
accepts an explicit crosswalk supplied by the analyst; it never derives a
port from a provider packet, an event name, or a sensor value.  The result is
still diagnostic when the facility or provider gates remain open.
"""
from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping, Sequence
import json
from typing import Any


SCHEMA = "prism.frequency_port_crosswalk.v1"
RESULT_AUDIT_SCHEMA = "prism.frequency_port_binding_audit.v1"


class FrequencyPortBindingError(ValueError):
    """Raised when an explicit frequency-port crosswalk cannot be applied."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FrequencyPortBindingError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrequencyPortBindingError(f"{label} must be a non-empty string")
    return value.strip()


def _ports(value: Any, label: str, *, expected: int | None = None) -> list[str]:
    if not isinstance(value, list) or not value:
        raise FrequencyPortBindingError(f"{label} must be a non-empty string array")
    values = [_text(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if len(set(values)) != len(values):
        raise FrequencyPortBindingError(f"{label} must not contain duplicate ports")
    if expected is not None and len(values) != expected:
        raise FrequencyPortBindingError(
            f"{label} must contain exactly {expected} reviewed port(s)"
        )
    return values


def _crosswalk_rows(crosswalk: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    crosswalk = _object(crosswalk, "crosswalk")
    if crosswalk.get("schema_version") != SCHEMA:
        raise FrequencyPortBindingError(f"crosswalk must be {SCHEMA}")
    rows = crosswalk.get("assets")
    if not isinstance(rows, list) or not rows:
        raise FrequencyPortBindingError("crosswalk.assets must be a non-empty array")
    output: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        row = _object(row, f"crosswalk.assets[{index}]")
        asset_id = _text(row.get("asset_id"), f"crosswalk.assets[{index}].asset_id")
        if asset_id in output:
            raise FrequencyPortBindingError(f"duplicate crosswalk asset_id: {asset_id}")
        _text(row.get("model_component_id"), f"crosswalk.assets[{index}].model_component_id")
        has_default = row.get("port_ids") is not None
        has_by_loc = row.get("port_ids_by_loc") is not None
        if not has_default and not has_by_loc:
            raise FrequencyPortBindingError(
                f"crosswalk asset {asset_id} must declare port_ids or port_ids_by_loc"
            )
        if has_default:
            _ports(row.get("port_ids"), f"crosswalk asset {asset_id}.port_ids")
        if has_by_loc:
            by_loc = row.get("port_ids_by_loc")
            if not isinstance(by_loc, Mapping) or not by_loc:
                raise FrequencyPortBindingError(
                    f"crosswalk asset {asset_id}.port_ids_by_loc must be a non-empty object"
                )
            for loc, values in by_loc.items():
                _text(loc, f"crosswalk asset {asset_id}.port_ids_by_loc key")
                _ports(values, f"crosswalk asset {asset_id}.port_ids_by_loc[{loc}]")
        output[asset_id] = row
    return output


def _request_port_ids(request: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Read an already-resolved provider exit without using it as a crosswalk."""
    for key in ("resolved_release_set", "resolved_release", "resolved_liquid_release"):
        value = request.get(key)
        if value is None:
            continue
        if key == "resolved_release_set":
            value = _object(value, f"request.{key}")
            releases = value.get("releases")
            if not isinstance(releases, list):
                raise FrequencyPortBindingError("request.resolved_release_set.releases must be an array")
            ports = tuple(_text(_object(item, "release").get("port_id"), "release.port_id") for item in releases)
        else:
            release = _object(value, f"request.{key}")
            ports = (_text(release.get("port_id"), f"request.{key}.port_id"),)
        if len(set(ports)) != len(ports):
            raise FrequencyPortBindingError("provider release port IDs must be unique")
        return ports
    return None


def _event_request_rows(campaign: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    routes = campaign.get("event_routes")
    if not isinstance(routes, list):
        raise FrequencyPortBindingError("campaign.event_routes must be an array")
    rows: dict[str, list[Mapping[str, Any]]] = {}
    for index, route in enumerate(routes):
        route = _object(route, f"campaign.event_routes[{index}]")
        event_id = _text(route.get("event_id"), f"campaign.event_routes[{index}].event_id")
        branches = route.get("branches")
        if not isinstance(branches, list):
            raise FrequencyPortBindingError(f"route {event_id}.branches must be an array")
        requests: list[Mapping[str, Any]] = []
        for branch_index, branch in enumerate(branches):
            branch = _object(branch, f"route {event_id}.branches[{branch_index}]")
            request = branch.get("request")
            if isinstance(request, Mapping):
                requests.append(request)
        rows[event_id] = requests
    return rows


def bind_frequency_ports_to_campaign(
    campaign: Mapping[str, Any],
    crosswalk: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply an explicit crosswalk to one campaign's frequency plan.

    The function changes only ``frequency_plan.assets[*].port_ids`` and
    ``port_ids_by_loc``.  Existing provider request identities are checked
    against the resulting generated event identities when the caller later
    executes the normal campaign pipeline.
    """
    campaign = _object(campaign, "campaign")
    plan = _object(campaign.get("frequency_plan"), "campaign.frequency_plan")
    assets = plan.get("assets")
    if not isinstance(assets, list) or not assets:
        raise FrequencyPortBindingError("campaign.frequency_plan.assets must be a non-empty array")
    rows = _crosswalk_rows(crosswalk)
    output = deepcopy(dict(campaign))
    output_plan = deepcopy(dict(plan))
    output_assets: list[dict[str, Any]] = []
    used: set[str] = set()
    event_port_ids: dict[str, tuple[str, ...]] = {}
    for index, raw_asset in enumerate(assets):
        asset = dict(_object(raw_asset, f"campaign.frequency_plan.assets[{index}]"))
        asset_id = _text(asset.get("id"), f"campaign.frequency_plan.assets[{index}].id")
        component_id = _text(
            asset.get("model_component_id"),
            f"campaign.frequency_plan.assets[{index}].model_component_id",
        )
        row = rows.get(asset_id)
        if row is None:
            raise FrequencyPortBindingError(
                f"frequency port crosswalk has no row for asset {asset_id}"
            )
        if row.get("model_component_id") != component_id:
            raise FrequencyPortBindingError(
                f"crosswalk component mismatch for asset {asset_id}: "
                f"{row.get('model_component_id')!r} != {component_id!r}"
            )
        if row.get("port_ids") is not None:
            asset["port_ids"] = _ports(row.get("port_ids"), f"crosswalk asset {asset_id}.port_ids")
        else:
            asset.pop("port_ids", None)
        if row.get("port_ids_by_loc") is not None:
            by_loc = _object(row.get("port_ids_by_loc"), f"crosswalk asset {asset_id}.port_ids_by_loc")
            asset["port_ids_by_loc"] = {
                str(loc): _ports(values, f"crosswalk asset {asset_id}.port_ids_by_loc[{loc}]")
                for loc, values in by_loc.items()
            }
        else:
            asset.pop("port_ids_by_loc", None)
        used.add(asset_id)
        output_assets.append(asset)
    extra = sorted(set(rows) - used)
    if extra:
        raise FrequencyPortBindingError(
            "crosswalk contains assets absent from campaign frequency plan: " + ", ".join(extra)
        )
    output_plan["assets"] = output_assets
    output["frequency_plan"] = output_plan

    # Validate the modified contract before writing it.  This catches invalid
    # port counts for two-sided LOCs while preserving the original campaign
    # route and provider payloads.
    from .campaign import RiskCampaign
    from .frequency import FrequencyPlan, generate_events
    from .equipment_manifest import EquipmentManifest

    validated_plan = FrequencyPlan.model_validate_json(
        json.dumps(output_plan, ensure_ascii=False)
    )
    validated_campaign = RiskCampaign.model_validate_json(
        json.dumps(output, ensure_ascii=False)
    )
    # A normal plan does not serialize events.  Generate those events against
    # the declared equipment manifest so every reviewed outlet is checked on
    # the same facility topology that the campaign runner will use.  Without
    # a manifest we can only validate an attached precomputed catalogue; we
    # deliberately refuse to pretend that asset metadata alone proves the
    # event-to-port binding.
    if manifest is not None:
        manifest_model = EquipmentManifest.model_validate_json(
            json.dumps(dict(manifest), ensure_ascii=False)
        )
        facility = manifest_model.to_facility()
        generated_events = generate_events(facility, validated_plan)
    elif validated_plan.precomputed_events is not None:
        generated_events = validated_plan.precomputed_events
    else:
        raise FrequencyPortBindingError(
            "manifest is required to bind a non-precomputed frequency plan"
        )
    event_port_ids = {
        event.id: tuple(event.port_ids or ()) for event in generated_events
    }
    unbound_events = sorted(event_id for event_id, ports in event_port_ids.items() if not ports)
    if unbound_events:
        raise FrequencyPortBindingError(
            "reviewed frequency crosswalk left events without accident ports: "
            + ", ".join(unbound_events)
        )
    route_requests = _event_request_rows(output)
    missing_routes = sorted(set(event_port_ids) - set(route_requests))
    extra_routes = sorted(set(route_requests) - set(event_port_ids))
    if missing_routes or extra_routes:
        details = []
        if missing_routes:
            details.append("missing routes: " + ", ".join(missing_routes))
        if extra_routes:
            details.append("unknown routes: " + ", ".join(extra_routes))
        raise FrequencyPortBindingError(
            "campaign routes do not match generated frequency events (" + "; ".join(details) + ")"
        )
    mismatches: list[dict[str, Any]] = []
    for event_id, requests in route_requests.items():
        expected = event_port_ids.get(event_id)
        if expected is None:
            continue
        for request_index, request in enumerate(requests):
            observed = _request_port_ids(request)
            if observed is not None and observed != expected:
                mismatches.append({
                    "event_id": event_id,
                    "branch_request_index": request_index,
                    "expected_port_ids": list(expected),
                    "observed_port_ids": list(observed),
                })
    if mismatches:
        raise FrequencyPortBindingError(
            "provider request port identity disagrees with reviewed frequency crosswalk"
        )
    events_with_ports = len(event_port_ids)
    audit = {
        "schema_version": RESULT_AUDIT_SCHEMA,
        "status": "FREQUENCY_PORT_CROSSWALK_BOUND",
        "campaign_id": validated_campaign.id,
        "frequency_plan_id": validated_plan.id,
        "asset_count": len(output_assets),
        "crosswalk_asset_count": len(rows),
        "generated_event_count": len(event_port_ids),
        "generated_port_scoped_event_count": sum(bool(value) for value in event_port_ids.values()),
        "generated_unbound_event_count": len(unbound_events),
        "provider_request_port_mismatch_count": len(mismatches),
        "provider_request_port_mismatches": mismatches,
        "crosswalk_provenance": _object(crosswalk, "crosswalk").get("provenance"),
        "manifest_facility_id": (
            manifest_model.facility_id if manifest is not None else None
        ),
        "frequency_inference_performed": False,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "policy": {
            "port_ids_are_explicit_crosswalk_input": True,
            "provider_ports_are_never_used_to_create_frequency_ports": True,
            "sensor_frequency_learning": False,
            "partial_or_synthetic_provider_chain_remains_partial": True,
        },
    }
    return output, audit


def bind_frequency_ports_to_campaign_result(
    campaign_result: Mapping[str, Any],
    event_port_map: Mapping[str, Sequence[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attach explicit frequency ports to an already executed extension result.

    This is used only for extension campaigns whose source frequency plan is
    no longer serialized.  Every event must be listed; case and risk-atom
    rows are copied with the same explicit identity and checked for agreement.
    """
    result = deepcopy(dict(_object(campaign_result, "campaign_result")))
    events = result.get("events")
    if not isinstance(events, list):
        raise FrequencyPortBindingError("campaign_result.events must be an array")
    normalized: dict[str, tuple[str, ...]] = {}
    for event_id, values in event_port_map.items():
        event_id = _text(event_id, "event_port_map event_id")
        if isinstance(values, (str, bytes)):
            raise FrequencyPortBindingError(
                f"event_port_map[{event_id}] must be a sequence of port IDs, not text"
            )
        normalized[event_id] = tuple(_ports(list(values), f"event_port_map[{event_id}]"))
    mismatches: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for event in events:
        event = _object(event, "campaign_result.events row")
        event_id = _text(event.get("id"), "campaign_result event.id")
        event_ids.add(event_id)
        expected = normalized.get(event_id)
        if expected is None:
            raise FrequencyPortBindingError(f"event_port_map has no row for event {event_id}")
        event["port_ids"] = list(expected)
    extra = sorted(set(normalized) - event_ids)
    if extra:
        raise FrequencyPortBindingError("event_port_map contains unknown events: " + ", ".join(extra))
    for key in ("cases", "uncomputed_cases", "risk_atoms"):
        rows = result.get(key, [])
        if not isinstance(rows, list):
            raise FrequencyPortBindingError(f"campaign_result.{key} must be an array")
        for row in rows:
            row = _object(row, f"campaign_result.{key} row")
            event_id = _text(row.get("event_id"), f"campaign_result.{key}.event_id")
            expected = normalized.get(event_id)
            if expected is None:
                raise FrequencyPortBindingError(f"event_port_map has no row for {event_id}")
            actual = row.get("frequency_port_ids")
            if actual is not None and tuple(actual) != expected:
                mismatches.append({
                    "row_kind": key,
                    "event_id": event_id,
                    "expected_port_ids": list(expected),
                    "actual_port_ids": list(actual),
                })
            row["frequency_port_ids"] = list(expected)
    if mismatches:
        raise FrequencyPortBindingError(
            "campaign result contains a conflicting frequency_port_ids value"
        )
    audit = {
        "schema_version": RESULT_AUDIT_SCHEMA,
        "status": "FREQUENCY_PORT_RESULT_BOUND",
        "event_count": len(events),
        "port_scoped_event_count": len(events),
        "row_mismatch_count": len(mismatches),
        "frequency_inference_performed": False,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "policy": {
            "port_ids_are_explicit_crosswalk_input": True,
            "provider_ports_are_never_used_to_create_frequency_ports": True,
            "sensor_frequency_learning": False,
        },
    }
    return result, audit


__all__ = [
    "SCHEMA",
    "RESULT_AUDIT_SCHEMA",
    "FrequencyPortBindingError",
    "bind_frequency_ports_to_campaign",
    "bind_frequency_ports_to_campaign_result",
]
