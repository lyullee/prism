"""Reconcile external provider responses with the facility evidence worklist.

The response-gap audit answers *what is missing from each provider response*.
This module answers the complementary question: *does that response identify
one of the exact facility cases currently requested?*  A component name or a
similar accident family is not enough for an exact match.  Missing identity,
port, qualification, origin, and evidence fields stay explicit, and this
report never promotes a packet or assigns a frequency.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.provider_response_facility_reconciliation.v1"
QUALIFIED_ORIGINS = frozenset({"reviewed_measurement", "provider_actual", "reviewed_actual", "native_provider"})


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _request_identity(request: Mapping[str, Any]) -> dict[str, Any]:
    exact = request.get("exact_match_required")
    exact = exact if isinstance(exact, Mapping) else {}
    return {
        "request_id": str(request.get("request_id") or ""),
        "event_id": exact.get("event_id", request.get("event_id")),
        "component_id": exact.get("component_id", request.get("component_id")),
        "port_ids": _list(exact.get("port_ids")),
        "release_branch_id": request.get("release_branch_id"),
        "annual_condition_id": request.get("annual_condition_id"),
    }


def _response_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "file": row.get("file"),
        "sha256": row.get("sha256"),
        "event_id": row.get("event_id"),
        "component_id": row.get("component_id"),
        "port_id": row.get("port_id"),
        "input_origin": row.get("input_origin"),
        "evidence_status": row.get("evidence_status"),
        "qualification_sidecar_present": row.get("qualification_sidecar_present") is True,
        "blocking_reasons": list(_list(row.get("blocking_reasons"))),
    }


def reconcile_provider_responses(
    response_gap_audit: Mapping[str, Any],
    facility_evidence_request: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an exact, non-promoting response-to-case reconciliation."""
    if not isinstance(response_gap_audit, Mapping):
        raise ValueError("response_gap_audit must be an object")
    if response_gap_audit.get("schema_version") != "prism.external_provider_response_gap_audit.v1":
        raise ValueError("response_gap_audit has an unsupported schema_version")
    if not isinstance(facility_evidence_request, Mapping):
        raise ValueError("facility_evidence_request must be an object")
    if facility_evidence_request.get("schema_version") != "prism.facility_evidence_request.v1":
        raise ValueError("facility_evidence_request has an unsupported schema_version")

    requests = [_request_identity(row) for row in _rows(facility_evidence_request.get("case_requests", []), "case_requests")]
    responses = [_response_identity(row) for row in _rows(response_gap_audit.get("rows", []), "response_gap_audit.rows")]
    response_rows: list[dict[str, Any]] = []
    exact_match_count = 0
    qualified_match_count = 0
    no_match_count = 0
    ambiguous_match_count = 0
    component_candidate_count = 0
    for response in responses:
        candidates: list[dict[str, Any]] = []
        component_candidates: list[dict[str, Any]] = []
        for request in requests:
            if request["component_id"] == response["component_id"]:
                component_candidates.append(request)
            if request["event_id"] != response["event_id"] or request["component_id"] != response["component_id"]:
                continue
            # A requested port list is mandatory for an exact provider case.
            # An empty list is therefore an explicit contract gap, not a match.
            if len(request["port_ids"]) != 1 or request["port_ids"][0] != response["port_id"]:
                continue
            candidates.append(request)
        if component_candidates:
            component_candidate_count += 1
        if not candidates:
            status = "NO_EXACT_CASE_MATCH"
            no_match_count += 1
        elif len(candidates) > 1:
            # One provider response must not silently cover multiple facility
            # cases. A case-specific release branch or condition is required.
            status = "AMBIGUOUS_CASE_MATCH"
            ambiguous_match_count += 1
        else:
            exact_match_count += 1
            qualified = (
                response["qualification_sidecar_present"]
                and response["input_origin"] in QUALIFIED_ORIGINS
                and response["evidence_status"] == "qualified_actual"
                and not response["blocking_reasons"]
            )
            status = "QUALIFIED_EXACT_CASE_MATCH" if qualified else "EXACT_CASE_MATCH_UNQUALIFIED"
            if qualified:
                qualified_match_count += 1
        response_rows.append({
            **response,
            "status": status,
            "exact_case_candidates": candidates,
            "component_case_candidates": component_candidates,
            "promotion_allowed": status == "QUALIFIED_EXACT_CASE_MATCH",
        })

    # Keep the inverse view as well.  A response-centric report can hide a
    # missing facility case when several responses happen to describe the
    # same component.  The facility case ledger is the authoritative unit for
    # QRA coverage, so every requested case gets an explicit status here.
    facility_case_rows: list[dict[str, Any]] = []
    facility_case_status_counts = {
        "QUALIFIED_RESPONSE": 0,
        "UNQUALIFIED_RESPONSE": 0,
        "COMPONENT_CANDIDATE_ONLY": 0,
        "NO_PROVIDER_RESPONSE": 0,
        "AMBIGUOUS_RESPONSE_IDENTITY": 0,
    }
    for request in requests:
        exact_rows = [
            row for row in response_rows
            if row["status"] in {
                "QUALIFIED_EXACT_CASE_MATCH",
                "EXACT_CASE_MATCH_UNQUALIFIED",
            }
            if any(candidate.get("request_id") == request["request_id"]
                   for candidate in row["exact_case_candidates"])
        ]
        component_rows = [
            row for row in response_rows
            if any(candidate.get("request_id") == request["request_id"]
                   for candidate in row["component_case_candidates"])
        ]
        qualified_rows = [
            row for row in exact_rows
            if row["status"] == "QUALIFIED_EXACT_CASE_MATCH"
        ]
        ambiguous_rows = [
            row for row in response_rows
            if row["status"] == "AMBIGUOUS_CASE_MATCH"
            and any(candidate.get("request_id") == request["request_id"]
                    for candidate in row["exact_case_candidates"])
        ]
        if qualified_rows:
            status = "QUALIFIED_RESPONSE"
        elif exact_rows:
            status = "UNQUALIFIED_RESPONSE"
        elif ambiguous_rows:
            status = "AMBIGUOUS_RESPONSE_IDENTITY"
        elif component_rows:
            status = "COMPONENT_CANDIDATE_ONLY"
        else:
            status = "NO_PROVIDER_RESPONSE"
        facility_case_status_counts[status] += 1
        facility_case_rows.append({
            **request,
            "status": status,
            "exact_response_files": [row.get("file") for row in exact_rows],
            "exact_response_digests": [row.get("sha256") for row in exact_rows],
            "qualified_response_files": [row.get("file") for row in qualified_rows],
            "ambiguous_response_files": [row.get("file") for row in ambiguous_rows],
            "component_candidate_response_files": [row.get("file") for row in component_rows],
            "promotion_allowed": False,
        })

    return {
        "schema_version": SCHEMA,
        "status": "QUALIFIED_RESPONSE_CASE_COVERAGE" if qualified_match_count == len(responses) and responses else "DIAGNOSTIC_RESPONSE_CASE_RECONCILIATION",
        "response_gap_audit_schema": response_gap_audit.get("schema_version"),
        "facility_evidence_request_schema": facility_evidence_request.get("schema_version"),
        "response_count": len(responses),
        "facility_case_count": len(requests),
        "exact_case_match_count": exact_match_count,
        "qualified_exact_case_match_count": qualified_match_count,
        "ambiguous_case_match_count": ambiguous_match_count,
        "component_candidate_response_count": component_candidate_count,
        "no_exact_case_match_count": no_match_count,
        "response_accounting_complete": (
            no_match_count + exact_match_count + ambiguous_match_count == len(responses)
        ),
        "rows": response_rows,
        "facility_case_rows": facility_case_rows,
        "facility_case_status_counts": facility_case_status_counts,
        "facility_case_exact_response_count": sum(
            value for key, value in facility_case_status_counts.items()
            if key in {"QUALIFIED_RESPONSE", "UNQUALIFIED_RESPONSE"}
        ),
        "facility_case_qualified_response_count": facility_case_status_counts[
            "QUALIFIED_RESPONSE"
        ],
        "facility_case_component_candidate_only_count": facility_case_status_counts[
            "COMPONENT_CANDIDATE_ONLY"
        ],
        "facility_case_no_provider_response_count": facility_case_status_counts[
            "NO_PROVIDER_RESPONSE"
        ],
        "facility_case_ambiguous_response_identity_count": facility_case_status_counts[
            "AMBIGUOUS_RESPONSE_IDENTITY"
        ],
        "promotion": {
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
        "policy": {
            "exact_event_component_port_identity_required": True,
            "qualification_sidecar_required": True,
            "qualified_origin_required": sorted(QUALIFIED_ORIGINS),
            "missing_identity_is_not_inferred": True,
            "ambiguous_case_identity_is_not_promoted": True,
            "facility_ir_fn_remains_withheld": True,
        },
    }


__all__ = ["SCHEMA", "reconcile_provider_responses"]
