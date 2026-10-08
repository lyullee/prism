"""Compare strict provider release packets with the declared event worklist.

The coverage report is a bookkeeping gate between an equipment digital twin
and the campaign compiler.  It checks event/component/port/opening identity and
the release family, but it never assigns a frequency or executes consequence
physics.  A packet that does not match an exact work item remains outside the
facility calculation.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping, Sequence

from .equipment_boundary import ResolvedGasRelease, ResolvedGasReleaseSet, ResolvedLiquidRelease


COVERAGE_SCHEMA = "prism.provider_release_catalog_coverage.v1"
ProviderPacket = ResolvedGasRelease | ResolvedLiquidRelease | ResolvedGasReleaseSet


def _packet_identity(packet: ProviderPacket) -> dict[str, Any]:
    if isinstance(packet, ResolvedGasReleaseSet):
        return {
            "event_id": packet.event_id,
            "component_id": packet.component_id,
            "packet_kind": "two_sided_rupture",
            "port_ids": sorted(release.port_id for release in packet.releases),
            "boundary_kinds": sorted({release.boundary_kind for release in packet.releases}),
            "opening_diameters_m": sorted(
                release.failure_opening_diameter_m for release in packet.releases
            ),
            "duration_s": packet.duration_s,
        }
    return {
        "event_id": packet.event_id,
        "component_id": packet.component_id,
        "packet_kind": "emergency_relief" if packet.event_kind == "emergency_relief" else "single_exit",
        "port_ids": [packet.port_id],
        "boundary_kinds": [packet.boundary_kind],
        "opening_diameters_m": [packet.failure_opening_diameter_m],
        "duration_s": packet.duration_s,
    }


def _match_item(item: Mapping[str, Any], packet: ProviderPacket) -> tuple[bool, list[str]]:
    """Return exact-match status and reasons without mutating either input."""
    reasons: list[str] = []
    identity = _packet_identity(packet)
    if identity["event_id"] != item.get("event_id"):
        reasons.append("event_id mismatch")
    if identity["component_id"] != item.get("component_id"):
        reasons.append("component_id mismatch")

    mode = item.get("release_mode")
    if mode == "two_sided_rupture":
        if not isinstance(packet, ResolvedGasReleaseSet):
            reasons.append("two_sided_rupture requires a resolved release set")
        else:
            if len(packet.releases) != int(item.get("provider_endpoint_count", 0)):
                reasons.append("provider endpoint count mismatch")
            expected_ports = sorted(item.get("accident_port_ids", ()))
            if expected_ports and identity["port_ids"] != expected_ports:
                reasons.append("two-sided accident ports do not exact-match worklist ports")
            expected_diameter = item.get("required_opening_diameter_m")
            if expected_diameter is not None:
                for diameter in identity["opening_diameters_m"]:
                    if diameter is None or not math.isclose(
                        float(diameter), float(expected_diameter), rel_tol=1e-10, abs_tol=1e-12
                    ):
                        reasons.append("two-sided failure opening does not exact-match frequency opening")
                        break
        return not reasons, reasons

    if isinstance(packet, ResolvedGasReleaseSet):
        reasons.append("single-exit work item cannot consume a resolved release set")
        return False, reasons
    expected_kind = item.get("provider_event_kind")
    if packet.event_kind != expected_kind:
        reasons.append(f"provider event_kind must be {expected_kind}")
    if packet.port_id not in set(item.get("accident_port_ids", ())):
        reasons.append("provider port_id is not an explicit accident port for this item")
    allowed_boundaries = set(item.get("provider_boundary_variants", ()))
    if packet.boundary_kind not in allowed_boundaries:
        reasons.append("provider boundary variant is not declared for this work item")

    expected_diameter = item.get("required_opening_diameter_m")
    if expected_diameter is not None:
        actual = packet.failure_opening_diameter_m
        if actual is None or not math.isclose(
            float(actual), float(expected_diameter), rel_tol=1e-10, abs_tol=1e-12
        ):
            reasons.append("provider failure opening does not exact-match frequency opening")
    elif packet.event_kind == "emergency_relief" and packet.failure_opening_diameter_m is not None:
        reasons.append("emergency-relief packet must not carry a random failure opening")

    expected_duration = item.get("required_duration_s")
    if expected_duration is not None and not math.isclose(
        float(packet.duration_s), float(expected_duration), rel_tol=0, abs_tol=1e-12
    ):
        reasons.append("provider duration does not exact-match the declared duration")
    return not reasons, reasons


def audit_provider_catalog_coverage(
    worklist: Mapping[str, Any],
    provider_packets: Sequence[ProviderPacket],
) -> dict[str, Any]:
    """Audit a strict packet catalog against every declared work-list item.

    The result is intentionally separate from :class:`RiskCampaign`: a
    ``FULLY_MATCHED`` report means that identity and boundary checks passed,
    while request defaults, barrier branches, frequency provenance, and
    consequence execution still require their own gates.
    """
    items = worklist.get("work_items")
    if not isinstance(items, list) or not items:
        raise ValueError("provider worklist must contain a non-empty work_items list")
    packets = tuple(provider_packets)
    if len({packet.event_id for packet in packets}) != len(packets):
        raise ValueError("provider packet event_id values must be unique for coverage audit")

    packet_by_event = {packet.event_id: packet for packet in packets}
    item_rows: list[dict[str, Any]] = []
    matched_events: set[str] = set()
    status_counts: Counter[str] = Counter()
    for item in items:
        event_id = item.get("event_id")
        packet = packet_by_event.get(event_id)
        if packet is None:
            row = {
                "event_id": event_id,
                "component_id": item.get("component_id"),
                "status": "UNMATCHED_NO_PROVIDER_PACKET",
                "reasons": ["no strict provider packet has this event_id"],
            }
        else:
            matched, reasons = _match_item(item, packet)
            if matched:
                matched_events.add(event_id)
                row = {
                    "event_id": event_id,
                    "component_id": item.get("component_id"),
                    "status": "EXACT_MATCH",
                    "packet": _packet_identity(packet),
                    "reasons": [],
                }
            else:
                row = {
                    "event_id": event_id,
                    "component_id": item.get("component_id"),
                    "status": "UNMATCHED_PACKET_CONTRACT",
                    "packet": _packet_identity(packet),
                    "reasons": reasons,
                }
        status_counts[row["status"]] += 1
        item_rows.append(row)

    worklist_events = {item.get("event_id") for item in items}
    extra_packets = [
        _packet_identity(packet)
        for packet in packets
        if packet.event_id not in worklist_events
    ]
    blocking_reasons: list[str] = []
    if status_counts["UNMATCHED_NO_PROVIDER_PACKET"]:
        blocking_reasons.append("one or more declared events have no provider packet")
    if status_counts["UNMATCHED_PACKET_CONTRACT"]:
        blocking_reasons.append("one or more provider packets fail exact worklist identity or boundary checks")
    if extra_packets:
        blocking_reasons.append("provider catalog contains packets outside the declared frequency worklist")
    status = "FULLY_MATCHED" if not blocking_reasons else (
        "NO_EXACT_MATCH" if not matched_events else "PARTIAL_EXACT_MATCH"
    )
    return {
        "schema": COVERAGE_SCHEMA,
        "status": status,
        "worklist_status": worklist.get("status"),
        "worklist_event_count": len(items),
        "provider_packet_count": len(packets),
        "exact_match_count": len(matched_events),
        "unmatched_event_count": len(items) - len(matched_events),
        "extra_packet_count": len(extra_packets),
        "status_counts": dict(sorted(status_counts.items())),
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "work_items": item_rows,
        "extra_packets": extra_packets,
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "request_defaults_are_not_attached": True,
            "normal_or_screening_flow_is_not_promoted": True,
            "full_match_does_not_claim_physical_validation": True,
            "campaign_requires_separate_exact_binding": True,
        },
    }

