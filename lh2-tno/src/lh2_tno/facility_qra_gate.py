"""Reconcile the independent gates that control strict facility QRA promotion.

The facility assessment, provider audit, and physical-validation matrix are
deliberately separate records.  This module gives dashboards and review
documents one conservative decision without merging evidence or inferring a
missing value.  A diagnostic IR/F-N sum can remain available while the strict
promotion decision is withheld.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA = "prism.facility_qra_gate_summary.v1"


class FacilityQRAGateError(ValueError):
    """Raised when a gate summary input is structurally invalid."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FacilityQRAGateError(f"{name} must be a mapping")
    return value


def _bool(value: Any) -> bool:
    return value is True


def build_facility_qra_gate_summary(
    assessment: Mapping[str, Any],
    provider_audit: Mapping[str, Any],
    validation_matrix: Mapping[str, Any],
    *,
    assessment_record: str,
    provider_audit_record: str,
    validation_record: str,
) -> dict[str, Any]:
    """Return one fail-closed strict-QRA promotion decision.

    The function only reads existing records.  It never reruns physics,
    assigns frequency, or treats a missing field as a successful gate.
    """
    assessment = _mapping(assessment, "assessment")
    provider_audit = _mapping(provider_audit, "provider_audit")
    validation_matrix = _mapping(validation_matrix, "validation_matrix")
    ledger = _mapping(assessment.get("facility_risk_ledger"), "assessment.facility_risk_ledger")
    strict_boundary = _mapping(
        ledger.get("strict_release_boundary"),
        "assessment.facility_risk_ledger.strict_release_boundary",
    )
    port_binding = _mapping(
        ledger.get("frequency_port_binding"),
        "assessment.facility_risk_ledger.frequency_port_binding",
    )
    trace = _mapping(
        ledger.get("risk_atom_case_traceability"),
        "assessment.facility_risk_ledger.risk_atom_case_traceability",
    )
    provider_gate = _mapping(
        assessment.get("provider_qualification_coverage"),
        "assessment.provider_qualification_coverage",
    )

    gates: dict[str, dict[str, Any]] = {}
    scope_complete = (
        ledger.get("status") == "FACILITY_SCOPE_EXECUTED"
        and _bool(ledger.get("declared_scope_numerically_complete"))
        and ledger.get("uncomputed_case_count") == 0
    )
    scope_reasons = [] if scope_complete else [
        "facility scope is partial or retains uncomputed cases"
    ]
    gates["facility_scope"] = {
        "complete": scope_complete,
        "status": ledger.get("status"),
        "event_count": ledger.get("event_count"),
        "case_count": ledger.get("case_count"),
        "uncomputed_case_count": ledger.get("uncomputed_case_count"),
        "blocking_reasons": scope_reasons,
    }

    release_complete = _bool(strict_boundary.get("strict_release_boundary_ready"))
    gates["release_boundary"] = {
        "complete": release_complete,
        "status": "READY" if release_complete else "WITHHELD",
        "withheld_case_count": strict_boundary.get("withheld_case_count"),
        "blocking_reasons": list(strict_boundary.get("blocking_reasons", [])),
    }

    provider_complete = (
        _bool(provider_gate.get("complete"))
        and provider_audit.get("qualification_status") == "QUALIFIED_FULL_WORKLIST"
        and provider_audit.get("qualified_provider_packet_count")
        == provider_audit.get("release_identity_request_count")
        and provider_audit.get("qualified_provider_packet_count", 0) > 0
    )
    provider_reasons = [] if provider_complete else list(
        provider_gate.get("blocking_reasons", [])
    )
    if not provider_reasons:
        provider_reasons = ["qualified provider packet coverage is unavailable"]
    gates["provider_qualification"] = {
        "complete": provider_complete,
        "status": provider_audit.get("status"),
        "qualification_status": provider_audit.get("qualification_status"),
        "release_identity_count": provider_audit.get("release_identity_request_count"),
        "exact_match_count": provider_audit.get("exact_match_count"),
        "qualified_provider_packet_count": provider_audit.get(
            "qualified_provider_packet_count"
        ),
        "blocking_reasons": provider_reasons,
    }

    validation_claims = {
        key: validation_matrix.get(key)
        for key in (
            "physical_validation_claim",
            "full_chain_validation_claim",
            "accident_release_validation_claim",
            "facility_qra_claim",
        )
    }
    physical_complete = (
        validation_matrix.get("schema_version") == "prism.validation_evidence_matrix.v1"
        and validation_matrix.get("status") == "INDEPENDENT_VALIDATED"
        and validation_matrix.get("decision") == "FACILITY_QRA_ALLOWED"
        and all(value is True for value in validation_claims.values())
    )
    gates["physical_validation"] = {
        "complete": physical_complete,
        "status": validation_matrix.get("status"),
        "decision": validation_matrix.get("decision"),
        "evidence_domain_count": len(validation_matrix.get("evidence_domains", []))
        if isinstance(validation_matrix.get("evidence_domains"), list)
        else 0,
        **validation_claims,
        "blocking_reasons": []
        if physical_complete
        else ["independent full-chain physical validation is not available"],
    }

    frequency_complete = (
        port_binding.get("status") == "ALIGNED"
        and _bool(port_binding.get("facility_qra_allowed"))
        and port_binding.get("frequency_inference_allowed") is False
    )
    gates["frequency_port_binding"] = {
        "complete": frequency_complete,
        "status": port_binding.get("status"),
        "port_scoped_event_count": port_binding.get("port_scoped_event_count"),
        "port_unbound_event_count": port_binding.get("port_unbound_event_count"),
        "mismatch_count": port_binding.get("mismatch_count"),
        "frequency_inference_allowed": port_binding.get("frequency_inference_allowed"),
        "blocking_reasons": []
        if frequency_complete
        else ["reviewed accident-port binding is incomplete or mismatched"],
    }

    trace_complete = (
        trace.get("status") == "CLOSED"
        and trace.get("unmatched_risk_atom_count") == 0
        and trace.get("ambiguous_risk_atom_count") == 0
        and trace.get("withheld_risk_atom_count") == 0
    )
    gates["case_traceability"] = {
        "complete": trace_complete,
        "status": trace.get("status"),
        "risk_atom_count": trace.get("risk_atom_count"),
        "eligible_risk_atom_count": trace.get("eligible_risk_atom_count"),
        "withheld_risk_atom_count": trace.get("withheld_risk_atom_count"),
        "unmatched_risk_atom_count": trace.get("unmatched_risk_atom_count"),
        "ambiguous_risk_atom_count": trace.get("ambiguous_risk_atom_count"),
        "blocking_reasons": []
        if trace_complete
        else list(trace.get("blocking_reasons", [])),
    }

    promotion_allowed = all(gate["complete"] for gate in gates.values())
    blocking_reasons = [
        f"{name}: {reason}"
        for name, gate in gates.items()
        if not gate["complete"]
        for reason in gate["blocking_reasons"]
    ]
    return {
        "schema_version": SCHEMA,
        "status": "FACILITY_QRA_ALLOWED" if promotion_allowed else "FACILITY_QRA_WITHHELD",
        "facility_id": assessment.get("facility_id"),
        "promotion_allowed": promotion_allowed,
        "facility_qra_claim": promotion_allowed,
        "diagnostic_facility_risk_available": _bool(
            assessment.get("conditional_diagnostic_facility_risk_available")
        ),
        "gates": gates,
        "blocking_reasons": blocking_reasons,
        "source_records": {
            "assessment": assessment_record,
            "provider_audit": provider_audit_record,
            "validation_matrix": validation_record,
        },
        "policy": {
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "missing_evidence_assigned_zero_risk": False,
            "diagnostic_ir_fn_may_remain_available": True,
            "all_gates_required_for_facility_qra": True,
        },
    }
