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


def _sidecar(parent: Path, names: tuple[str, ...]) -> tuple[Mapping[str, Any] | None, str | None]:
    """Load the first declared evidence sidecar without guessing its values.

    Provider folders are exchanged by several teams, so the audit accepts the
    documented short names while keeping the path in the report.  A malformed
    sidecar is returned as ``None`` with its path; callers can then distinguish
    a missing record from a record that failed qualification validation.
    """
    for name in names:
        path = parent / name
        if not path.is_file():
            continue
        try:
            value = _load(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None, str(path)
        return (value if isinstance(value, Mapping) else None), str(path)
    return None, None


def _unwrap(value: Mapping[str, Any] | None, key: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    nested = value.get(key)
    return nested if isinstance(nested, Mapping) else value


def _qualification_sidecar_matches(
    releases: list[Mapping[str, Any]],
    payload: Mapping[str, Any] | None,
) -> tuple[bool, str | None]:
    """Check a qualification sidecar against every resolved endpoint."""
    record = _unwrap(payload, "provider_qualification")
    if record is None:
        return False, "qualification_sidecar_invalid"
    if record.get("schema_version") != "prism.provider_qualification_evidence.v1":
        return False, "qualification_sidecar_invalid"
    if record.get("status") != "qualified_actual":
        return False, "qualification_sidecar_invalid"
    if record.get("provider_origin") not in {"native_provider", "reviewed_actual"}:
        return False, "qualification_sidecar_invalid"
    if not isinstance(record.get("evidence_id"), str) or not str(record.get("evidence_id")).strip():
        return False, "qualification_sidecar_invalid"
    if not releases:
        return False, "qualification_sidecar_invalid"
    event_ids = {str(release.get("event_id")) for release in releases}
    component_ids = {str(release.get("component_id")) for release in releases}
    ports = tuple(str(release.get("port_id")) for release in releases)
    if record.get("event_id") not in event_ids or record.get("component_id") not in component_ids:
        return False, "qualification_sidecar_identity_mismatch"
    declared_ports = record.get("port_ids")
    if declared_ports is None:
        declared_port = record.get("port_id")
        declared_ports = [declared_port] if declared_port is not None else None
    if not isinstance(declared_ports, (list, tuple)) or tuple(str(item) for item in declared_ports) != ports:
        return False, "qualification_sidecar_identity_mismatch"
    source_digests = tuple(str(release.get("provider_source_digest")) for release in releases)
    result_digests = tuple(str(release.get("provider_result_digest")) for release in releases)
    for digest in (*source_digests, *result_digests):
        if len(digest) != 64:
            return False, "qualification_sidecar_digest_mismatch"
        try:
            int(digest, 16)
        except ValueError:
            return False, "qualification_sidecar_digest_mismatch"
    declared_sources = record.get("provider_source_digests")
    if declared_sources is None:
        declared_source = record.get("provider_source_digest")
        declared_sources = [declared_source] if declared_source is not None else None
    declared_results = record.get("provider_result_digests")
    if declared_results is None:
        declared_result = record.get("provider_result_digest")
        declared_results = [declared_result] if declared_result is not None else None
    if (
        not isinstance(declared_sources, (list, tuple))
        or tuple(str(item) for item in declared_sources) != source_digests
        or not isinstance(declared_results, (list, tuple))
        or tuple(str(item) for item in declared_results) != result_digests
    ):
        return False, "qualification_sidecar_digest_mismatch"
    return True, None


def _physical_validation_present(
    verification: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None,
) -> tuple[bool, str | None]:
    """Recognize an explicit independent-validation record only."""
    record = _unwrap(payload, "physical_validation_evidence")
    if record is None and isinstance(verification, Mapping):
        record = _unwrap(verification, "physical_validation_evidence")
    if record is None:
        return False, "physical_validation_evidence_missing"
    if record.get("status") != "independent_validated":
        return False, "physical_validation_evidence_invalid"
    evidence_id = record.get("evidence_id")
    digest = record.get("evidence_digest")
    if not isinstance(evidence_id, str) or not evidence_id.strip() or not isinstance(digest, str) or len(digest) != 64:
        return False, "physical_validation_evidence_invalid"
    try:
        int(digest, 16)
    except ValueError:
        return False, "physical_validation_evidence_invalid"
    return True, None


def _qualification_readiness(
    releases: list[Mapping[str, Any]],
    verification: Mapping[str, Any] | None,
    *,
    qualification: Mapping[str, Any] | None,
    physical_validation: Mapping[str, Any] | None,
    qualification_path: str | None,
    physical_validation_path: str | None,
) -> dict[str, Any]:
    """Explain why an exact packet is still withheld from qualification.

    Exact identity and a successful exporter run are useful diagnostic facts,
    but they do not establish that the release represents a qualified facility
    accident.  Keep the reasons machine-readable so an evidence request can be
    closed one item at a time without changing the promotion policy.
    """

    origins = sorted({
        str(release.get("input_origin"))
        for release in releases
        if release.get("input_origin") not in (None, "")
    })
    termination_bases = sorted({
        str(release.get("termination_basis"))
        for release in releases
        if release.get("termination_basis") not in (None, "")
    })
    limitations = []
    if isinstance(verification, Mapping):
        raw_limitations = verification.get("limitations", ())
        if isinstance(raw_limitations, (list, tuple)):
            limitations = [str(item) for item in raw_limitations if str(item).strip()]

    if qualification is None and qualification_path is None:
        qualification_present, qualification_reason = False, "qualification_sidecar_missing"
    else:
        qualification_present, qualification_reason = _qualification_sidecar_matches(
            releases, qualification
        )
    if physical_validation is None and physical_validation_path is None:
        physical_validation_present, physical_validation_reason = (
            False,
            "physical_validation_evidence_missing",
        )
    elif physical_validation is None:
        physical_validation_present, physical_validation_reason = (
            False,
            "physical_validation_evidence_invalid",
        )
    else:
        physical_validation_present, physical_validation_reason = _physical_validation_present(
            verification, physical_validation
        )
    blockers: list[str] = []
    if not qualification_present:
        blockers.append(qualification_reason or "qualification_sidecar_missing")
    if not physical_validation_present:
        blockers.append(physical_validation_reason or "physical_validation_evidence_missing")
    verification_status = str(verification.get("status", "")) if verification else ""
    if "OPERATOR_LIMITED" in verification_status or (
        isinstance(verification, Mapping) and verification.get("operator_limited") is True
    ):
        blockers.append("operator_limited_input")
    if any(origin in {"synthetic", "screening_only"} for origin in origins):
        blockers.append("synthetic_or_screening_input_origin")
    limitation_text = " ".join(limitations).lower()
    if any(token in limitation_text for token in ("synthetic", "diagnostic horizon", "screening")):
        blockers.append("synthetic_or_screening_boundary_declared")
    if any("residual inventory" in str(release.get("termination_provenance", "")).lower()
           for release in releases):
        blockers.append("termination_leaves_declared_inventory_residual")
    return {
        "status": "BLOCKED_REVIEW" if blockers else "REVIEW_REQUIRED",
        "blockers": list(dict.fromkeys(blockers)),
        "input_origins": origins,
        "termination_bases": termination_bases,
        "verification_status": verification_status or None,
        "verification_limitations": limitations,
        "qualification_sidecar_present": qualification_present,
        "qualification_sidecar_path": qualification_path,
        "physical_validation_evidence_present": physical_validation_present,
        "physical_validation_evidence_path": physical_validation_path,
    }


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
    qualification, qualification_path = _sidecar(
        parent, ("provider_qualification.json", "qualification.json")
    )
    physical_validation, physical_validation_path = _sidecar(
        parent,
        ("physical_validation.json", "physical_validation_evidence.json", "validation.json"),
    )
    if qualification is None and isinstance(candidate["response"], Mapping):
        embedded = candidate["response"].get("provider_qualification")
        if isinstance(embedded, Mapping):
            qualification = embedded
            qualification_path = str(response_path)
    if physical_validation is None and isinstance(verification, Mapping):
        embedded = verification.get("physical_validation_evidence")
        if isinstance(embedded, Mapping):
            physical_validation = embedded
            physical_validation_path = str(parent / "verification.json")
    readiness = _qualification_readiness(
        matching,
        verification,
        qualification=qualification,
        physical_validation=physical_validation,
        qualification_path=qualification_path,
        physical_validation_path=physical_validation_path,
    )
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
        "qualification_readiness": readiness,
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
    readiness_rows = [
        row["evidence"].get("qualification_readiness", {})
        for row in exact_rows
        if isinstance(row.get("evidence"), Mapping)
    ]
    readiness_counts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    origin_counts: dict[str, int] = {}
    for readiness in readiness_rows:
        status = str(readiness.get("status", "UNKNOWN"))
        readiness_counts[status] = readiness_counts.get(status, 0) + 1
        for blocker in readiness.get("blockers", ()):
            blocker_counts[str(blocker)] = blocker_counts.get(str(blocker), 0) + 1
        for origin in readiness.get("input_origins", ()):
            origin_counts[str(origin)] = origin_counts.get(str(origin), 0) + 1
    qualification_sidecar_count = sum(
        bool(readiness.get("qualification_sidecar_present"))
        for readiness in readiness_rows
    )
    physical_validation_evidence_count = sum(
        bool(readiness.get("physical_validation_evidence_present"))
        for readiness in readiness_rows
    )
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
        "qualification_readiness": {
            "status_counts": dict(sorted(readiness_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "input_origin_counts": dict(sorted(origin_counts.items())),
            "qualification_sidecar_present_count": qualification_sidecar_count,
            "physical_validation_evidence_present_count": physical_validation_evidence_count,
        },
        "rows": rows,
        "interpretation": (
            "Saved external-model outputs reached strict packet and exact worklist checks "
            "where reported; evidence remains diagnostic and is never promoted to qualified "
            "provider coverage or facility risk. Qualification readiness is reported separately "
            "so operator-limited and synthetic boundaries cannot be mistaken for actual evidence."
        ),
    }


__all__ = ["build_provider_worklist_packet_evidence"]
