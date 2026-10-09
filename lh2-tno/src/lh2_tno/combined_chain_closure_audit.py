"""Combine qualified-subset and operator-limited chain-closure audits.

The combined record answers one narrow question: did every declared event
reach a diagnostic final-harm atom?  It keeps the two evidence classes
separate, so operator-limited vertical events cannot be mistaken for qualified
provider packets or a complete facility QRA.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


COMBINED_CHAIN_CLOSURE_SCHEMA = "prism.facility_combined_chain_closure_audit.v1"


class CombinedChainClosureAuditError(ValueError):
    """Raised when component chain-closure audits are malformed."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CombinedChainClosureAuditError(f"{label} must be an object")
    return value


def build_combined_chain_closure_audit(
    packet_chain_audit: Mapping[str, Any],
    vertical_handoff_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one fail-closed diagnostic closure summary."""
    packet = _object(packet_chain_audit, "packet_chain_audit")
    vertical = _object(vertical_handoff_audit, "vertical_handoff_audit")
    packet_status = packet.get("status")
    vertical_status = vertical.get("status")
    packet_closed = int(packet.get("packet_chain_closed_event_count", 0))
    vertical_closed = int(vertical.get("vertical_chain_closed_event_count", 0))
    packet_events = int(packet.get("packet_event_count", 0))
    vertical_events = int(vertical.get("vertical_event_count", 0))
    declared_events = int(packet.get("campaign_event_count", 0))
    mismatch_ids = list(packet.get("packet_chain_mismatch_event_ids", ())) + list(
        vertical.get("vertical_chain_mismatch_event_ids", ())
    )
    mismatch_ids = list(dict.fromkeys(str(item) for item in mismatch_ids))
    class_counts = {
        "qualified_subset_diagnostic_events": packet_closed,
        "operator_limited_vertical_events": vertical_closed,
        "combined_diagnostic_events": packet_closed + vertical_closed,
    }
    event_count_matches = packet_events + vertical_events == declared_events
    all_closed = (
        packet_status == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
        and vertical_status == "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED"
        and packet_closed == packet_events
        and vertical_closed == vertical_events
        and event_count_matches
        and not mismatch_ids
        and vertical.get("all_declared_events_diagnostic_chain_closed") is True
    )
    return {
        "schema_version": COMBINED_CHAIN_CLOSURE_SCHEMA,
        "status": (
            "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED"
            if all_closed
            else "BLOCKED_COMBINED_CHAIN_CLOSURE"
        ),
        "facility_id": packet.get("facility_id") or vertical.get("facility_id"),
        "declared_event_count": declared_events,
        "packet_subset_event_count": packet_events,
        "packet_subset_closed_event_count": packet_closed,
        "vertical_handoff_event_count": vertical_events,
        "vertical_handoff_closed_event_count": vertical_closed,
        "combined_diagnostic_closed_event_count": packet_closed + vertical_closed,
        "event_count_matches_declared_scope": event_count_matches,
        "class_counts": class_counts,
        "mismatch_event_ids": mismatch_ids,
        "facility_ir_aggregate_closed": packet.get("facility_ir_aggregate_closed") is True,
        "facility_fn_aggregate_closed": packet.get("facility_fn_aggregate_closed") is True,
        "qualified_provider_packet_count": int(packet.get("qualified_provider_packet_count") or 0),
        "operator_limited_vertical_event_count": vertical_closed,
        "frequency_from_provider_packet": False,
        "physical_validation_claim": False,
        "facility_total_risk_available": False,
        "complete_facility_qra_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "All declared events reached a diagnostic final-harm atom when the qualified-subset "
            "closure and the operator-limited vertical closure are read together. The five vertical "
            "events remain a separate synthetic/operator-limited class; no provider qualification, "
            "field frequency, physical validation, facility total IR/F-N, or QRA promotion follows."
        ),
    }


__all__ = ["COMBINED_CHAIN_CLOSURE_SCHEMA", "CombinedChainClosureAuditError", "build_combined_chain_closure_audit"]
