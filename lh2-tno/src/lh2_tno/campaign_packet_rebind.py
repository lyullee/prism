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
from collections.abc import Mapping
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
from .state_snapshot import EquipmentStateSnapshot


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
    # Inventory-horizon packets deliberately do not carry a random failure
    # opening.  They still need an exact event identity and a strict packet
    # contract before they can be rebound.  Keep the opening check for leak
    # packets, while allowing the explicit inventory identity gate for these
    # two provider-owned termination modes.
    opening_match = evidence.get("exact_opening_match") is True
    inventory_identity_match = (
        evidence.get("event_identity_match") is True
        and evidence.get("termination_basis") in {"inventory_depletion", "inventory_depletion_positive_threshold", "inventory_over_600s"}
    )
    if (not opening_match and not inventory_identity_match) or evidence.get("strict_packet_valid") is not True:
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


def _load_selected_state_snapshot(
    packet_path: Path,
    *,
    event_id: str,
    component_id: str,
) -> tuple[dict[str, Any], str] | None:
    """Load the canonical state echoed beside a native provider packet.

    Native exporters keep accident-owned release fields in the resolved packet
    and the state-only handoff in ``verification.json``.  Rebinding a packet
    must carry both contracts into the campaign request; otherwise the packet
    can be exact while the facility ledger loses the equipment-state identity.
    Older diagnostic fixtures may not have a verification sidecar, so the
    helper remains optional for those fixtures.
    """
    verification_path = packet_path.with_name("verification.json")
    if not verification_path.exists():
        return None
    verification = _load_json(verification_path)
    raw_snapshot = verification.get("state_snapshot")
    if raw_snapshot is None:
        return None
    snapshot = EquipmentStateSnapshot.from_mapping(raw_snapshot)
    if snapshot.component_id != component_id:
        raise ProviderReleaseContractError(
            f"selected state snapshot component disagrees with worklist: {event_id}"
        )
    handoff = verification.get("state_snapshot_handoff")
    digest = snapshot.digest()
    if isinstance(handoff, dict):
        if handoff.get("digest") not in (None, digest):
            raise ProviderReleaseContractError(
                f"selected state snapshot digest disagrees with verification: {event_id}"
            )
        echoed = handoff.get("provider_echo_digest")
        echoed_values = echoed if isinstance(echoed, list) else [echoed]
        if any(value not in (None, digest) for value in echoed_values):
            raise ProviderReleaseContractError(
                f"provider state snapshot echo disagrees with canonical snapshot: {event_id}"
            )
    return snapshot.to_mapping(), digest


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
    # The provider packet owns the termination basis.  When an older campaign
    # template omitted the equipment-specific source operator, bind the
    # corresponding explicit operator here instead of leaving the request in
    # the generic integrated-transient path.  This mapping is identity
    # metadata only; it does not infer a duration, mass, frequency, or QRA
    # result.
    source_operator_by_basis = {
        "inventory_depletion": (
            "equipment_liquid_release"
            if isinstance(release, ResolvedLiquidRelease)
            else "equipment_inventory_depletion"
        ),
        "inventory_depletion_positive_threshold": (
            "equipment_liquid_release"
            if isinstance(release, ResolvedLiquidRelease)
            else "equipment_inventory_depletion"
        ),
        "inventory_over_600s": (
            "equipment_liquid_over_600s"
            if isinstance(release, ResolvedLiquidRelease)
            else "equipment_inventory_over_600s"
        ),
        "two_sided_rupture": "equipment_two_sided_rupture",
        "emergency_relief_discharge": "equipment_emergency_relief",
    }
    # A pressure-equalisation packet owns its natural stop time.  Older
    # campaign templates usually carry the generic declared-duration context;
    # retaining that context makes the provider packet fail validation even
    # though the packet itself is complete.  Bind the explicit operator and
    # duration mode from the provider termination basis.  This only changes
    # request identity metadata; the provider duration and mass ledger remain
    # authoritative.
    if getattr(release, "termination_basis", None) == "model_pressure_equalization":
        defaults["source_duration_mode"] = "model_natural"
        if isinstance(release, ResolvedLiquidRelease):
            defaults["source_operator"] = "equipment_liquid_release"
        else:
            defaults["source_operator"] = "equipment_pressure_equalization"
    elif getattr(release, "termination_basis", None) in {
        "reviewed_isolation_success",
        "reviewed_isolation_failure",
        "inventory_depletion",
        "inventory_depletion_positive_threshold",
        "inventory_over_600s",
        "emergency_relief_discharge",
        "two_sided_rupture",
    }:
        # A changed provider packet can carry a different termination basis
        # from the older campaign template.  Explicit finite-horizon and
        # inventory packets use the declared provider clock; retaining a
        # stale model-natural mode would reject an otherwise valid packet.
        defaults["source_duration_mode"] = "declared"
    source_operator = source_operator_by_basis.get(getattr(release, "termination_basis", None))
    if source_operator is not None:
        # The provider termination basis determines which explicit equipment
        # operator is contract-compatible.  Rebinding an exact packet must
        # repair stale template metadata as well as replace the packet.
        defaults["source_operator"] = source_operator
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
        selected_paths = evidence_row.get("evidence", {}).get("resolved_packet_paths")
        if not isinstance(selected_paths, list) or len(selected_paths) != 1:
            raise ProviderReleaseContractError(
                f"worklist event requires exactly one selected resolved packet: {event_id}"
            )
        packet_path = _resolve_packet_path(selected_paths[0], packet_root_path)
        selected_snapshot = _load_selected_state_snapshot(
            packet_path,
            event_id=event_id,
            component_id=str(evidence_row.get("component_id") or current_request.get("component_id") or ""),
        )
        if selected_snapshot is not None:
            snapshot_payload, snapshot_digest = selected_snapshot
            current_request = copy.deepcopy(current_request)
            current_request["state_snapshot"] = snapshot_payload
            current_request["state_snapshot_digest"] = snapshot_digest
            current_request["provider_state_snapshot_digest"] = snapshot_digest
            current_request["provider_state_snapshot_digests"] = [snapshot_digest]
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


