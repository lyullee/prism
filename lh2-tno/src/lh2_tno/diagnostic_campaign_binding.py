"""Audit the structural handoff from provider packets into a facility campaign.

The audit deliberately separates two questions that are easy to confuse:

* did the packet worklist event IDs reach the campaign event/case/risk-atom
  ledgers; and
* did the campaign actually consume the saved provider packet values?

The current campaign format stores the first relationship and provider packet
identity on cases, but a saved packet file must still be digest-checked for each
campaign event.  The report therefore separates an exact packet-subset
consumption result from full campaign coverage.  It never creates a frequency,
promotes a packet, or turns an incomplete facility result into a qualified QRA.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
import json
from typing import Any


def _event_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("event_id", row.get("id"))
    return value if isinstance(value, str) and value else None


def _component_id(row: Mapping[str, Any]) -> str | None:
    for key in ("component_id", "model_component_id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _opening_diameter(row: Mapping[str, Any]) -> float | None:
    value = row.get("required_opening_diameter_m")
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    release = row.get("release")
    if isinstance(release, Mapping):
        value = release.get("hole_diameter_m")
        if isinstance(value, (int, float)) and value == value:
            return float(value)
    return None


def _same_float(left: float | None, right: float | None, *, tolerance: float = 1.0e-12) -> bool:
    return left is not None and right is not None and abs(left - right) <= tolerance * max(1.0, abs(left), abs(right))


def _packet_digest_pairs(path: Path) -> set[tuple[str, str]]:
    packets = _packet_release_rows(path)
    pairs = set()
    for row in packets:
        source = row.get("provider_source_digest")
        result = row.get("provider_result_digest")
        if isinstance(source, str) and isinstance(result, str):
            pairs.add((source, result))
    return pairs


def _packet_release_rows(path: Path) -> list[Mapping[str, Any]]:
    """Read resolved-release rows without treating response metadata as a release."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get("releases")
    packets = rows if isinstance(rows, list) else [payload]
    return [row for row in packets if isinstance(row, Mapping)]


