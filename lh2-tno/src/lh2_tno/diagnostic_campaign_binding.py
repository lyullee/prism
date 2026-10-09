"""Audit the structural handoff from provider packets into a facility campaign.

The audit deliberately separates two questions that are easy to confuse:

* did the packet worklist event IDs reach the campaign event/case/risk-atom
  ledgers; and
* did the campaign actually consume the saved provider packet values?

The current campaign format stores the first relationship, but not a provider
packet digest on every event or case.  Therefore this module reports a
structural diagnostic binding while keeping ``packet_identity_consumed`` false.
It never creates a frequency, promotes a packet, or turns an incomplete
facility result into a qualified QRA.
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("releases") if isinstance(payload, Mapping) else None
    packets = rows if isinstance(rows, list) else [payload]
    pairs = set()
    for row in packets:
        if not isinstance(row, Mapping):
            continue
        source = row.get("provider_source_digest")
        result = row.get("provider_result_digest")
        if isinstance(source, str) and isinstance(result, str):
            pairs.add((source, result))
    return pairs


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
    packet_identity_consumed = (
        len(digest_match_event_ids) == len(packet_ids)
        and not packet_digest_unreadable_event_ids
        and identity_case_count == len(campaign_cases)
        and bool(campaign_cases)
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
        "status": "PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING" if structural_complete and packet_claims_preserved else "BLOCKED_DIAGNOSTIC_CAMPAIGN_BINDING",
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
        "packet_digest_checked_event_count": len(digest_checked_event_ids),
        "packet_digest_match_event_count": len(digest_match_event_ids),
        "packet_digest_mismatch_event_ids": digest_mismatch_event_ids,
        "packet_digest_unreadable_event_ids": sorted(set(packet_digest_unreadable_event_ids)),
        "packet_identity_consumed": packet_identity_consumed,
        "packet_identity_consumption_reason": (
            "campaign result provider source/result digests match the packet-evidence files for every "
            "event; packet identity is recorded but qualification and facility claims remain separate"
            if packet_identity_consumed
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
            "The campaign still uses its declared literature frequency catalog and does not prove that "
            "the saved external packet time history was consumed; this diagnostic binding cannot qualify "
            "the packets or close the facility-QRA gate."
        ),
    }