def rebind_request_to_compressible_handoff(
    current_request: dict[str, Any],
    handoff_packet: Mapping[str, Any],
    *,
    event_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replace one gas request with an explicit compressible-plane packet.

    The handoff is a new provider result for the same event. It is checked
    against the campaign's existing packet by event, component, port, and
    source digest before the request is rebuilt. This prevents a packet from
    another accident or equipment state being attached by shape alone.
    """
    if not isinstance(current_request, dict):
        raise ProviderReleaseContractError("campaign request must be an object")
    current_payload = current_request.get("resolved_release")
    if not isinstance(current_payload, Mapping):
        raise ProviderReleaseContractError("compressible handoff rebind requires an existing gas packet")
    current_release = load_provider_release(current_payload)
    handoff_release = load_provider_release(handoff_packet)
    if not isinstance(current_release, ResolvedGasRelease) or not isinstance(handoff_release, ResolvedGasRelease):
        raise ProviderReleaseContractError("compressible handoff rebind requires flat gas release packets")
    checks = {
        "event_id_match": current_release.event_id == handoff_release.event_id,
        "component_id_match": current_release.component_id == handoff_release.component_id,
        "port_id_match": current_release.port_id == handoff_release.port_id,
        "source_digest_match": current_release.provider_source_digest == handoff_release.provider_source_digest,
        "handoff_present": handoff_release.compressible_plane_handoff is not None,
    }
    if event_id is not None:
        checks["requested_event_id_match"] = event_id == handoff_release.event_id
    if not all(checks.values()):
        failed = ", ".join(key for key, value in checks.items() if not value)
        raise ProviderReleaseContractError(f"compressible handoff identity check failed: {failed}")
    rebound = _request_from_selected_packet(current_request, handoff_release)
    handoff = handoff_release.compressible_plane_handoff
    assert handoff is not None
    provenance = {
        "schema_version": "prism.campaign_compressible_handoff_rebind.v1",
        "event_id": handoff_release.event_id,
        "component_id": handoff_release.component_id,
        "port_id": handoff_release.port_id,
        "original_provider_result_digest": current_release.provider_result_digest,
        "handoff_provider_result_digest": handoff_release.provider_result_digest,
        "identity_checks": checks,
        "compressible_plane_handoff_consumed": True,
        "handoff_provenance": handoff.provenance,
        "facility_qra_claim": False,
        "frequency_inference": False,
        "physical_validation_claim": False,
        "provider_packet_promoted": False,
        "diagnostic_only": True,
        "interpretation": (
            "The request was explicitly rebound to a provider-supplied compressible plane for the "
            "same event, component, port, and source state. The adapter remains diagnostic; its "
            "near-field result is not independently validated and it does not create frequency or QRA claims."
        ),
    }
    return rebound, provenance


def rebind_campaign_to_compressible_handoff(
    campaign: dict[str, Any],
    handoff_packet: Mapping[str, Any],
    *,
    event_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rebind exactly one campaign route to a validated compressible handoff."""
    output = copy.deepcopy(campaign)
    routes = output.get("event_routes")
    if not isinstance(routes, list):
        raise ValueError("campaign event_routes must be an array")
    matches = [route for route in routes if isinstance(route, dict) and route.get("event_id") == event_id]
    if len(matches) != 1:
        raise ProviderReleaseContractError(f"campaign must contain exactly one route for handoff event: {event_id}")
    route = matches[0]
    branches = route.get("branches")
    if not isinstance(branches, list):
        raise ValueError(f"campaign route branches must be an array: {event_id}")
    request_branches = [branch for branch in branches if isinstance(branch, dict) and branch.get("request") is not None]
    if len(request_branches) != 1:
        raise ProviderReleaseContractError(f"handoff rebind requires exactly one request branch: {event_id}")
    branch = request_branches[0]
    request, provenance = rebind_request_to_compressible_handoff(
        branch["request"], handoff_packet, event_id=event_id
    )
    branch["request"] = request
    validated = RiskCampaign.model_validate_json(json.dumps(output, ensure_ascii=False, allow_nan=False))
    return validated.model_dump(mode="json"), provenance
