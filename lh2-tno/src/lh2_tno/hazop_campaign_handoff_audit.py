"""Recompute and audit the structural contents of a HAZOP facility handoff.

The handoff carries three independent diagnostics: HAZOP scenario identity,
equipment-state to provider-release identity, and release-to-risk-atom chain
closure.  This module recomputes those diagnostics from the nested campaign
and compares them with the embedded records.  A partial provider/domain
chain is reported explicitly; it is never upgraded to a qualified facility
QRA result.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import canonical_digest
from .equipment_state_release_audit import build_equipment_state_release_audit
from .hazop_scenario_trace_audit import audit_hazop_scenario_trace
from .risk_atom_chain_audit import build_risk_atom_chain_audit


SCHEMA = "prism.hazop_campaign_handoff_audit.v1"
_HANDOFF_SCHEMAS = {
    "prism.hazop_facility_campaign_handoff.v1",
    "prism.hazop_facility_campaign_branches.v1",
}


class HazopCampaignHandoffAuditError(ValueError):
    """Raised when a handoff cannot be audited as a mapping."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HazopCampaignHandoffAuditError(f"{label} must be an object")
    return value


def audit_hazop_campaign_handoff(
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute embedded handoff audits and fail closed on drift."""
    handoff = _object(handoff, "handoff")
    schema = handoff.get("schema_version")
    errors: list[str] = []
    if schema not in _HANDOFF_SCHEMAS:
        errors.append(f"unsupported HAZOP handoff schema: {schema!r}")
    campaign = _object(handoff.get("campaign"), "handoff.campaign")

    trace_wrapper = {
        "schema_version": schema,
        "status": handoff.get("status"),
        "campaign": campaign,
    }
    trace = audit_hazop_scenario_trace(trace_wrapper)
    state_release = build_equipment_state_release_audit(campaign)
    risk_chain = build_risk_atom_chain_audit(campaign)
    embedded = {
        "hazop_scenario_trace_audit": handoff.get("hazop_scenario_trace_audit"),
        "equipment_state_release_audit": handoff.get("equipment_state_release_audit"),
        "risk_atom_chain_audit": handoff.get("risk_atom_chain_audit"),
    }
    recomputed = {
        "hazop_scenario_trace_audit": trace,
        "equipment_state_release_audit": state_release,
        "risk_atom_chain_audit": risk_chain,
    }
    mismatches: list[str] = []
    for name, expected in recomputed.items():
        actual = embedded[name]
        if not isinstance(actual, Mapping):
            errors.append(f"handoff.{name} is missing or not an object")
            continue
        if canonical_digest(actual) != canonical_digest(expected):
            mismatches.append(name)
    if mismatches:
        errors.append("embedded audit differs from recomputed audit: " + ", ".join(mismatches))
    if trace["status"] != "HAZOP_SCENARIO_TRACE_COMPLETE":
        errors.append(
            "HAZOP scenario trace is not complete: "
            + "; ".join(trace.get("errors", []))
        )

    chain_closed = (
        state_release.get("status") == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
        and risk_chain.get("status") == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    )
    if errors:
        status = "HAZOP_CAMPAIGN_HANDOFF_AUDIT_BLOCKED"
    elif chain_closed:
        status = "HAZOP_CAMPAIGN_HANDOFF_AUDITED_CHAIN_CLOSED_DIAGNOSTIC"
    else:
        status = "HAZOP_CAMPAIGN_HANDOFF_AUDITED_CHAIN_PARTIAL"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "handoff_schema_version": schema,
        "facility_id": handoff.get("facility_id"),
        "campaign_digest": campaign.get("campaign_digest"),
        "hazop_scenario_trace_status": trace.get("status"),
        "equipment_state_release_status": state_release.get("status"),
        "risk_atom_chain_status": risk_chain.get("status"),
        "chain_closed": chain_closed,
        "embedded_audit_mismatch_count": len(mismatches),
        "blocking_reasons": list(dict.fromkeys(errors)),
        "policy": {
            "hazop_scenario_id_inferred": False,
            "frequency_inference_performed": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_promotion": False,
            "partial_chain_is_not_complete": True,
            "diagnostic_only": True,
        },
        "interpretation": (
            "The HAZOP handoff embeds reproducible identity and chain diagnostics. "
            "A partial state/release or release/damage chain remains visible and is not promoted."
        ),
    }


__all__ = ["SCHEMA", "HazopCampaignHandoffAuditError", "audit_hazop_campaign_handoff"]
