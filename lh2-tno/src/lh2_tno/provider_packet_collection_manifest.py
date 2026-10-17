"""Build an actionable, fail-closed provider-packet collection manifest."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.provider_packet_collection_manifest.v1"
REQUEST_SCHEMA = "prism.facility_evidence_request.v1"
REQUIRED_PROVIDER_INPUT_ORIGIN = "reviewed_measurement"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def build_provider_packet_collection_manifest(
    evidence_request: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert facility evidence requests into packet-collection rows.

    This function copies identity and evidence requirements only.  It never
    fabricates a release packet, qualification result, frequency, or risk
    value.  A row is closed only by the separate provider packet input audit.
    """
    if not isinstance(evidence_request, Mapping):
        raise ValueError("evidence_request must be an object")
    if evidence_request.get("schema_version") != REQUEST_SCHEMA:
        raise ValueError(f"evidence_request schema_version must be {REQUEST_SCHEMA}")
    case_requests = _rows(evidence_request.get("case_requests", []), "evidence_request.case_requests")
    promotion_gate = evidence_request.get("promotion_gate")
    promotion_gate = dict(promotion_gate) if isinstance(promotion_gate, Mapping) else {}
    default_strict_gate_requirements = [
        key for key, value in promotion_gate.items() if value is True
    ]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    blocking_reasons: list[str] = []
    for index, request in enumerate(case_requests):
        request_id = str(request.get("request_id") or f"case-request-{index + 1}").strip()
        event_id = str(request.get("event_id") or "").strip()
        component_id = str(request.get("component_id") or "").strip()
        branch_id = str(request.get("release_branch_id") or "").strip()
        condition_id = str(request.get("annual_condition_id") or "").strip()
        reasons: list[str] = []
        if not event_id:
            reasons.append("event_id is missing")
        if not component_id:
            reasons.append("component_id is missing")
        identity = request.get("exact_match_required")
        if not isinstance(identity, Mapping):
            identity = {}
            reasons.append("exact_match_required is missing")
        key = (event_id, component_id, branch_id, condition_id)
        if key in seen:
            reasons.append("duplicate facility case identity")
        seen.add(key)
        if reasons:
            blocking_reasons.extend(f"{request_id}: {reason}" for reason in reasons)
        rows.append({
            "collection_id": request_id,
            "status": "OPEN",
            "event_id": event_id,
            "asset_id": str(request.get("asset_id") or "").strip() or None,
            "component_id": component_id,
            "release_branch_id": branch_id or None,
            "annual_condition_id": condition_id or None,
            "scenario_families": _list(request.get("scenario_families", [])),
            "request_kind": request.get("request_kind"),
            "qualification_required": request.get("qualification_required") is True,
            "required_input_origin": str(
                request.get("required_input_origin") or REQUIRED_PROVIDER_INPUT_ORIGIN
            ).strip(),
            "current_case_status": request.get("current_status"),
            "gap_class": request.get("gap_class"),
            "exact_match_required": dict(identity),
            "required_provider_evidence": _list(request.get("required_provider_evidence", [])),
            "strict_gate_requirements": (
                _list(request.get("strict_gate_requirements", []))
                or list(default_strict_gate_requirements)
            ),
            "current_release_boundary": request.get("current_release_boundary"),
            "current_boundary_gaps": _list(request.get("current_boundary_gaps", [])),
            "release_path": None,
            "qualification_path": None,
            "blocking_reasons": reasons,
        })

    if not case_requests:
        blocking_reasons.append("facility evidence request contains no case_requests")
    return {
        "schema": SCHEMA,
        "status": "OPEN_PROVIDER_PACKET_COLLECTION" if not blocking_reasons else "INVALID_PROVIDER_PACKET_COLLECTION_MANIFEST",
        "facility_id": evidence_request.get("facility_id"),
        "source_evidence_request_schema": evidence_request.get("schema_version"),
        "source_evidence_request_status": evidence_request.get("status"),
        "provider_input_origin_policy": (
            dict(evidence_request["provider_input_origin_policy"])
            if isinstance(evidence_request.get("provider_input_origin_policy"), Mapping)
            else {
                "required_for_qualification": REQUIRED_PROVIDER_INPUT_ORIGIN,
                "accepted_for_diagnostic_only": ["synthetic", "model_prediction"],
                "frequency_inference_allowed": False,
            }
        ),
        "promotion_gate": promotion_gate,
        "strict_gate_catalog": dict(evidence_request.get("strict_gate_catalog", {}))
        if isinstance(evidence_request.get("strict_gate_catalog"), Mapping)
        else {},
        "request_count": len(rows),
        "open_request_count": sum(row["status"] == "OPEN" for row in rows),
        "qualified_packet_count": 0,
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "release_packet_is_not_created": True,
            "qualification_is_not_inferred": True,
            "required_provider_input_origin": REQUIRED_PROVIDER_INPUT_ORIGIN,
            "facility_ir_fn_promotion": False,
            "closed_only_by": "audit_provider_packet_inputs plus exact facility case coverage and independent validation",
        },
    }


__all__ = [
    "REQUEST_SCHEMA",
    "SCHEMA",
    "REQUIRED_PROVIDER_INPUT_ORIGIN",
    "build_provider_packet_collection_manifest",
]
