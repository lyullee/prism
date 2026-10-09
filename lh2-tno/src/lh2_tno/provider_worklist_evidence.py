"""Audit saved external-provider packets against the generic LH2 worklist.

The audit is deliberately evidence-only.  It checks that a saved provider
response has a matching strict ``prism.resolved_release.v1`` packet, exact
component/port/opening identity, and an operator-limited verification record.
It never adds a frequency, promotes a packet, or treats a normal-state result
as an accident history.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from pathlib import Path
from typing import Any


PROVIDER_RESPONSE_SCHEMA = "prism.external_accident_history.v1"
RESOLVED_RELEASE_SCHEMA = "prism.resolved_release.v1"
RESOLVED_RELEASE_SET_SCHEMA = "prism.resolved_release_set.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_provider_responses(value: Any, path: Path) -> Iterator[dict[str, Any]]:
    if isinstance(value, Mapping):
        data = value.get("data")
        if (
            value.get("provider_export_schema") == PROVIDER_RESPONSE_SCHEMA
            and isinstance(data, Mapping)
            and isinstance(data.get("event_id"), str)
        ):
            yield {"path": str(path), "response": value, "data": data}
            return
        for child in value.values():
            yield from _walk_provider_responses(child, path)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_provider_responses(child, path)


def _walk_resolved(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if value.get("provider_export_schema") in {
            RESOLVED_RELEASE_SCHEMA,
            RESOLVED_RELEASE_SET_SCHEMA,
        }:
            yield value
        for child in value.values():
            yield from _walk_resolved(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_resolved(child)


def _finite_equal(left: Any, right: Any, tolerance: float = 1.0e-12) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def _strict_packet_ok(release: Mapping[str, Any]) -> bool:
    required = (
        "provider_export_schema",
        "event_id",
        "component_id",
        "port_id",
        "event_kind",
        "steps",
        "duration_s",
        "available_mass_kg",
        "cumulative_mass_out_kg",
        "termination_provenance",
        "property_basis",
    )
    return (
        release.get("provider_export_schema") == RESOLVED_RELEASE_SCHEMA
        and all(key in release for key in required)
        and release.get("event_kind") in {"accidental_leak", "emergency_relief"}
        and isinstance(release.get("steps"), list)
        and len(release["steps"]) > 0
        and isinstance(release.get("property_basis"), Mapping)
    )


def _verification(parent: Path) -> Mapping[str, Any] | None:
    path = parent / "verification.json"
    if not path.is_file():
        return None
    try:
        value = _load(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _candidate_packet(candidate: Mapping[str, Any], work_item: Mapping[str, Any]) -> dict[str, Any]:
    response_path = Path(str(candidate["path"]))
    parent = response_path.parent
    resolved_files = sorted(parent.glob("resolved_release*.json"))
    resolved: list[Mapping[str, Any]] = []
    for path in resolved_files:
        try:
            resolved.extend(_walk_resolved(_load(path)))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    event_id = work_item.get("event_id")
    component_id = work_item.get("component_id")
    ports = set(work_item.get("accident_port_ids", []))
    required_opening = work_item.get("required_opening_diameter_m")
    matching = [
        release
        for release in resolved
        if release.get("event_id") == event_id
        and release.get("component_id") == component_id
        and release.get("port_id") in ports
    ]
    response_data = candidate["data"]
    response_port = response_data.get("port_id")
    response_identity = (
        response_data.get("event_id") == event_id
        and response_data.get("component_id") == component_id
        and (response_port in ports or not ports)
    )
    release_ports = {release.get("port_id") for release in matching}
    expected_endpoint_count = int(work_item.get("provider_endpoint_count", len(ports)))
    endpoint_complete = (
        release_ports == ports if expected_endpoint_count > 1 else bool(matching)
    )
    exact_opening = bool(matching) and all(
        _finite_equal(release.get("failure_opening_diameter_m"), required_opening)
        for release in matching
    )
    strict_valid = bool(matching) and all(_strict_packet_ok(release) for release in matching)
    verification = _verification(parent)
    verification_ok = (
        isinstance(verification, Mapping)
        and isinstance(verification.get("status"), str)
        and "EXECUTED" in verification.get("status", "")
        and verification.get("provider_packet_promoted") is False
        and verification.get("frequency_inference") is False
        and verification.get("facility_qra_claim") is False
    )
    return {
        "response_path": str(response_path),
        "resolved_packet_paths": [str(path) for path in resolved_files],
        "provider_model": candidate["response"].get("provider_model"),
        "response_identity_match": response_identity,
        "endpoint_complete": endpoint_complete,
        "exact_opening_match": exact_opening,
        "strict_packet_valid": strict_valid,
        "verification_status": verification.get("status") if verification else None,
        "verification_ok": verification_ok,
        "qualified_provider_packet": False,
        "frequency_bound": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }


def _chain_events(results_root: Path) -> set[str]:
    event_ids: set[str] = set()
    for verification_path in results_root.rglob("verification.json"):
        try:
            verification = _load(verification_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(verification, Mapping) or not str(
            verification.get("status", "")
        ).startswith("END_TO_END"):
            continue
        request_path = verification_path.parent / "request.json"
        try:
            request = _load(request_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(request, Mapping):
            continue
        for key in ("resolved_release", "resolved_liquid_release", "resolved_release_set"):
            value = request.get(key)
            if isinstance(value, Mapping) and isinstance(value.get("event_id"), str):
                event_ids.add(value["event_id"])
    return event_ids


def build_provider_worklist_packet_evidence(
    provider_worklist: Mapping[str, Any],
    results_root: str | Path,
) -> dict[str, Any]:
    """Return exact-match diagnostic coverage for saved provider packets."""

    work_items = provider_worklist.get("work_items")
    if not isinstance(work_items, list):
        raise ValueError("provider_worklist.work_items must be an array")
    root = Path(results_root)
    candidates: list[dict[str, Any]] = []
    for path in sorted(root.rglob("provider_response*.json")):
        try:
            value = _load(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        candidates.extend(_walk_provider_responses(value, path))

    by_event: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_event.setdefault(str(candidate["data"].get("event_id")), []).append(candidate)
    rows: list[dict[str, Any]] = []
    for raw in work_items:
        if not isinstance(raw, Mapping):
            continue
        event_id = str(raw.get("event_id"))
        options = by_event.get(event_id, [])
        packet_options = [_candidate_packet(option, raw) for option in options]
        packet = next(
            (
                option
                for option in packet_options
                if option["response_identity_match"]
                and option["endpoint_complete"]
                and option["exact_opening_match"]
                and option["strict_packet_valid"]
                and option["verification_ok"]
            ),
            packet_options[0] if packet_options else None,
        )
        exact = bool(
            packet
            and packet["response_identity_match"]
            and packet["endpoint_complete"]
            and packet["exact_opening_match"]
            and packet["strict_packet_valid"]
            and packet["verification_ok"]
        )
        rows.append({
            "worklist_item_id": raw.get("id"),
            "event_id": event_id,
            "component_id": raw.get("component_id"),
            "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC" if exact else (
                "PROVIDER_PACKET_CANDIDATE_REJECTED" if packet else "UNCOMPUTED_PROVIDER_PACKET"
            ),
            "candidate_count": len(options),
            "evidence": packet,
        })
    exact_rows = [row for row in rows if row["status"] == "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC"]
    matched_rows = [row for row in rows if row["candidate_count"] > 0]
    chain_events = _chain_events(root)
    chain_count = sum(row["event_id"] in chain_events for row in exact_rows)
    status = "PARTIAL_DIAGNOSTIC_EVIDENCE" if exact_rows else "NO_DIAGNOSTIC_PACKET_EVIDENCE"
    return {
        "schema_version": "prism.provider_worklist_packet_evidence.v1",
        "status": status,
        "worklist_event_count": len(rows),
        "candidate_event_count": len(matched_rows),
        "exact_match_event_count": len(exact_rows),
        "strict_packet_valid_event_count": len(exact_rows),
        "consequence_chain_event_count": chain_count,
        "qualified_provider_packet_count": 0,
        "frequency_bound": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "rows": rows,
        "interpretation": (
            "Saved external-model outputs reached strict packet and exact worklist checks "
            "where reported; evidence remains diagnostic and is never promoted to qualified "
            "provider coverage or facility risk."
        ),
    }


__all__ = ["build_provider_worklist_packet_evidence"]
