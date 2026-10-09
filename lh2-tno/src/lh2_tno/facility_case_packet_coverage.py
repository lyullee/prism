"""Audit qualified provider evidence against facility case requests.

The facility evidence request is intentionally a request document rather than
a risk result.  This module provides the next, fail-closed boundary: when a
provider sends promoted ``prism.provider_packet_evidence.v1`` rows, compare
each row with the exact event/component/port/source-digest/result-digest
identity required by every facility case.  A packet may be reused for more
than one weather case of the same event; case coverage is counted separately
from unique provider-event coverage.

No frequency, branch probability, consequence result, or facility IR/F-N value
is created here.  Exact identity is necessary for promotion, but it is not a
claim of physical validation.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .campaign import ProviderPacketEvidence
from .provider_packet_promotion import load_provider_packet_evidence_catalog


SCHEMA = "prism.facility_case_provider_coverage.v1"


def _sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(value)


def _request_identity(request: Mapping[str, Any]) -> dict[str, Any]:
    exact = request.get("exact_match_required")
    if not isinstance(exact, Mapping):
        exact = {}
    return {
        "event_id": exact.get("event_id", request.get("event_id")),
        "component_id": exact.get("component_id", request.get("component_id")),
        "port_ids": _sequence(exact.get("port_ids")),
        "provider_source_digests": _sequence(exact.get("provider_source_digests")),
        "provider_result_digests": _sequence(exact.get("provider_result_digests")),
    }


def _evidence_identity(evidence: ProviderPacketEvidence) -> dict[str, Any]:
    return {
        "event_id": evidence.event_id,
        "component_id": evidence.component_id,
        "port_ids": tuple(evidence.port_ids),
        "provider_source_digests": tuple(evidence.provider_source_digests),
        "provider_result_digests": tuple(evidence.provider_result_digests),
    }


def _identity_reasons(
    requested: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for field in (
        "event_id",
        "component_id",
        "port_ids",
        "provider_source_digests",
        "provider_result_digests",
    ):
        if requested.get(field) != evidence.get(field):
            reasons.append(f"{field} mismatch")
    return reasons


def audit_facility_case_packet_coverage(
    request_document: Mapping[str, Any],
    provider_evidence: (
        Sequence[ProviderPacketEvidence | Mapping[str, Any]]
        | Mapping[str, Any]
        | str
    ) = (),
) -> dict[str, Any]:
    """Compare an evidence-request document with promoted provider evidence.

    ``provider_evidence`` accepts the same object/array/wrapper forms as the
    provider-promotion loader.  An empty catalog is valid and produces an
    explicit missing-evidence report, which is useful for the current
    diagnostic facility state.
    """
    if not isinstance(request_document, Mapping):
        raise ValueError("request_document must be a JSON object")
    raw_requests = request_document.get("case_requests", ())
    if not isinstance(raw_requests, Sequence) or isinstance(raw_requests, (str, bytes)):
        raise ValueError("request_document.case_requests must be an array")
    requests = [row for row in raw_requests if isinstance(row, Mapping)]
    if len(requests) != len(raw_requests):
        raise ValueError("every case request must be an object")

    if provider_evidence in (None, (), [], {}):
        evidence_rows: tuple[ProviderPacketEvidence, ...] = ()
    else:
        evidence_rows = load_provider_packet_evidence_catalog(provider_evidence)
    # Keep every evidence row for an event.  One initiating event can have
    # multiple provider packets when release branches (or equipment ports)
    # have different exact source/result digests.  Collapsing to a single
    # dictionary entry would make the result depend on input order and could
    # incorrectly mark a valid case as a digest mismatch.
    evidence_by_event: dict[str, list[ProviderPacketEvidence]] = {}
    for row in evidence_rows:
        evidence_by_event.setdefault(row.event_id, []).append(row)

    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    matched_case_ids: set[str] = set()
    matched_events: set[str] = set()
    for index, request in enumerate(requests):
        request_id = str(request.get("request_id") or f"case-{index + 1}")
        requested = _request_identity(request)
        event_id = requested.get("event_id")
        reasons: list[str] = []
        if not all(
            isinstance(requested.get(field), str) and str(requested.get(field)).strip()
            for field in ("event_id", "component_id")
        ):
            reasons.append("request exact provider identity is incomplete")
        if not requested["port_ids"]:
            reasons.append("request exact port_ids are empty")
        candidates = evidence_by_event.get(event_id, [])
        if not candidates:
            status = "MISSING_QUALIFIED_PROVIDER_EVIDENCE"
            reasons.append("no qualified provider evidence has this event_id")
            evidence_identity = None
        else:
            # Select by the complete exact identity, rather than by event ID
            # alone.  If no candidate matches, report the closest candidate's
            # mismatches so the evidence request remains actionable.
            candidate_identities = [
                _evidence_identity(candidate) for candidate in candidates
            ]
            exact_candidates = [
                identity
                for identity in candidate_identities
                if not _identity_reasons(requested, identity)
            ]
            evidence_identity = (
                exact_candidates[0]
                if exact_candidates
                else candidate_identities[0]
            )
            reasons.extend(_identity_reasons(requested, evidence_identity))
            status = "QUALIFIED_EXACT_MATCH" if not reasons else "UNQUALIFIED_EVIDENCE_MISMATCH"
            if not reasons:
                matched_case_ids.add(request_id)
                if isinstance(event_id, str):
                    matched_events.add(event_id)
        status_counts[status] += 1
        rows.append({
            "request_id": request_id,
            "event_id": event_id,
            "annual_condition_id": request.get("annual_condition_id"),
            "release_branch_id": request.get("release_branch_id"),
            "component_id": requested.get("component_id"),
            "status": status,
            "requested_identity": {
                **requested,
                "port_ids": list(requested["port_ids"]),
                "provider_source_digests": list(requested["provider_source_digests"]),
                "provider_result_digests": list(requested["provider_result_digests"]),
            },
            "evidence_identity": (
                None
                if evidence_identity is None
                else {
                    **evidence_identity,
                    "port_ids": list(evidence_identity["port_ids"]),
                    "provider_source_digests": list(evidence_identity["provider_source_digests"]),
                    "provider_result_digests": list(evidence_identity["provider_result_digests"]),
                }
            ),
            "blocking_reasons": list(dict.fromkeys(reasons)),
        })

    request_events = {
        identity.get("event_id")
        for identity in (_request_identity(request) for request in requests)
        if identity.get("event_id")
    }
    extra_evidence_events = sorted(set(evidence_by_event) - request_events)
    blockers: list[str] = []
    if status_counts["MISSING_QUALIFIED_PROVIDER_EVIDENCE"]:
        blockers.append("one or more facility cases have no qualified provider evidence")
    if status_counts["UNQUALIFIED_EVIDENCE_MISMATCH"]:
        blockers.append("one or more provider evidence rows fail exact facility identity")
    if extra_evidence_events:
        blockers.append("provider evidence contains events outside the facility case request")
    if not requests:
        blockers.append("facility request document contains no case requests")

    full = bool(requests) and not blockers
    status = "QUALIFIED_FULL_CASE_COVERAGE" if full else (
        "NO_CASE_MATCH" if not matched_case_ids else "PARTIAL_CASE_COVERAGE"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "facility_id": request_document.get("facility_id"),
        "case_request_count": len(requests),
        "qualified_provider_event_count": len(matched_events),
        "qualified_provider_case_count": len(matched_case_ids),
        "provider_evidence_row_count": len(evidence_rows),
        "extra_provider_event_count": len(extra_evidence_events),
        "extra_provider_events": extra_evidence_events,
        "status_counts": dict(sorted(status_counts.items())),
        "blocking_reasons": blockers,
        "case_rows": rows,
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "sensor_frequency_learning": False,
            "exact_case_identity_required": True,
            "physical_validation_claim": False,
            "facility_ir_fn_promotion": (
                "requires this full case gate plus independent scope and validation gates"
            ),
        },
    }


__all__ = ["SCHEMA", "audit_facility_case_packet_coverage"]
