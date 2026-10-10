"""Audit the equipment-state to release-packet identity for every facility case.

This is a structural diagnostic audit.  It verifies that a case keeps the
equipment identity, canonical state snapshot, provider source/result
digests, release branch and termination boundary together before consequence
calculations are consumed.  It never turns a synthetic or operator-limited
packet into qualified evidence or a facility QRA.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


EQUIPMENT_STATE_RELEASE_AUDIT_SCHEMA = "prism.equipment_state_release_audit.v1"


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _case_label(case: Mapping[str, Any]) -> str:
    return "/".join(
        str(case.get(key, ""))
        for key in ("event_id", "annual_condition_id", "release_branch_id")
    )


def build_equipment_state_release_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fail-closed identity audit for all facility cases."""
    if not isinstance(result, Mapping):
        raise TypeError("facility result must be a mapping")
    raw_cases = result.get("cases", ())
    cases = (
        tuple(row for row in raw_cases if isinstance(row, Mapping))
        if isinstance(raw_cases, Sequence) and not isinstance(raw_cases, (str, bytes))
        else ()
    )
    blockers: list[str] = []
    complete_ids: list[str] = []
    incomplete_ids: list[str] = []
    component_counts: Counter[str] = Counter()
    component_complete_counts: Counter[str] = Counter()
    component_limited_counts: Counter[str] = Counter()
    seen_case_ids: set[str] = set()
    termination_echo_gap_case_ids: list[str] = []

    for case in cases:
        label = _case_label(case)
        case_errors: list[str] = []
        if label in seen_case_ids:
            case_errors.append("duplicate event/condition/release identity")
        seen_case_ids.add(label)

        status = str(case.get("status", ""))
        if not status.startswith("EXECUTED"):
            case_errors.append("case is not numerically executed")

        asset_id = case.get("asset_id")
        if not _nonempty(asset_id):
            case_errors.append("asset_id is missing")

        packet = case.get("provider_packet_identity")
        if not isinstance(packet, Mapping):
            case_errors.append("provider packet identity is missing")
            packet = {}
        component_id = packet.get("component_id")
        if not _nonempty(component_id):
            case_errors.append("provider component_id is missing")
        else:
            component_counts[str(component_id)] += 1

        snapshot = packet.get("state_snapshot")
        if not isinstance(snapshot, Mapping):
            case_errors.append("canonical equipment state snapshot is missing")
            snapshot = {}
        if snapshot.get("schema_version") != "prism.equipment_state_snapshot.v1":
            case_errors.append("state snapshot schema is missing or unsupported")
        if component_id and snapshot.get("component_id") != component_id:
            case_errors.append("state snapshot component_id does not match provider component_id")
        if not _nonempty(packet.get("state_snapshot_digest")):
            case_errors.append("state snapshot digest is missing")
        if packet.get("provider_state_snapshot_digest") != packet.get("state_snapshot_digest"):
            case_errors.append("provider state snapshot digest does not echo the canonical digest")
        if not _nonempty(snapshot.get("origin")):
            case_errors.append("state snapshot origin is missing")
        if not _finite_nonnegative(snapshot.get("captured_at_s")):
            case_errors.append("state snapshot capture time is missing or invalid")

        for field in ("provider_source_digests", "provider_result_digests"):
            values = packet.get(field)
            if (
                not isinstance(values, Sequence)
                or isinstance(values, (str, bytes))
                or not values
                or any(not _nonempty(value) for value in values)
            ):
                case_errors.append(f"{field} are missing or invalid")

        termination = case.get("termination")
        if (
            not isinstance(termination, Mapping)
            or not _nonempty(termination.get("basis"))
            or not _finite_nonnegative(termination.get("time_s"))
            or float(termination.get("time_s", 0.0)) <= 0.0
        ):
            case_errors.append("release termination basis/time is missing or invalid")
        packet_bases = packet.get("termination_bases")
        termination_echo_gap = False
        if (
            not isinstance(packet_bases, Sequence)
            or isinstance(packet_bases, (str, bytes))
            or not packet_bases
            or not isinstance(termination, Mapping)
            or termination.get("basis") not in packet_bases
        ):
            provenance_rows = packet.get("termination_provenances")
            synthetic_horizon_gap = (
                status == "EXECUTED_OPERATOR_LIMITED"
                and isinstance(termination, Mapping)
                and termination.get("basis") == "synthetic_diagnostic_horizon"
                and isinstance(provenance_rows, Sequence)
                and not isinstance(provenance_rows, (str, bytes))
                and any("synthetic" in str(row).lower() for row in provenance_rows)
            )
            if synthetic_horizon_gap:
                termination_echo_gap = True
                termination_echo_gap_case_ids.append(label)
            else:
                case_errors.append("provider termination basis does not echo case termination")

        if case_errors:
            incomplete_ids.append(label)
            if component_id:
                component_limited_counts[str(component_id)] += 1
            blockers.extend(f"{label}: {error}" for error in case_errors)
        else:
            complete_ids.append(label)
            if component_id:
                component_complete_counts[str(component_id)] += 1

    blockers = list(dict.fromkeys(blockers))
    component_ids = sorted(component_counts)
    complete = bool(cases) and not blockers
    return {
        "schema_version": EQUIPMENT_STATE_RELEASE_AUDIT_SCHEMA,
        "status": "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
        if complete
        else "PARTIAL_EQUIPMENT_STATE_RELEASE_CHAIN",
        "facility_id": result.get("facility_id"),
        "case_count": len(cases),
        "complete_case_count": len(complete_ids),
        "incomplete_case_count": len(incomplete_ids),
        "complete_case_ids": sorted(complete_ids),
        "incomplete_case_ids": sorted(incomplete_ids),
        "component_count": len(component_ids),
        "component_ids": component_ids,
        "component_case_counts": {
            component: component_counts[component] for component in component_ids
        },
        "component_complete_case_counts": {
            component: component_complete_counts[component] for component in component_ids
        },
        "component_incomplete_case_counts": {
            component: component_limited_counts[component] for component in component_ids
        },
        "operator_limited_case_count": sum(
            str(case.get("status", "")) == "EXECUTED_OPERATOR_LIMITED"
            for case in cases
        ),
        "provider_termination_echo_gap_case_count": len(termination_echo_gap_case_ids),
        "provider_termination_echo_gap_case_ids": sorted(termination_echo_gap_case_ids),
        "blocking_reasons": blockers,
        "diagnostic_only": True,
        "provider_packet_promoted": False,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Each numerical case must preserve the asset/component identity, canonical state snapshot, "
            "provider source/result digests, release termination and provider termination echo. "
            "A synthetic operator-limited horizon without a provider termination echo is counted "
            "explicitly as a limitation rather than repaired. This identity closure is diagnostic "
            "and does not qualify the provider or facility QRA."
        ),
    }


__all__ = [
    "EQUIPMENT_STATE_RELEASE_AUDIT_SCHEMA",
    "build_equipment_state_release_audit",
]
