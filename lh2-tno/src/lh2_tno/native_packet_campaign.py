"""Audit a facility campaign executed from native LH2 packet identities."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


def build_native_packet_campaign_execution_ledger(
    campaign: Mapping[str, Any],
    result: Mapping[str, Any],
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarise native-packet campaign consumption without promoting QRA claims."""
    routes = campaign.get("event_routes")
    events = result.get("events")
    cases = result.get("cases")
    if not isinstance(routes, list) or not isinstance(events, list) or not isinstance(cases, list):
        return {
            "schema_version": "prism.native_lh2dt_packet_campaign_execution.v1",
            "status": "MALFORMED_NATIVE_PACKET_CAMPAIGN",
            "diagnostic_only": True,
            "provider_packet_promoted": False,
            "frequency_from_provider_packet": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "interpretation": "campaign routes, events or cases are not arrays",
        }
    route_ids = {row.get("event_id") for row in routes if isinstance(row, Mapping)}
    result_event_ids = {row.get("id") for row in events if isinstance(row, Mapping)}
    case_ids = {row.get("event_id") for row in cases if isinstance(row, Mapping)}
    status_counts = Counter(
        str(row.get("status")) for row in cases if isinstance(row, Mapping)
    )
    identity_cases = [
        row for row in cases
        if isinstance(row, Mapping) and isinstance(row.get("provider_packet_identity"), Mapping)
    ]
    digest_cases = [
        row for row in identity_cases
        if row["provider_packet_identity"].get("provider_source_digests")
        and row["provider_packet_identity"].get("provider_result_digests")
    ]
    failed = [
        {"event_id": row.get("event_id"), "status": row.get("status"), "reason": row.get("reason")}
        for row in cases
        if isinstance(row, Mapping) and row.get("status") == "FAILED"
    ]
    operator_limited = [
        row.get("event_id") for row in cases
        if isinstance(row, Mapping) and row.get("status") == "EXECUTED_OPERATOR_LIMITED"
    ]
    chain_executed_count = sum(
        str(row.get("status", "")).startswith("EXECUTED")
        for row in cases
        if isinstance(row, Mapping)
    )
    packet_identity_consumed = (
        bool(cases)
        and len(identity_cases) == len(cases)
        and len(digest_cases) == len(cases)
        and route_ids == result_event_ids == case_ids
    )
    result_total_ir = result.get("total_facility_annual_ir_low_high")
    result_total_fn = result.get("total_facility_expected_death_fn_low_high")
    structural_match = (
        route_ids == result_event_ids == case_ids
        and len(cases) == len(routes)
        and packet_identity_consumed
    )
    return {
        "schema_version": "prism.native_lh2dt_packet_campaign_execution.v1",
        "status": "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED" if structural_match else "MALFORMED_NATIVE_PACKET_CAMPAIGN",
        "campaign_id": campaign.get("id"),
        "campaign_scope_provenance": campaign.get("scope_provenance"),
        "event_count": len(routes),
        "result_event_count": len(events),
        "case_count": len(cases),
        "chain_executed_case_count": chain_executed_count,
        "packet_identity_case_count": len(identity_cases),
        "packet_digest_case_count": len(digest_cases),
        "packet_identity_consumed": packet_identity_consumed,
        "route_event_set_matches_result": route_ids == result_event_ids,
        "route_event_set_matches_cases": route_ids == case_ids,
        "status_counts": dict(sorted(status_counts.items())),
        "operator_limited_case_count": len(operator_limited),
        "operator_limited_event_ids": sorted(str(value) for value in operator_limited),
        "failed_case_count": len(failed),
        "failed_cases": failed,
        "risk_atom_count": len(result.get("risk_atoms", [])) if isinstance(result.get("risk_atoms"), list) else None,
        "known_contribution_annual_ir_low_high": result.get("known_contribution_annual_ir_low_high"),
        "known_contribution_expected_death_fn_low_high": result.get("known_contribution_expected_death_fn_low_high"),
        "facility_total_risk_available": result_total_ir is not None or result_total_fn is not None,
        "frequency_from_provider_packet": False,
        "frequency_source": "campaign FrequencyPlan; provider packet carries release history only",
        "provider_packet_promoted": False,
        "facility_qra_claim": result.get("complete_facility_qra_claim") is True,
        "physical_validation_claim": result.get("physical_validation_claim") is True,
        "rebind_provenance_status": provenance.get("schema_version") if isinstance(provenance, Mapping) else None,
        "diagnostic_only": True,
        "policy": {
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "frequency_from_provider_packet": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
        "interpretation": (
            "The campaign consumed the strict native packet identities and preserved every failed or "
            "operator-limited case.  Literature frequencies remain campaign inputs; the provider packet "
            "does not generate a rate, and a partial campaign does not expose facility total IR/F-N."
        ),
    }


__all__ = ["build_native_packet_campaign_execution_ledger"]
