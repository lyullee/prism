"""Audit alignment of a facility evidence request and its provider template.

This audit checks the intake contract only.  It does not read or qualify a
provider packet, assign frequency, infer a release, or enable facility QRA.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.facility_provider_intake_audit.v1"
FACILITY_REQUEST_SCHEMA = "prism.facility_evidence_request.v1"
TEMPLATE_SCHEMA = "prism.provider_qualification_sidecar_manifest.v1"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _identity(request: Mapping[str, Any]) -> dict[str, Any]:
    value = request.get("exact_match_required")
    return dict(value) if isinstance(value, Mapping) else {}


def _entry_identity(entry: Mapping[str, Any]) -> dict[str, Any]:
    value = entry.get("requested_exact_identity")
    if isinstance(value, Mapping):
        return dict(value)
    value = entry.get("expected_identity")
    return dict(value) if isinstance(value, Mapping) else {}


def _compare_identity(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    mismatches: list[str] = []
    keys = (
        "event_id",
        "component_id",
        "hazop_scenario_id",
        "operating_mode",
        "port_ids",
        "reviewed_frequency_port_ids",
        "provider_source_digests",
        "provider_result_digests",
    )
    for key in keys:
        if key in expected and actual.get(key) != expected.get(key):
            mismatches.append(key)
    return mismatches


def audit_facility_provider_intake_template(
    facility_request: Mapping[str, Any],
    template: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed alignment report for a  facility provider template."""
    if not isinstance(facility_request, Mapping):
        raise ValueError("facility_request must be an object")
    if not isinstance(template, Mapping):
        raise ValueError("template must be an object")

    request_rows = _as_list(facility_request.get("case_requests"))
    template_rows = _as_list(template.get("entries"))
    request_by_id: dict[str, Mapping[str, Any]] = {}
    duplicate_request_ids: list[str] = []
    for row in request_rows:
        if not isinstance(row, Mapping):
            continue
        request_id = str(row.get("request_id") or "").strip()
        if not request_id:
            continue
        if request_id in request_by_id:
            duplicate_request_ids.append(request_id)
        request_by_id[request_id] = row

    entry_ids: list[str] = []
    duplicate_entry_ids: list[str] = []
    rows: list[dict[str, Any]] = []
    for entry in template_rows:
        if not isinstance(entry, Mapping):
            rows.append({"status": "INVALID_ENTRY", "mismatches": ["entry_not_object"]})
            continue
        request_id = str(
            entry.get("facility_case_request_id") or entry.get("request_id") or ""
        ).strip()
        if request_id in entry_ids:
            duplicate_entry_ids.append(request_id)
        entry_ids.append(request_id)
        request = request_by_id.get(request_id)
        if request is None:
            rows.append({
                "request_id": request_id,
                "status": "UNEXPECTED_ENTRY",
                "mismatches": ["request_id_not_in_facility_request"],
            })
            continue
        expected = _identity(request)
        actual = _entry_identity(entry)
        mismatches = _compare_identity(expected, actual)
        if entry.get("required_input_origin") != request.get("required_input_origin"):
            mismatches.append("required_input_origin")
        if entry.get("provider_packet_port_ids") != request.get("provider_packet_port_ids"):
            mismatches.append("provider_packet_port_ids")
        rows.append({
            "request_id": request_id,
            "event_id": request.get("event_id"),
            "component_id": request.get("component_id"),
            "status": "ALIGNED" if not mismatches else "MISMATCH",
            "mismatches": sorted(set(mismatches)),
        })

    missing_ids = sorted(set(request_by_id) - set(entry_ids))
    unexpected_ids = sorted(set(entry_ids) - set(request_by_id))
    template_contract_ok = (
        template.get("schema_version") == TEMPLATE_SCHEMA
        and template.get("status") == "TEMPLATE_ONLY"
        and template.get("promotion_allowed") is False
        and template.get("frequency_inference_allowed") is False
        and template.get("facility_qra_allowed") is False
    )
    aligned_count = sum(row.get("status") == "ALIGNED" for row in rows)
    mismatch_count = sum(row.get("status") == "MISMATCH" for row in rows)
    blockers: list[str] = []
    if facility_request.get("schema_version") != FACILITY_REQUEST_SCHEMA:
        blockers.append("facility_request_schema_invalid")
    if not template_contract_ok:
        blockers.append("template_contract_invalid")
    if duplicate_request_ids:
        blockers.append("duplicate_facility_request_ids")
    if duplicate_entry_ids:
        blockers.append("duplicate_template_entry_ids")
    if missing_ids:
        blockers.append("facility_requests_missing_from_template")
    if unexpected_ids:
        blockers.append("template_entries_not_in_facility_request")
    if mismatch_count:
        blockers.append("template_identity_mismatch")
    status = "ALIGNED_TEMPLATE_ONLY" if not blockers else "BLOCKED_TEMPLATE_ALIGNMENT"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "facility_id": facility_request.get("facility_id"),
        "facility_request_schema": facility_request.get("schema_version"),
        "template_schema": template.get("schema_version"),
        "request_case_count": len(request_rows),
        "template_entry_count": len(template_rows),
        "aligned_entry_count": aligned_count,
        "mismatch_entry_count": mismatch_count,
        "missing_request_ids": missing_ids,
        "unexpected_entry_ids": unexpected_ids,
        "duplicate_request_ids": sorted(set(duplicate_request_ids)),
        "duplicate_entry_ids": sorted(set(duplicate_entry_ids)),
        "rows": rows,
        "blocking_reasons": blockers,
        "promotion_policy": {
            "template_only": True,
            "frequency_inference_allowed": False,
            "sensor_frequency_learning": False,
            "provider_qualification": False,
            "facility_qra_allowed": False,
        },
        "interpretation": (
            "Alignment proves that the intake template covers the declared facility cases. "
            "It is not provider evidence and cannot promote frequency, physical validation, "
            "or facility QRA."
        ),
    }


__all__ = ["SCHEMA", "audit_facility_provider_intake_template"]
