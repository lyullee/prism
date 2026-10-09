"""Cross-check the published PRISM readiness and facility ledgers.

The completion audit, facility assessment, evidence request, campaign ledger,
and two status ledgers are produced at different steps.  This module checks
that they still describe the same saved campaign before a result is shared.
It is deliberately an accounting check: it never promotes a provider packet,
assigns a frequency, or opens facility IR/F-N.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object and reject duplicate keys."""
    import json

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            value[key] = item
        return value

    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _check(
    checks: list[dict[str, Any]],
    name: str,
    condition: bool,
    evidence: Mapping[str, Any],
) -> None:
    checks.append({
        "name": name,
        "status": "PASS" if condition else "FAIL",
        "evidence": dict(evidence),
    })


def _endswith(value: Any, filename: str) -> bool:
    return isinstance(value, str) and value.replace("\\", "/").endswith(filename)


def build_status_consistency_report(
    *,
    current_status: Mapping[str, Any],
    development_goal: Mapping[str, Any],
    audit: Mapping[str, Any],
    assessment: Mapping[str, Any],
    evidence_request: Mapping[str, Any],
    ledger: Mapping[str, Any],
    coverage: Mapping[str, Any],
    audit_filename: str,
    assessment_filename: str,
    evidence_request_filename: str,
    ledger_filename: str,
    coverage_filename: str,
) -> dict[str, Any]:
    """Return a fail-closed cross-artifact consistency report."""
    checks: list[dict[str, Any]] = []

    audit_checks = audit.get("checks")
    audit_case_check = next(
        (
            row
            for row in audit_checks
            if isinstance(row, Mapping)
            and row.get("name") == "facility_case_provider_packet_coverage"
        ),
        None,
    ) if isinstance(audit_checks, Sequence) and not isinstance(audit_checks, (str, bytes)) else None
    audit_case_evidence = (
        audit_case_check.get("evidence", {})
        if isinstance(audit_case_check, Mapping)
        else {}
    )
    audit_combined_chain_check = next(
        (
            row
            for row in audit_checks
            if isinstance(row, Mapping)
            and row.get("name") == "diagnostic_combined_chain_closure"
        ),
        None,
    ) if isinstance(audit_checks, Sequence) and not isinstance(audit_checks, (str, bytes)) else None
    audit_combined_chain_evidence = (
        audit_combined_chain_check.get("evidence", {})
        if isinstance(audit_combined_chain_check, Mapping)
        else {}
    )
    audit_slabx_check = next(
        (
            row
            for row in audit_checks
            if isinstance(row, Mapping)
            and row.get("name") == "diagnostic_slabx_lh2_validation_evidence"
        ),
        None,
    ) if isinstance(audit_checks, Sequence) and not isinstance(audit_checks, (str, bytes)) else None
    audit_slabx_evidence = (
        audit_slabx_check.get("evidence", {})
        if isinstance(audit_slabx_check, Mapping)
        else {}
    )
    audit_realtime_cache_check = next(
        (
            row
            for row in audit_checks
            if isinstance(row, Mapping)
            and row.get("name") == "diagnostic_realtime_cache_benchmark"
        ),
        None,
    ) if isinstance(audit_checks, Sequence) and not isinstance(audit_checks, (str, bytes)) else None
    audit_realtime_cache_evidence = (
        audit_realtime_cache_check.get("evidence", {})
        if isinstance(audit_realtime_cache_check, Mapping)
        else {}
    )
    audit_domain_recovery_check = next(
        (
            row
            for row in audit_checks
            if isinstance(row, Mapping)
            and row.get("name") == "diagnostic_domain_recovery_audit"
        ),
        None,
    ) if isinstance(audit_checks, Sequence) and not isinstance(audit_checks, (str, bytes)) else None
    audit_domain_recovery_evidence = (
        audit_domain_recovery_check.get("evidence", {})
        if isinstance(audit_domain_recovery_check, Mapping)
        else {}
    )
    audit_check_count = len(audit_checks or ())
    audit_blocking_reason_count = len(audit.get("blocking_reasons", ()))
    # The completion audit grows as new evidence gates are added.  Compare
    # the saved report with the status ledger instead of freezing an old
    # check count and treating every new diagnostic gate as drift.
    _check(
        checks,
        "audit_identity",
        audit.get("status") == "INCOMPLETE_EVIDENCE"
        and audit_check_count > 0
        and audit_blocking_reason_count > 0,
        {
            "status": audit.get("status"),
            "check_count": audit_check_count,
            "blocking_reason_count": audit_blocking_reason_count,
        },
    )
    _check(
        checks,
        "audit_case_gate",
        audit_case_check is not None
        and audit_case_check.get("status") == "BLOCKED"
        and audit_case_evidence.get("case_request_count") == 34
        and audit_case_evidence.get("qualified_provider_case_count") == 0,
        {
            "case_request_count": audit_case_evidence.get("case_request_count"),
            "qualified_provider_case_count": audit_case_evidence.get(
                "qualified_provider_case_count"
            ),
        },
    )
    _check(
        checks,
        "audit_combined_chain_gate",
        audit_combined_chain_check is not None
        and audit_combined_chain_check.get("status") == "PASS"
        and audit_combined_chain_check.get("diagnostic_only") is True
        and audit_combined_chain_evidence.get("schema_version")
        == "prism.facility_combined_chain_closure_audit.v1"
        and audit_combined_chain_evidence.get("status")
        == "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED"
        and audit_combined_chain_evidence.get("declared_event_count") == 29
        and audit_combined_chain_evidence.get("packet_subset_closed_event_count") == 24
        and audit_combined_chain_evidence.get("vertical_handoff_closed_event_count") == 5
        and audit_combined_chain_evidence.get("combined_diagnostic_closed_event_count") == 29
        and audit_combined_chain_evidence.get("event_count_matches_declared_scope") is True
        and audit_combined_chain_evidence.get("mismatch_event_ids") == []
        and audit_combined_chain_evidence.get("facility_ir_aggregate_closed") is True
        and audit_combined_chain_evidence.get("facility_fn_aggregate_closed") is True
        and audit_combined_chain_evidence.get("qualified_provider_packet_count") == 0
        and audit_combined_chain_evidence.get("facility_qra_claim") is False,
        {
            "status": (
                audit_combined_chain_check.get("status")
                if isinstance(audit_combined_chain_check, Mapping)
                else None
            ),
            "diagnostic_only": (
                audit_combined_chain_check.get("diagnostic_only")
                if isinstance(audit_combined_chain_check, Mapping)
                else None
            ),
            "declared_event_count": audit_combined_chain_evidence.get("declared_event_count"),
            "packet_subset_closed_event_count": audit_combined_chain_evidence.get(
                "packet_subset_closed_event_count"
            ),
            "vertical_handoff_closed_event_count": audit_combined_chain_evidence.get(
                "vertical_handoff_closed_event_count"
            ),
            "combined_diagnostic_closed_event_count": audit_combined_chain_evidence.get(
                "combined_diagnostic_closed_event_count"
            ),
            "mismatch_event_ids": audit_combined_chain_evidence.get("mismatch_event_ids"),
            "qualified_provider_packet_count": audit_combined_chain_evidence.get(
                "qualified_provider_packet_count"
            ),
            "facility_qra_claim": audit_combined_chain_evidence.get("facility_qra_claim"),
        },
    )
    _check(
        checks,
        "audit_slabx_validation_gate",
        audit_slabx_check is not None
        and audit_slabx_check.get("status") == "PASS"
        and audit_slabx_check.get("diagnostic_only") is True
        and audit_slabx_evidence.get("schema_version")
        == "prism.slabx_lh2_validation_audit.v1"
        and audit_slabx_evidence.get("status")
        == "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
        and audit_slabx_evidence.get("check_count") == 5
        and isinstance(audit_slabx_evidence.get("metrics"), Mapping)
        and audit_slabx_evidence["metrics"].get("ffi_case_count") == 6
        and audit_slabx_evidence["metrics"].get("flacs_comparison_row_count") == 6
        and audit_slabx_evidence.get("physical_validation_claim") is False
        and audit_slabx_evidence.get("facility_qra_claim") is False
        and all(
            _endswith(
                status.get("slabx_lh2_validation_evidence_record"),
                "slabx_lh2_validation_audit_v1.json",
            )
            for status in (current_status, development_goal)
        ),
        {
            "status": (
                audit_slabx_check.get("status")
                if isinstance(audit_slabx_check, Mapping)
                else None
            ),
            "diagnostic_only": (
                audit_slabx_check.get("diagnostic_only")
                if isinstance(audit_slabx_check, Mapping)
                else None
            ),
            "schema_version": audit_slabx_evidence.get("schema_version"),
            "evidence_status": audit_slabx_evidence.get("status"),
            "check_count": audit_slabx_evidence.get("check_count"),
            "ffi_case_count": (
                audit_slabx_evidence.get("metrics", {}).get("ffi_case_count")
                if isinstance(audit_slabx_evidence.get("metrics"), Mapping)
                else None
            ),
            "flacs_comparison_row_count": (
                audit_slabx_evidence.get("metrics", {}).get("flacs_comparison_row_count")
                if isinstance(audit_slabx_evidence.get("metrics"), Mapping)
                else None
            ),
            "facility_qra_claim": audit_slabx_evidence.get("facility_qra_claim"),
        },
    )
    _check(
        checks,
        "audit_realtime_cache_benchmark_gate",
        audit_realtime_cache_check is not None
        and audit_realtime_cache_check.get("status") == "PASS"
        and audit_realtime_cache_check.get("diagnostic_only") is True
        and audit_realtime_cache_evidence.get("schema_version")
        == "prism.realtime_cache_benchmark.v1"
        and isinstance(audit_realtime_cache_evidence.get("cache_hits"), int)
        and audit_realtime_cache_evidence.get("cache_hits")
        == audit_realtime_cache_evidence.get("cache_sample_count")
        and audit_realtime_cache_evidence.get("cache_median_ms", float("inf")) <= 1000
        and audit_realtime_cache_evidence.get("cache_p95_ms", float("inf")) <= 1000
        and audit_realtime_cache_evidence.get("one_hz_deadline_s") == 1.0
        and audit_realtime_cache_evidence.get("fresh_physics_meets_one_hz") is False
        and audit_realtime_cache_evidence.get("cache_meets_one_hz_all_samples") is True
        and audit_realtime_cache_evidence.get("realtime_fresh_physics_claim") is False
        and all(
            _endswith(
                status.get("realtime_cache_benchmark_record"),
                "native_lh2_realtime_cache_benchmark_v1.json",
            )
            for status in (current_status, development_goal)
        ),
        {
            "status": (
                audit_realtime_cache_check.get("status")
                if isinstance(audit_realtime_cache_check, Mapping)
                else None
            ),
            "diagnostic_only": (
                audit_realtime_cache_check.get("diagnostic_only")
                if isinstance(audit_realtime_cache_check, Mapping)
                else None
            ),
            "schema_version": audit_realtime_cache_evidence.get("schema_version"),
            "cache_hits": audit_realtime_cache_evidence.get("cache_hits"),
            "cache_sample_count": audit_realtime_cache_evidence.get("cache_sample_count"),
            "cache_median_ms": audit_realtime_cache_evidence.get("cache_median_ms"),
            "cache_p95_ms": audit_realtime_cache_evidence.get("cache_p95_ms"),
            "fresh_physics_meets_one_hz": audit_realtime_cache_evidence.get(
                "fresh_physics_meets_one_hz"
            ),
            "cache_meets_one_hz_all_samples": audit_realtime_cache_evidence.get(
                "cache_meets_one_hz_all_samples"
            ),
        },
    )
    _check(
        checks,
        "audit_domain_recovery_gate",
        audit_domain_recovery_check is not None
        and audit_domain_recovery_check.get("status") == "PASS"
        and audit_domain_recovery_check.get("diagnostic_only") is True
        and audit_domain_recovery_evidence.get("schema") == "prism.domain_recovery_audit.v1"
        and audit_domain_recovery_evidence.get("status") == "DOMAIN_RECOVERY_REVIEWED"
        and audit_domain_recovery_evidence.get("event_count") == 24
        and audit_domain_recovery_evidence.get("baseline_domain_incomplete_event_count") == 6
        and audit_domain_recovery_evidence.get("recovery_domain_incomplete_event_count") == 6
        and isinstance(audit_domain_recovery_evidence.get("persistent_domain_incomplete_event_ids"), list)
        and len(audit_domain_recovery_evidence.get("persistent_domain_incomplete_event_ids")) == 6
        and audit_domain_recovery_evidence.get("facility_ir_fn_promotion") is False
        and all(
            _endswith(status.get("domain_recovery_audit_record"), "domain_recovery_audit_v1.json")
            for status in (current_status, development_goal)
        ),
        {
            "status": (
                audit_domain_recovery_check.get("status")
                if isinstance(audit_domain_recovery_check, Mapping)
                else None
            ),
            "diagnostic_only": (
                audit_domain_recovery_check.get("diagnostic_only")
                if isinstance(audit_domain_recovery_check, Mapping)
                else None
            ),
            "schema": audit_domain_recovery_evidence.get("schema"),
            "event_count": audit_domain_recovery_evidence.get("event_count"),
            "baseline_domain_incomplete_event_count": audit_domain_recovery_evidence.get(
                "baseline_domain_incomplete_event_count"
            ),
            "recovery_domain_incomplete_event_count": audit_domain_recovery_evidence.get(
                "recovery_domain_incomplete_event_count"
            ),
            "persistent_domain_incomplete_event_count": len(
                audit_domain_recovery_evidence.get("persistent_domain_incomplete_event_ids", [])
            )
            if isinstance(audit_domain_recovery_evidence.get("persistent_domain_incomplete_event_ids"), list)
            else None,
            "facility_ir_fn_promotion": audit_domain_recovery_evidence.get("facility_ir_fn_promotion"),
        },
    )

    assessment_coverage = assessment.get("facility_case_packet_coverage")
    assessment_coverage = assessment_coverage if isinstance(assessment_coverage, Mapping) else {}
    _check(
        checks,
        "assessment_gate",
        assessment.get("status") == "PARTIAL_FACILITY_SCOPE"
        and assessment.get("provider_packet_case_count") == 34
        and assessment.get("qualified_provider_packet_case_count") == 0
        and assessment.get("facility_case_packet_coverage_complete") is False
        and assessment.get("qualified_facility_qra_available") is False
        and assessment.get("facility_total_risk_available") is False,
        {
            "status": assessment.get("status"),
            "provider_packet_case_count": assessment.get("provider_packet_case_count"),
            "qualified_provider_packet_case_count": assessment.get(
                "qualified_provider_packet_case_count"
            ),
            "facility_case_packet_coverage_complete": assessment.get(
                "facility_case_packet_coverage_complete"
            ),
            "qualified_facility_qra_available": assessment.get(
                "qualified_facility_qra_available"
            ),
            "facility_total_risk_available": assessment.get("facility_total_risk_available"),
        },
    )
    _check(
        checks,
        "coverage_gate",
        coverage.get("status") == "NO_CASE_MATCH"
        and coverage.get("case_request_count") == 34
        and coverage.get("qualified_provider_case_count") == 0
        and assessment_coverage.get("coverage_status") == coverage.get("status")
        and assessment_coverage.get("case_request_count") == coverage.get("case_request_count")
        and assessment_coverage.get("qualified_provider_case_count")
        == coverage.get("qualified_provider_case_count"),
        {
            "coverage_status": coverage.get("status"),
            "case_request_count": coverage.get("case_request_count"),
            "qualified_provider_case_count": coverage.get("qualified_provider_case_count"),
        },
    )

    risk_atoms = ledger.get("risk_atoms")
    _check(
        checks,
        "ledger_accounting",
        ledger.get("status") == "PARTIAL_FACILITY_SCOPE"
        and ledger.get("event_count") == 29
        and ledger.get("case_count") == 34
        and ledger.get("uncomputed_case_count") == 35
        and ledger.get("conditional_case_count") == 34
        and ledger.get("conditional_executed_case_count") == 34
        and ledger.get("conditional_uncomputed_case_count") == 0
        and isinstance(risk_atoms, Sequence)
        and not isinstance(risk_atoms, (str, bytes))
        and len(risk_atoms) == 136
        and ledger.get("provider_packet_case_count") == 34
        and ledger.get("qualified_provider_packet_case_count") == 0,
        {
            "status": ledger.get("status"),
            "event_count": ledger.get("event_count"),
            "case_count": ledger.get("case_count"),
            "strict_uncomputed_case_count": ledger.get("uncomputed_case_count"),
            "conditional_case_count": ledger.get("conditional_case_count"),
            "conditional_executed_case_count": ledger.get("conditional_executed_case_count"),
            "conditional_uncomputed_case_count": ledger.get("conditional_uncomputed_case_count"),
            "risk_atom_count": len(risk_atoms) if isinstance(risk_atoms, Sequence) else None,
            "qualified_provider_packet_case_count": ledger.get(
                "qualified_provider_packet_case_count"
            ),
        },
    )
    component_contributions = ledger.get("component_contributions")
    component_contributions = (
        component_contributions if isinstance(component_contributions, Mapping) else {}
    )
    component_risk_ranking = ledger.get("component_risk_ranking")
    ranking_rows = (
        component_risk_ranking.get("rows", ())
        if isinstance(component_risk_ranking, Mapping)
        else ()
    )
    ranking_ids = {
        str(row.get("component_id"))
        for row in ranking_rows
        if isinstance(row, Mapping) and row.get("component_id")
    }
    _check(
        checks,
        "component_risk_ranking",
        isinstance(component_risk_ranking, Mapping)
        and component_risk_ranking.get("status") == "AVAILABLE"
        and component_risk_ranking.get("component_count") == len(component_contributions)
        and len(ranking_rows) == len(component_contributions)
        and ranking_ids == {str(key) for key in component_contributions}
        and component_risk_ranking.get("frequency_reallocation_performed") is False
        and component_risk_ranking.get("facility_ir_fn_promotion") is False
        and isinstance(assessment.get("component_risk_ranking"), Mapping)
        and assessment["component_risk_ranking"].get("component_count")
        == component_risk_ranking.get("component_count"),
        {
            "status": (
                component_risk_ranking.get("status")
                if isinstance(component_risk_ranking, Mapping)
                else None
            ),
            "ledger_component_count": len(component_contributions),
            "ranking_component_count": (
                component_risk_ranking.get("component_count")
                if isinstance(component_risk_ranking, Mapping)
                else None
            ),
            "assessment_component_count": (
                assessment.get("component_risk_ranking", {}).get("component_count")
                if isinstance(assessment.get("component_risk_ranking"), Mapping)
                else None
            ),
            "frequency_reallocation_performed": (
                component_risk_ranking.get("frequency_reallocation_performed")
                if isinstance(component_risk_ranking, Mapping)
                else None
            ),
            "facility_ir_fn_promotion": (
                component_risk_ranking.get("facility_ir_fn_promotion")
                if isinstance(component_risk_ranking, Mapping)
                else None
            ),
        },
    )
    _check(
        checks,
        "evidence_request_identity",
        evidence_request.get("status") == "OPEN_EVIDENCE_REQUEST"
        and evidence_request.get("case_request_count") == 34
        and len(evidence_request.get("family_requests", ())) == 12
        and len(evidence_request.get("component_requests", ())) == 8,
        {
            "status": evidence_request.get("status"),
            "case_request_count": evidence_request.get("case_request_count"),
            "family_request_count": len(evidence_request.get("family_requests", ())),
            "component_request_count": len(evidence_request.get("component_requests", ())),
        },
    )

    for label, status in (("current_status", current_status), ("development_goal", development_goal)):
        _check(
            checks,
            f"{label}_audit_pointer",
            _endswith(status.get("ijhe_completion_audit_latest_record"), audit_filename)
            and status.get("ijhe_completion_audit_latest_check_count") == audit_check_count
            and status.get("ijhe_completion_audit_latest_blocking_reason_count")
            == audit_blocking_reason_count,
            {
                "record": status.get("ijhe_completion_audit_latest_record"),
                "check_count": status.get("ijhe_completion_audit_latest_check_count"),
                "blocking_reason_count": status.get(
                    "ijhe_completion_audit_latest_blocking_reason_count"
                ),
            },
        )
        _check(
            checks,
            f"{label}_assessment_pointer",
            _endswith(status.get("ijhe_completion_audit_latest_facility_assessment_record"), assessment_filename)
            and isinstance(status.get("full_portable_test_count"), int)
            and status.get("full_portable_test_count", 0) > 0
            and status.get("full_portable_test_status")
            == f"{status.get('full_portable_test_count')} passed",
            {
                "assessment_record": status.get(
                    "ijhe_completion_audit_latest_facility_assessment_record"
                ),
                "full_portable_test_count": status.get("full_portable_test_count"),
            },
        )
        _check(
            checks,
            f"{label}_evidence_request_pointer",
            _endswith(status.get("facility_evidence_request_latest_record"), evidence_request_filename),
            {"record": status.get("facility_evidence_request_latest_record")},
        )
        if "facility_ledger_latest_record" in status:
            _check(
                checks,
                f"{label}_ledger_pointer",
                _endswith(status.get("facility_ledger_latest_record"), ledger_filename),
                {"record": status.get("facility_ledger_latest_record")},
            )
        if "ijhe_audit_latest_record" in status:
            _check(
                checks,
                f"{label}_legacy_audit_alias",
                _endswith(status.get("ijhe_audit_latest_record"), audit_filename)
                and status.get("ijhe_audit_latest_check_count") == audit_check_count,
                {
                    "record": status.get("ijhe_audit_latest_record"),
                    "check_count": status.get("ijhe_audit_latest_check_count"),
                },
            )

    report = {
        "schema_version": "prism.readiness_status_consistency.v1",
        "status": "CONSISTENT" if all(row["status"] == "PASS" for row in checks) else "INCONSISTENT",
        "diagnostic_only": True,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_ir_fn_promotion": False,
        "artifact_filenames": {
            "audit": audit_filename,
            "assessment": assessment_filename,
            "evidence_request": evidence_request_filename,
            "ledger": ledger_filename,
            "coverage": coverage_filename,
        },
        "checks": checks,
        "blocking_reasons": [
            row["name"] for row in checks if row["status"] != "PASS"
        ],
    }
    return report


__all__ = ["build_status_consistency_report", "load_json_object"]
