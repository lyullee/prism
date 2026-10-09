"""Rebind a campaign to the exact strict packets selected by worklist evidence.

The mixed campaign compiler can legitimately use a reviewed provider catalog,
while a later evidence scan may select a newer packet for the same event.  This
module makes that difference explicit and provides a deterministic way to
replace each request with the selected strict packet before a fresh run.  It
never supplies a packet when the evidence row is missing or non-strict.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .campaign import RiskCampaign
from .provider_release import (
    ProviderReleaseContractError,
    ResolvedGasRelease,
    ResolvedGasReleaseSet,
    ResolvedLiquidRelease,
    build_consequence_request_from_provider_release,
    build_consequence_request_from_provider_release_set,
    load_provider_emergency_relief,
    load_provider_release,
    load_provider_release_set,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _resolve_packet_path(raw: str, packet_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else packet_root / path


def _load_selected_release(
    event_id: str,
    evidence_row: dict[str, Any],
    packet_root: Path,
) -> Any:
    evidence = evidence_row.get("evidence")
    if not isinstance(evidence, dict):
        raise ProviderReleaseContractError(f"worklist evidence has no evidence object: {event_id}")
    if evidence.get("exact_opening_match") is not True or evidence.get("strict_packet_valid") is not True:
        raise ProviderReleaseContractError(f"worklist evidence is not exact/strict: {event_id}")
    paths = evidence.get("resolved_packet_paths")
    if not isinstance(paths, list) or len(paths) != 1 or not isinstance(paths[0], str):
        raise ProviderReleaseContractError(
            f"worklist event requires exactly one selected resolved packet: {event_id}"
        )
    path = _resolve_packet_path(paths[0], packet_root)
    payload = _load_json(path)
    schema = payload.get("provider_export_schema")
    if schema == "prism.resolved_release_set.v1":
        release = load_provider_release_set(path)
    elif payload.get("event_kind") == "emergency_relief":
        release = load_provider_emergency_relief(path)
    else:
        release = load_provider_release(path)
    if release.event_id != event_id:
        raise ProviderReleaseContractError(
            f"selected packet event_id disagrees with worklist: {event_id} != {release.event_id}"
        )
    return release


def _defaults_from_request(request: dict[str, Any]) -> dict[str, Any]:
    defaults = copy.deepcopy(request)
    for key in (
        "component_id",
        "available_mass_kg",
        "source_position_enu_m",
        "source_positions_enu_m",
        "source_input",
        "resolved_release",
        "resolved_release_set",
        "resolved_liquid_release",
        "annual_frequency_per_year",
        "annual_frequency_provenance",
        "frequency_event",
        "initiation_intensity_per_s",
    ):
        defaults.pop(key, None)
    old_termination = defaults.get("release_termination")
    if not isinstance(old_termination, dict):
        raise ProviderReleaseContractError("campaign request lacks release_termination context")
    defaults["release_termination"] = {
        "basis": "provider_declared",
        "time_s": "provider_duration",
        "provenance": "selected exact strict worklist packet; provider clock retained",
    }
    old_time = old_termination.get("time_s")
    times = defaults.get("evaluation_times_s")
    if isinstance(times, list) and isinstance(old_time, (int, float)):
        defaults["evaluation_times_s"] = [time for time in times if time != old_time]
    return defaults


def _request_from_selected_packet(
    current_request: dict[str, Any],
    release: Any,
) -> dict[str, Any]:
    # The selected worklist packet owns thermodynamics and provider history,
    # while the already compiled campaign may have explicitly placed a generic
    # packet at a facility port.  Preserve that reviewed placement by applying
    # the same explicit rebase used by campaign compilation.  Never infer a
    # position when the campaign did not declare one.
    if isinstance(release, ResolvedGasReleaseSet):
        positions = current_request.get("source_positions_enu_m")
        if positions is not None:
            if not isinstance(positions, list) or len(positions) != len(release.releases):
                raise ProviderReleaseContractError("campaign endpoint placement count disagrees with selected packet")
            payload = release.model_dump(mode="json")
            payload["releases"] = [
                {**endpoint.model_dump(mode="json"), "position_enu_m": list(position)}
                for endpoint, position in zip(release.releases, positions)
            ]
            payload["inventory_provenance"] = (
                f"{release.inventory_provenance}; explicit endpoint placement from campaign facility ports"
            )
            release = ResolvedGasReleaseSet.model_validate_json(json.dumps(payload, allow_nan=False))
    elif isinstance(release, (ResolvedGasRelease, ResolvedLiquidRelease)):
        position = current_request.get("source_position_enu_m")
        if position is not None:
            if not isinstance(position, list) or len(position) != 3:
                raise ProviderReleaseContractError("campaign facility placement must be a three-vector")
            payload = release.model_dump(mode="json")
            payload["position_enu_m"] = list(position)
            payload["provider_boundary_reference"] = (
                f"{release.provider_boundary_reference}; explicit placement from campaign facility port"
            )
            release = type(release).model_validate_json(json.dumps(payload, allow_nan=False))
    defaults = _defaults_from_request(current_request)
    if getattr(release, "event_kind", None) == "emergency_relief":
        defaults["release_termination"] = {
            "basis": "provider_declared",
            "time_s": "provider_duration",
            "provenance": "selected exact strict emergency-relief worklist packet; provider clock retained",
        }
    if hasattr(release, "releases"):
        request = build_consequence_request_from_provider_release_set(release, defaults)
    else:
        request = build_consequence_request_from_provider_release(release, defaults)
    return request.model_dump(mode="json")


def rebind_campaign_to_worklist_packets(
    campaign: dict[str, Any],
    packet_evidence: dict[str, Any],
    *,
    packet_root: str | Path,
) -> dict[str, Any]:
    """Return a validated campaign whose requests use selected strict packets."""
    output = copy.deepcopy(campaign)
    rows = packet_evidence.get("rows")
    routes = output.get("event_routes")
    if not isinstance(rows, list) or not isinstance(routes, list):
        raise ValueError("campaign event_routes and packet evidence rows must be arrays")
    evidence_by_event = {
        row["event_id"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("event_id"), str)
    }
    packet_root_path = Path(packet_root)
    rebound: list[str] = []
    for route in routes:
        if not isinstance(route, dict) or not isinstance(route.get("event_id"), str):
            raise ValueError("campaign route must contain event_id")
        event_id = route["event_id"]
        evidence_row = evidence_by_event.get(event_id)
        if evidence_row is None:
            raise ProviderReleaseContractError(f"no packet evidence row for campaign event: {event_id}")
        branches = route.get("branches")
        if not isinstance(branches, list):
            raise ValueError(f"campaign route branches must be an array: {event_id}")
        request_branches = [branch for branch in branches if isinstance(branch, dict) and branch.get("request") is not None]
        if len(request_branches) != 1:
            raise ProviderReleaseContractError(
                f"worklist packet rebind requires exactly one request branch: {event_id}"
            )
        release = _load_selected_release(event_id, evidence_row, packet_root_path)
        branch = request_branches[0]
        current_request = branch["request"]
        if not isinstance(current_request, dict):
            raise ValueError(f"campaign request must be an object: {event_id}")
        branch["request"] = _request_from_selected_packet(current_request, release)
        rebound.append(event_id)
    validated = RiskCampaign.model_validate_json(json.dumps(output, ensure_ascii=False, allow_nan=False))
    # Keep the output a strict RiskCampaign document.  Contract.extra="forbid"
    # means provenance must be written beside the campaign, rather than added
    # as an unknown top-level campaign field that the runner would reject.
    return validated.model_dump(mode="json")


def packet_rebind_provenance(
    packet_evidence: dict[str, Any],
    event_ids: list[str],
) -> dict[str, Any]:
    """Describe the rebind without changing the strict campaign schema."""
    return {
        "schema_version": "prism.campaign_packet_rebind.v1",
        "event_count": len(event_ids),
        "event_ids": event_ids,
        "packet_evidence_status": packet_evidence.get("status"),
        "qualified_provider_packet_count": packet_evidence.get("qualified_provider_packet_count"),
        "frequency_bound": packet_evidence.get("frequency_bound"),
        "facility_qra_claim": packet_evidence.get("facility_qra_claim"),
        "physical_validation_claim": packet_evidence.get("physical_validation_claim"),
        "interpretation": (
            "Each campaign request was rebuilt from the selected exact/strict worklist packet. "
            "This changes packet identity and provider clock inputs only; it does not qualify the "
            "provider evidence, assign frequency, or complete the facility QRA."
        ),
    }
