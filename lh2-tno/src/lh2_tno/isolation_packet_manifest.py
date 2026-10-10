"""Build a fail-closed packet collection manifest for isolation branches."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.provider_packet_collection_manifest.v1"
CAMPAIGN_SCHEMA = "prism.facility_risk_ledger.v1"
EXTENSION_SCHEMA = "prism.isolation_union_extension_verification.v1"


def _sequence(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return list(value)


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in _sequence(value) if str(item).strip()]


def _identity(case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = case.get("provider_packet_identity")
    return value if isinstance(value, Mapping) else {}


def build_isolation_provider_packet_collection_manifest(
    campaign_result: Mapping[str, Any],
    extension_verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Create open collection rows without fabricating qualification evidence.

    The diagnostic campaign is used only to copy case identity and its current
    release boundary.  Every row stays ``OPEN`` and every promotion flag stays
    false until a separate provider packet and qualification sidecar are
    audited against the exact identity.
    """
    if not isinstance(campaign_result, Mapping):
        raise ValueError("campaign_result must be an object")
    campaign_schema = campaign_result.get("schema_version") or campaign_result.get("schema")
    if campaign_schema not in (None, CAMPAIGN_SCHEMA):
        raise ValueError(f"campaign_result schema must be {CAMPAIGN_SCHEMA} when declared")
    if not isinstance(extension_verification, Mapping):
        raise ValueError("extension_verification must be an object")
    if extension_verification.get("schema") != EXTENSION_SCHEMA:
        raise ValueError(f"extension_verification schema must be {EXTENSION_SCHEMA}")
    cases = [row for row in _sequence(campaign_result.get("cases")) if isinstance(row, Mapping)]
    expected_cases = extension_verification.get("isolation_counts", {}).get("cases")
    if not isinstance(expected_cases, int) or expected_cases != len(cases):
        raise ValueError("extension verification isolation case count does not match campaign")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    blocking_reasons: list[str] = []
    for index, case in enumerate(cases):
        identity = _identity(case)
        event_id = str(case.get("event_id") or identity.get("event_id") or "").strip()
        component_id = str(
            identity.get("component_id") or case.get("component_id") or ""
        ).strip()
        branch_id = str(case.get("release_branch_id") or "").strip()
        condition_id = str(case.get("annual_condition_id") or "").strip()
        row_id = (
            f"{event_id}/{branch_id}/{condition_id}/"
            "isolation-provider-packet-request"
        )
        reasons: list[str] = []
        if not event_id:
            reasons.append("event_id is missing")
        if not component_id:
            reasons.append("component_id is missing")
        if not branch_id:
            reasons.append("release_branch_id is missing")
        if not condition_id:
            reasons.append("annual_condition_id is missing")
        key = (event_id, component_id, branch_id, condition_id)
        if key in seen:
            reasons.append("duplicate isolation case identity")
        seen.add(key)
        if reasons:
            blocking_reasons.extend(f"case-{index + 1}: {reason}" for reason in reasons)

        mass_ledger = case.get("mass_ledger")
        termination = case.get("termination")
        boundary = {
            "termination": termination,
            "mass_ledger": mass_ledger,
            "domain_assessment": case.get("domain_assessment"),
            "diagnostic_identity_only": identity.get("diagnostic_identity_only") is True,
        }
        exact_match = {
            "event_id": event_id,
            "component_id": component_id,
            "port_ids": _strings(identity.get("port_ids")),
            "provider_source_digests": _strings(identity.get("provider_source_digests")),
            "provider_result_digests": _strings(identity.get("provider_result_digests")),
        }
        rows.append(
            {
                "collection_id": row_id,
                "status": "OPEN",
                "event_id": event_id,
                "asset_id": str(case.get("asset_id") or "").strip() or None,
                "component_id": component_id,
                "release_branch_id": branch_id,
                "annual_condition_id": condition_id,
                "scenario_families": _strings(case.get("scenario_families")),
                "request_kind": "QUALIFIED_PROVIDER_PACKET",
                "qualification_required": True,
                "current_case_status": case.get("status"),
                "gap_class": "QUALIFICATION_EVIDENCE_WITHHELD",
                "exact_match_required": exact_match,
                "required_provider_evidence": [
                    "qualified actual provider status with source/result SHA-256 digests and evidence identifier",
                    "exact event, component, isolation branch, accident port, opening geometry, position and direction",
                    "provider-owned time history with command, valve response and explicit termination basis",
                    "provider mass and energy closure with initial/final inventory and residuals",
                    "independent physical validation or a declared validation gap for the isolation boundary",
                    "success trace with closed-seat leakage and post-close flow, or failure trace with declared horizon",
                    "canonical equipment state snapshot and provider echo for the release boundary",
                ],
                "strict_gate_requirements": [
                    "qualified_provider_packet_required",
                    "exact_event_component_port_and_digest_match_required",
                    "independent_physical_validation_required",
                    "complete_declared_scope_required",
                    "facility_ir_fn_remains_withheld_until_all_true",
                ],
                "current_release_boundary": boundary,
                "current_boundary_gaps": [
                    "diagnostic isolation response is model-prediction evidence only",
                    "qualified provider packet and qualification sidecar are absent",
                ],
                "release_path": None,
                "qualification_path": None,
                "blocking_reasons": reasons,
            }
        )

    if not cases:
        blocking_reasons.append("isolation campaign contains no cases")
    return {
        "schema": SCHEMA,
        "status": (
            "OPEN_PROVIDER_PACKET_COLLECTION"
            if not blocking_reasons
            else "INVALID_PROVIDER_PACKET_COLLECTION_MANIFEST"
        ),
        "facility_id": campaign_result.get("facility_id"),
        "source_campaign_schema": campaign_schema or CAMPAIGN_SCHEMA,
        "source_campaign_status": campaign_result.get("status"),
        "source_extension_schema": extension_verification.get("schema"),
        "source_extension_status": extension_verification.get("status"),
        "promotion_gate": {
            "qualified_provider_packet_required": True,
            "exact_event_component_port_and_digest_match_required": True,
            "independent_physical_validation_required": True,
            "complete_declared_scope_required": True,
            "facility_ir_fn_remains_withheld_until_all_true": True,
        },
        "strict_gate_catalog": {
            "ISOLATION_PROVIDER_EVIDENCE": "replace diagnostic isolation response with a qualified provider packet and qualification sidecar",
            "ISOLATION_TERMINATION": "provide provider-owned isolation success/failure timing and mass closure",
            "ISOLATION_STATE_SNAPSHOT": "provide canonical state snapshot and provider echo for every isolation case",
        },
        "request_count": len(rows),
        "open_request_count": sum(row["status"] == "OPEN" for row in rows),
        "qualified_packet_count": 0,
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "release_packet_is_not_created": True,
            "qualification_is_not_inferred": True,
            "diagnostic_provider_response_is_not_promoted": True,
            "facility_ir_fn_promotion": False,
            "closed_only_by": "audit_provider_packet_inputs plus exact case coverage and independent validation",
        },
    }


__all__ = [
    "CAMPAIGN_SCHEMA",
    "EXTENSION_SCHEMA",
    "SCHEMA",
    "build_isolation_provider_packet_collection_manifest",
]