def _same_numeric(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    return _same_float(float(left), float(right), tolerance=1.0e-8)


def _same_value_sequence(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    for left_value, right_value in zip(left, right):
        if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
            if not _same_numeric(left_value, right_value):
                return False
        elif left_value != right_value:
            return False
    return True


def _packet_value_mismatches(
    packet_rows: list[Mapping[str, Any]],
    case_rows: list[Mapping[str, Any]],
) -> list[str]:
    """Compare provider aggregate release values with every campaign case.

    This is deliberately a consumption audit, not a qualification decision.
    It checks the release aggregates that the facility ledger can carry
    (duration, termination, available mass, cumulative mass and residual
    released mass).  It does not claim that every provider time-step was
    independently re-simulated by the consequence solver.
    """
    mismatches: list[str] = []
    packet_by_result = {
        row.get("provider_result_digest"): row
        for row in packet_rows
        if isinstance(row.get("provider_result_digest"), str)
    }
    if not packet_by_result:
        return ["packet has no provider_result_digest rows"]
    for case_index, case in enumerate(case_rows):
        identity = case.get("provider_packet_identity")
        if not isinstance(identity, Mapping):
            mismatches.append(f"case[{case_index}] has no provider_packet_identity")
            continue
        results = identity.get("provider_result_digests")
        sources = identity.get("provider_source_digests")
        if not isinstance(results, list) or not isinstance(sources, list) or len(results) != len(sources):
            mismatches.append(f"case[{case_index}] provider digest arrays are malformed")
            continue
        if len(results) != len(packet_rows):
            mismatches.append(
                f"case[{case_index}] packet endpoint count differs: identity={len(results)} packet={len(packet_rows)}"
            )
            continue
        identity_fields = {
            "duration_s": identity.get("duration_s"),
            "available_mass_kg": identity.get("available_mass_kg"),
            "cumulative_mass_out_kg": identity.get("cumulative_mass_out_kg"),
            "termination_bases": identity.get("termination_bases"),
            "termination_provenances": identity.get("termination_provenances"),
        }
        packet_fields = {key: [] for key in identity_fields}
        for index, result_digest in enumerate(results):
            packet = packet_by_result.get(result_digest)
            if packet is None:
                mismatches.append(
                    f"case[{case_index}] missing packet result digest: {result_digest}"
                )
                continue
            if packet.get("provider_source_digest") != sources[index]:
                mismatches.append(f"case[{case_index}] source digest order differs at endpoint {index}")
            packet_fields["duration_s"].append(packet.get("duration_s"))
            packet_fields["available_mass_kg"].append(packet.get("available_mass_kg"))
            packet_fields["cumulative_mass_out_kg"].append(packet.get("cumulative_mass_out_kg"))
            packet_fields["termination_bases"].append(packet.get("termination_basis"))
            packet_fields["termination_provenances"].append(packet.get("termination_provenance"))
        for field, packet_values in packet_fields.items():
            if not _same_value_sequence(identity_fields[field], packet_values):
                mismatches.append(f"case[{case_index}] {field} differs from packet")
        termination = case.get("termination")
        termination = termination if isinstance(termination, Mapping) else {}
        packet_durations = packet_fields["duration_s"]
        case_time = termination.get("time_s")
        finite_durations = [value for value in packet_durations if isinstance(value, (int, float))]
        if finite_durations and not _same_numeric(case_time, max(finite_durations)):
            mismatches.append(f"case[{case_index}] termination.time_s differs from provider duration")
        mass_ledger = case.get("mass_ledger")
        mass_ledger = mass_ledger if isinstance(mass_ledger, Mapping) else {}
        cumulative = [
            value for value in packet_fields["cumulative_mass_out_kg"]
            if isinstance(value, (int, float))
        ]
        released = mass_ledger.get("released_kg")
        if cumulative and not _same_numeric(released, sum(cumulative)):
            mismatches.append(f"case[{case_index}] mass_ledger.released_kg differs from packet cumulative mass")
    return mismatches


def build_diagnostic_campaign_binding(
    packet_evidence: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    provider_worklist: Mapping[str, Any] | None = None,
    packet_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a fail-closed structural packet-to-campaign binding report."""
    packet_rows = packet_evidence.get("rows")
    campaign_events = campaign_result.get("events")
    campaign_cases = campaign_result.get("cases")
    risk_atoms = campaign_result.get("risk_atoms")
    if not isinstance(packet_rows, list):
        raise ValueError("packet evidence rows must be an array")
    if not isinstance(campaign_events, list):
        raise ValueError("campaign events must be an array")
    if not isinstance(campaign_cases, list):
        raise ValueError("campaign cases must be an array")
    if not isinstance(risk_atoms, list):
        raise ValueError("campaign risk_atoms must be an array")

    exact_rows = [
        row for row in packet_rows
        if isinstance(row, Mapping)
        and isinstance(row.get("evidence"), Mapping)
        and row["evidence"].get("exact_opening_match") is True
        and row["evidence"].get("strict_packet_valid") is True
    ]
    packet_by_event = {
        row["event_id"]: row
        for row in exact_rows
        if isinstance(row.get("event_id"), str) and row.get("event_id")
    }
    event_by_id = {
        row["id"]: row
        for row in campaign_events
        if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row.get("id")
    }
    case_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in campaign_cases:
        if isinstance(row, Mapping) and isinstance(row.get("event_id"), str):
            case_by_event.setdefault(row["event_id"], []).append(row)
    atom_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in risk_atoms:
        if isinstance(row, Mapping) and isinstance(row.get("event_id"), str):
            atom_by_event.setdefault(row["event_id"], []).append(row)

    packet_ids = set(packet_by_event)
    event_ids = set(event_by_id)
    case_ids = set(case_by_event)
    atom_ids = set(atom_by_event)
    event_matches = sorted(packet_ids & event_ids)
    case_matches = sorted(packet_ids & case_ids)
    atom_matches = sorted(packet_ids & atom_ids)
    missing_events = sorted(packet_ids - event_ids)
    missing_cases = sorted(packet_ids - case_ids)
    missing_atoms = sorted(packet_ids - atom_ids)
    unexpected_events = sorted(event_ids - packet_ids)

    worklist_by_event: dict[str, Mapping[str, Any]] = {}
    if isinstance(provider_worklist, Mapping):
        items = provider_worklist.get("work_items")
        if isinstance(items, list):
            worklist_by_event = {
                row["event_id"]: row
                for row in items
                if isinstance(row, Mapping)
                and isinstance(row.get("event_id"), str)
                and row.get("event_id")
            }

    geometry_matches = 0
    geometry_checked = 0
    geometry_mismatches: list[str] = []
    component_matches = 0
    component_checked = 0
    for event_id in event_matches:
        packet_row = packet_by_event[event_id]
        event_row = event_by_id[event_id]
        work_row = worklist_by_event.get(event_id)
        expected_component = _component_id(packet_row)
        actual_component = _component_id(event_row)
        if expected_component is not None and actual_component is not None:
            component_checked += 1
            if expected_component == actual_component:
                component_matches += 1
        expected_opening = _opening_diameter(work_row or packet_row)
        actual_opening = _opening_diameter(event_row)
        if expected_opening is not None and actual_opening is not None:
            geometry_checked += 1
            if _same_float(expected_opening, actual_opening):
                geometry_matches += 1
            else:
                geometry_mismatches.append(event_id)

    case_status_counts = Counter(
        str(row.get("status", "UNKNOWN"))
        for rows in case_by_event.values()
        for row in rows
    )
    identity_case_count = sum(
        1
        for row in campaign_cases
        if isinstance(row, Mapping)
        and isinstance(row.get("provider_packet_identity"), Mapping)
        and row["provider_packet_identity"].get("provider_source_digests")
        and row["provider_packet_identity"].get("provider_result_digests")
    )
    packet_root_path = Path(packet_root) if packet_root is not None else Path.cwd()
    packet_digest_pairs_by_event: dict[str, set[tuple[str, str]]] = {}
    packet_digest_unreadable_event_ids: list[str] = []
    for event_id, row in packet_by_event.items():
        evidence = row.get("evidence")
        paths = evidence.get("resolved_packet_paths") if isinstance(evidence, Mapping) else None
        pairs: set[tuple[str, str]] = set()
        if isinstance(paths, list):
            for raw_path in paths:
                if not isinstance(raw_path, str):
                    continue
                path = Path(raw_path)
                if not path.is_absolute():
                    path = packet_root_path / path
                try:
                    pairs.update(_packet_digest_pairs(path))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    packet_digest_unreadable_event_ids.append(event_id)
        packet_digest_pairs_by_event[event_id] = pairs
    campaign_pairs_by_event: dict[str, set[tuple[str, str]]] = {}
    for event_id, rows in case_by_event.items():
        pairs: set[tuple[str, str]] = set()
        for row in rows:
            identity = row.get("provider_packet_identity")
            if not isinstance(identity, Mapping):
                continue
            sources = identity.get("provider_source_digests")
            results = identity.get("provider_result_digests")
            if isinstance(sources, list) and isinstance(results, list):
                pairs.update(
                    (source, result)
                    for source in sources
                    for result in results
                    if isinstance(source, str) and isinstance(result, str)
                )
        campaign_pairs_by_event[event_id] = pairs
    digest_checked_event_ids = sorted(
        event_id for event_id in packet_ids
        if packet_digest_pairs_by_event.get(event_id) and campaign_pairs_by_event.get(event_id)
    )
    digest_match_event_ids = sorted(
        event_id for event_id in digest_checked_event_ids
        if packet_digest_pairs_by_event[event_id] == campaign_pairs_by_event[event_id]
    )
    digest_mismatch_event_ids = sorted(set(digest_checked_event_ids) - set(digest_match_event_ids))
    packet_subset_identity_consumed = (
        len(digest_match_event_ids) == len(packet_ids)
        and not packet_digest_unreadable_event_ids
        and bool(packet_ids)
    )
    risk_atom_count_by_event = {event_id: len(rows) for event_id, rows in atom_by_event.items()}
    structural_complete = (
        bool(packet_ids)
        and packet_ids == event_ids
        and packet_ids == case_ids
        and packet_ids == atom_ids
        and not missing_events
        and not missing_cases
        and not missing_atoms
        and component_checked == len(event_matches)
        and component_matches == component_checked
        # Inventory-depletion and relief events intentionally have no hole
        # diameter.  Every event with a declared diameter must match, while
        # absence of a diameter is recorded as an event-type boundary rather
        # than treated as a failed comparison.
        and geometry_checked > 0
        and geometry_matches == geometry_checked
        and all(risk_atom_count_by_event.get(event_id, 0) > 0 for event_id in packet_ids)
    )
    packet_scope_subset_complete = (
        bool(packet_ids)
        and packet_ids <= event_ids
        and packet_ids <= case_ids
        and packet_ids <= atom_ids
        and not missing_events
        and not missing_cases
        and not missing_atoms
        and component_checked == len(event_matches)
        and component_matches == component_checked
        and geometry_checked > 0
        and geometry_matches == geometry_checked
        and all(risk_atom_count_by_event.get(event_id, 0) > 0 for event_id in packet_ids)
    )
    campaign_scope_packet_coverage_complete = bool(event_ids) and event_ids <= packet_ids
    packet_identity_consumed = (
        packet_subset_identity_consumed
        and campaign_scope_packet_coverage_complete
        and identity_case_count == len(campaign_cases)
        and bool(campaign_cases)
    )
    packet_value_mismatch_reasons: dict[str, list[str]] = {}
    packet_value_consumed_event_ids: list[str] = []
    for event_id in sorted(packet_ids & case_ids):
        evidence = packet_by_event[event_id].get("evidence")
        paths = evidence.get("resolved_packet_paths") if isinstance(evidence, Mapping) else None
        packet_rows: list[Mapping[str, Any]] = []
        if isinstance(paths, list):
            for raw_path in paths:
                if not isinstance(raw_path, str):
                    continue
                path = Path(raw_path)
                if not path.is_absolute():
                    path = packet_root_path / path
                try:
                    packet_rows.extend(_packet_release_rows(path))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    packet_value_mismatch_reasons.setdefault(event_id, []).append(
                        f"unable to read packet values: {raw_path}"
                    )
        mismatches = _packet_value_mismatches(packet_rows, case_by_event[event_id])
        if mismatches:
            packet_value_mismatch_reasons.setdefault(event_id, []).extend(mismatches)
        elif packet_rows:
            packet_value_consumed_event_ids.append(event_id)
        else:
            packet_value_mismatch_reasons.setdefault(event_id, []).append(
                "no resolved packet rows were available"
            )
    packet_value_checked_event_ids = sorted(packet_ids & case_ids)
    packet_value_consumed_event_ids = sorted(set(packet_value_consumed_event_ids))
    packet_value_mismatch_event_ids = sorted(packet_value_mismatch_reasons)
    packet_subset_value_consumed = (
        bool(packet_ids)
        and packet_value_checked_event_ids == sorted(packet_ids)
        and packet_value_consumed_event_ids == sorted(packet_ids)
    )
    packet_claims_preserved = (
        packet_evidence.get("qualified_provider_packet_count") == 0
        and packet_evidence.get("frequency_bound") is False
        and packet_evidence.get("facility_qra_claim") is False
        and packet_evidence.get("physical_validation_claim") is False
        and campaign_result.get("complete_facility_qra_claim") is False
        and campaign_result.get("physical_validation_claim") is False
    )
    executed_case_count = sum(
        count for status, count in case_status_counts.items() if status.startswith("EXECUTED")
    )
    return {
        "schema_version": "prism.diagnostic_campaign_binding.v1",
        "status": "PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING" if packet_scope_subset_complete and packet_claims_preserved else "BLOCKED_DIAGNOSTIC_CAMPAIGN_BINDING",
        "packet_event_count": len(packet_ids),
        "campaign_event_count": len(event_ids),
        "campaign_case_count": len(campaign_cases),
        "campaign_risk_atom_count": len(risk_atoms),
        "packet_event_to_campaign_event_match_count": len(event_matches),
        "packet_event_to_campaign_case_match_count": len(case_matches),
        "packet_event_to_campaign_risk_atom_match_count": len(atom_matches),
        "missing_campaign_event_ids": missing_events,
        "missing_campaign_case_ids": missing_cases,
        "missing_campaign_risk_atom_ids": missing_atoms,
        "unexpected_campaign_event_ids": unexpected_events,
        "unbound_campaign_event_ids": unexpected_events,
        "unbound_campaign_event_count": len(unexpected_events),
        "packet_event_coverage_ratio": len(event_matches) / len(event_ids) if event_ids else 0.0,
        "packet_case_coverage_ratio": len(case_matches) / len(case_ids) if case_ids else 0.0,
        "packet_risk_atom_event_coverage_ratio": len(atom_matches) / len(atom_ids) if atom_ids else 0.0,
        "component_match_count": component_matches,
        "component_checked_count": component_checked,
        "opening_geometry_match_count": geometry_matches,
        "opening_geometry_checked_count": geometry_checked,
        "opening_geometry_unchecked_event_count": len(event_matches) - geometry_checked,
        "opening_geometry_mismatch_event_ids": geometry_mismatches,
        "risk_atom_count_by_event": risk_atom_count_by_event,
        "case_status_counts": dict(case_status_counts),
        "executed_case_count": executed_case_count,
        "campaign_provider_identity_case_count": identity_case_count,
        "campaign_provider_identity_recorded": identity_case_count == len(campaign_cases) and bool(campaign_cases),
        "structural_binding_complete": structural_complete,
        "packet_scope_subset_complete": packet_scope_subset_complete,
        "campaign_scope_packet_coverage_complete": campaign_scope_packet_coverage_complete,
        "packet_digest_checked_event_count": len(digest_checked_event_ids),
        "packet_digest_match_event_count": len(digest_match_event_ids),
        "packet_digest_mismatch_event_ids": digest_mismatch_event_ids,
        "packet_digest_unreadable_event_ids": sorted(set(packet_digest_unreadable_event_ids)),
        "packet_subset_identity_consumed": packet_subset_identity_consumed,
        "packet_identity_consumed": packet_identity_consumed,
        "packet_value_checked_event_count": len(packet_value_checked_event_ids),
        "packet_value_consumed_event_count": len(packet_value_consumed_event_ids),
        "packet_value_consumed_event_ids": packet_value_consumed_event_ids,
        "packet_value_mismatch_event_ids": packet_value_mismatch_event_ids,
        "packet_value_mismatch_reasons": packet_value_mismatch_reasons,
        "packet_subset_value_consumed": packet_subset_value_consumed,
        "packet_time_step_history_replayed": False,
        "packet_value_consumption_policy": (
            "Duration, termination basis/provenance, available mass, cumulative release mass and case "
            "released mass are compared to the saved resolved packet; provider time-step history is not "
            "claimed to be independently replayed."
        ),
        "packet_identity_consumption_reason": (
            "campaign result provider source/result digests match the packet-evidence files for every "
            "event; packet identity is recorded but qualification and facility claims remain separate"
            if packet_identity_consumed
            else "selected packet subset source/result digests match the packet-evidence files, but "
            "one or more campaign events have no packet evidence; full campaign packet consumption is withheld"
            if packet_subset_identity_consumed and not campaign_scope_packet_coverage_complete
            else "campaign result preserves provider source/result digests, but those digests were not "
            "proven equal to the packet-evidence files supplied to this audit"
            if identity_case_count == len(campaign_cases) and bool(campaign_cases)
            else "campaign event/case records contain no provider_source_digest or provider_result_digest; "
            "the result proves event identity and opening geometry only"
        ),
        "frequency_from_provider_packet": False,
        "qualified_provider_packet_count": packet_evidence.get("qualified_provider_packet_count"),
        "facility_qra_claim": campaign_result.get("complete_facility_qra_claim"),
        "physical_validation_claim": campaign_result.get("physical_validation_claim"),
        "packet_claims_preserved": packet_claims_preserved,
        "interpretation": (
            "Provider worklist event IDs structurally reach facility events, cases, and risk atoms. "
            "For the matched packet subset, release aggregate values are compared with the facility case "
            "termination and mass ledger. The campaign still uses its declared literature frequency catalog, "
            "does not replay every provider time step, and cannot qualify packets or close the facility-QRA gate."
        ),
    }
