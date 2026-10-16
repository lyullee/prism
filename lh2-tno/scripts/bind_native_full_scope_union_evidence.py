#!/usr/bin/env python3
"""Bind validation and realtime evidence to a native LH2 union assessment.

This command is an evidence-bookkeeping step after
``run_native_full_scope_union_assessment.py``.  It deliberately does not run a
new provider solver or promote a synthetic packet.  Instead it builds the
fail-closed validation matrix, reruns the IJHE readiness audit with the
measured cache benchmark, and records the resulting gate state beside the
union assessment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.completion_audit import build_ijhe_completion_audit  # noqa: E402
from lh2_tno.validation_evidence_matrix import (  # noqa: E402
    build_validation_evidence_matrix,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _with_record(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = _load(path)
    value["_record_path"] = str(path)
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.union_dir
    scope = _load(output_dir / "scope_matrix.json")
    campaign = _load(output_dir / "campaign_result.json")
    facility = _load(output_dir / "facility_assessment.json")
    facility_case_packet_coverage_path = output_dir / "facility_case_packet_coverage.json"
    facility_case_packet_coverage = (
        _load(facility_case_packet_coverage_path)
        if facility_case_packet_coverage_path.is_file()
        else None
    )
    if facility_case_packet_coverage is not None:
        facility_case_packet_coverage["_record_path"] = str(
            facility_case_packet_coverage_path
        )
    current_status = _load(args.current_status)

    source_audit = _load(args.ijhe_audit_source)
    matrix = build_validation_evidence_matrix(
        args.pool_record,
        args.equipment_audit,
        output_dir / "facility_assessment.json",
        native_contract_path=args.native_contract,
        slabx_validation_path=args.slabx_validation_evidence,
        ijhe_audit_path=args.ijhe_audit_source,
        external_sweep_path=args.external_sweep,
    )
    matrix["_record_path"] = str(output_dir / "validation_evidence_matrix.json")

    provider_worklist = _with_record(args.provider_worklist)
    registry = _with_record(args.diagnostic_adapter_registry)
    facility_record = dict(facility)
    facility_record["_record_path"] = str(output_dir / "facility_assessment.json")
    vertical = _with_record(args.vertical_handoff_result)
    realtime = _with_record(args.realtime_cache_benchmark)
    native_full_bore = _with_record(args.native_full_bore_result)
    state_snapshot_binding = _with_record(args.state_snapshot_binding_audit)
    native_state_snapshot_campaign = _with_record(args.native_state_snapshot_campaign_ledger)
    native_scope_packet_catalog = _with_record(args.native_scope_packet_catalog_verification)
    slabx_validation = _with_record(args.slabx_validation_evidence)
    native_model_contract_audit = _with_record(args.native_model_contract_audit)
    frequency_provenance_report = _with_record(args.frequency_provenance_report)
    diagnostic_worklist_evidence = _with_record(args.diagnostic_worklist_evidence)
    native_packet_campaign_ledger = _with_record(args.native_packet_campaign_ledger)
    native_binding_reconciliation = _with_record(args.native_binding_reconciliation)
    domain_recovery_audit = _with_record(args.domain_recovery_audit)
    observed_state_evidence = _with_record(args.observed_state_evidence)
    observed_state_model_binding_audit = _with_record(
        args.observed_state_model_binding_audit
    )
    external_equipment_model_contract_audit = _with_record(
        args.external_equipment_model_contract_audit
    )
    scope_ledger_consistency = _with_record(args.scope_ledger_consistency)
    risk_atom_chain_audit = _with_record(args.risk_atom_chain_audit)
    equipment_state_release_audit = _with_record(args.equipment_state_release_audit)
    facility_aggregate_closure_audit = _with_record(
        args.facility_aggregate_closure_audit
    )
    facility_component_contribution_audit = _with_record(
        args.facility_component_contribution_audit
    )
    facility_frequency_uncertainty_audit = _with_record(
        args.facility_frequency_uncertainty_audit
    )
    isolation_union_extension_verification = _with_record(
        args.isolation_union_extension_verification
    )

    # Keep the audit inputs explicit. The completion-audit API has a long
    # optional signature; positional arguments here previously mixed the
    # facility assessment, uncertainty ledger, and provider worklist domains.
    uncertainty_result = None
    frequency_scenarios_path = output_dir / "frequency_scenarios.json"
    if frequency_scenarios_path.is_file():
        uncertainty_result = _with_record(frequency_scenarios_path)
    audit = build_ijhe_completion_audit(
        current_status,
        scope,
        campaign,
        uncertainty_result=uncertainty_result,
        provider_worklist=provider_worklist,
        diagnostic_adapter_registry=registry,
        facility_assessment=facility_record,
        facility_case_packet_coverage=facility_case_packet_coverage,
        vertical_handoff_result=vertical,
        native_model_contract_audit=native_model_contract_audit,
        frequency_provenance_report=frequency_provenance_report,
        diagnostic_worklist_evidence=diagnostic_worklist_evidence,
        native_packet_campaign_ledger=native_packet_campaign_ledger,
        validation_evidence_matrix=matrix,
        native_binding_reconciliation=native_binding_reconciliation,
        realtime_cache_benchmark=realtime,
        native_full_bore_result=native_full_bore,
        domain_recovery_audit=domain_recovery_audit,
        state_snapshot_binding_audit=state_snapshot_binding,
        native_scope_packet_catalog_verification=native_scope_packet_catalog,
        slabx_validation_evidence=slabx_validation,
        observed_state_evidence=observed_state_evidence,
        scope_ledger_consistency=scope_ledger_consistency,
        risk_atom_chain_audit=risk_atom_chain_audit,
        equipment_state_release_audit=equipment_state_release_audit,
        facility_aggregate_closure_audit=facility_aggregate_closure_audit,
        facility_component_contribution_audit=facility_component_contribution_audit,
        facility_frequency_uncertainty_audit=facility_frequency_uncertainty_audit,
        isolation_union_extension_verification=isolation_union_extension_verification,
        observed_state_model_binding_audit=observed_state_model_binding_audit,
        external_equipment_model_contract_audit=external_equipment_model_contract_audit,
    )

    verification_path = output_dir / "verification.json"
    verification = _load(verification_path)
    verification.update(
        {
            "validation_evidence_matrix_status": matrix["status"],
            "validation_evidence_matrix_decision": matrix["decision"],
            "validation_evidence_matrix_domain_count": len(matrix["evidence_domains"]),
            "validation_evidence_matrix_physical_validation_claim": matrix[
                "physical_validation_claim"
            ],
            "validation_evidence_matrix_facility_qra_claim": matrix["facility_qra_claim"],
            "realtime_cache_benchmark_cache_hits": realtime.get("cache_hits") if realtime else None,
            "realtime_cache_benchmark_cache_p95_ms": realtime.get("cache_p95_ms") if realtime else None,
            "realtime_cache_benchmark_fresh_physics_elapsed_ms": (
                realtime.get("fresh_physics_elapsed_ms") if realtime else None
            ),
            "realtime_cache_benchmark_fresh_physics_meets_one_hz": (
                realtime.get("fresh_physics_meets_one_hz") if realtime else None
            ),
            "realtime_cache_benchmark_persistent_fresh_physics": (
                realtime.get("persistent_fresh_physics") if realtime else None
            ),
            "ijhe_audit_status": audit["status"],
            "ijhe_audit_check_count": len(audit["checks"]),
            "ijhe_audit_pass_count": sum(row["status"] == "PASS" for row in audit["checks"]),
            "ijhe_audit_blocked_count": sum(
                row["status"] == "BLOCKED" for row in audit["checks"]
            ),
            "ijhe_audit_blocked_check_ids": [
                row["name"] for row in audit["checks"] if row["status"] == "BLOCKED"
            ],
            "state_snapshot_binding_status": (
                state_snapshot_binding.get("status") if state_snapshot_binding else None
            ),
            "state_snapshot_binding_record_count": (
                state_snapshot_binding.get("record_count") if state_snapshot_binding else None
            ),
            "state_snapshot_binding_bound_count": (
                state_snapshot_binding.get("bound_count") if state_snapshot_binding else None
            ),
            "state_snapshot_binding_unbound_count": (
                state_snapshot_binding.get("unbound_count") if state_snapshot_binding else None
            ),
            "native_state_snapshot_campaign_status": (
                native_state_snapshot_campaign.get("status")
                if native_state_snapshot_campaign else None
            ),
            "native_state_snapshot_campaign_event_count": (
                native_state_snapshot_campaign.get("event_count")
                if native_state_snapshot_campaign else None
            ),
            "native_state_snapshot_campaign_bound_event_count": (
                native_state_snapshot_campaign.get("state_snapshot_campaign_reconciliation", {}).get(
                    "bound_event_count"
                )
                if native_state_snapshot_campaign else None
            ),
            "native_state_snapshot_campaign_provider_result_digest_mismatch_count": (
                len(
                    native_state_snapshot_campaign.get(
                        "state_snapshot_campaign_reconciliation", {}
                    ).get("provider_result_digest_mismatch_event_ids", [])
                )
                if native_state_snapshot_campaign else None
            ),
            "native_scope_packet_catalog_status": (
                native_scope_packet_catalog.get("status") if native_scope_packet_catalog else None
            ),
            "native_scope_packet_catalog_event_count": (
                native_scope_packet_catalog.get("frequency_event_count")
                if native_scope_packet_catalog else None
            ),
            "native_scope_packet_catalog_exact_packet_count": (
                native_scope_packet_catalog.get("exact_native_packet_count")
                if native_scope_packet_catalog else None
            ),
            "slabx_validation_evidence_status": (
                slabx_validation.get("status") if slabx_validation else None
            ),
            "slabx_validation_evidence_check_count": (
                len(slabx_validation.get("checks", []))
                if slabx_validation and isinstance(slabx_validation.get("checks"), list)
                else None
            ),
            "slabx_validation_evidence_physical_validation_claim": (
                slabx_validation.get("physical_validation_claim") if slabx_validation else None
            ),
            "facility_case_packet_coverage_status": (
                facility_case_packet_coverage.get("status")
                if facility_case_packet_coverage
                else None
            ),
            "facility_case_packet_coverage_case_count": (
                facility_case_packet_coverage.get("case_request_count")
                if facility_case_packet_coverage
                else None
            ),
            "facility_case_packet_coverage_qualified_case_count": (
                facility_case_packet_coverage.get("qualified_provider_case_count")
                if facility_case_packet_coverage
                else None
            ),
            "scope_ledger_consistency_status": (
                scope_ledger_consistency.get("status")
                if scope_ledger_consistency
                else verification.get("scope_ledger_consistency_status")
            ),
            "scope_ledger_consistency_blocking_reason_count": (
                len(scope_ledger_consistency.get("blocking_reasons", []))
                if scope_ledger_consistency
                else verification.get("scope_ledger_consistency_blocking_reason_count")
            ),
            "risk_atom_chain_audit_status": (
                risk_atom_chain_audit.get("status")
                if risk_atom_chain_audit
                else verification.get("risk_atom_chain_audit_status")
            ),
            "risk_atom_chain_audit_case_count": (
                risk_atom_chain_audit.get("case_count")
                if risk_atom_chain_audit
                else verification.get("risk_atom_chain_audit_case_count")
            ),
            "risk_atom_chain_audit_complete_case_count": (
                risk_atom_chain_audit.get("complete_case_count")
                if risk_atom_chain_audit
                else verification.get("risk_atom_chain_audit_complete_case_count")
            ),
            "risk_atom_chain_audit_risk_atom_count": (
                risk_atom_chain_audit.get("risk_atom_count")
                if risk_atom_chain_audit
                else verification.get("risk_atom_chain_audit_risk_atom_count")
            ),
            "risk_atom_chain_audit_blocking_reason_count": (
                len(risk_atom_chain_audit.get("blocking_reasons", []))
                if risk_atom_chain_audit
                else verification.get("risk_atom_chain_audit_blocking_reason_count")
            ),
            "equipment_state_release_audit_status": (
                equipment_state_release_audit.get("status")
                if equipment_state_release_audit
                else verification.get("equipment_state_release_audit_status")
            ),
            "equipment_state_release_audit_case_count": (
                equipment_state_release_audit.get("case_count")
                if equipment_state_release_audit
                else verification.get("equipment_state_release_audit_case_count")
            ),
            "equipment_state_release_audit_complete_case_count": (
                equipment_state_release_audit.get("complete_case_count")
                if equipment_state_release_audit
                else verification.get("equipment_state_release_audit_complete_case_count")
            ),
            "equipment_state_release_audit_component_count": (
                equipment_state_release_audit.get("component_count")
                if equipment_state_release_audit
                else verification.get("equipment_state_release_audit_component_count")
            ),
            "equipment_state_release_audit_blocking_reason_count": (
                len(equipment_state_release_audit.get("blocking_reasons", []))
                if equipment_state_release_audit
                else verification.get("equipment_state_release_audit_blocking_reason_count")
            ),
            "facility_aggregate_closure_audit_status": (
                facility_aggregate_closure_audit.get("status")
                if facility_aggregate_closure_audit
                else verification.get("facility_aggregate_closure_audit_status")
            ),
            "facility_aggregate_closure_audit_risk_atom_count": (
                facility_aggregate_closure_audit.get("risk_atom_count")
                if facility_aggregate_closure_audit
                else verification.get("facility_aggregate_closure_audit_risk_atom_count")
            ),
            "facility_aggregate_closure_audit_ir_mismatch_count": (
                facility_aggregate_closure_audit.get("ir_mismatch_count")
                if facility_aggregate_closure_audit
                else verification.get("facility_aggregate_closure_audit_ir_mismatch_count")
            ),
            "facility_aggregate_closure_audit_fn_mismatch_count": (
                facility_aggregate_closure_audit.get("fn_mismatch_count")
                if facility_aggregate_closure_audit
                else verification.get("facility_aggregate_closure_audit_fn_mismatch_count")
            ),
            "facility_aggregate_closure_audit_blocking_reason_count": (
                len(facility_aggregate_closure_audit.get("blocking_reasons", []))
                if facility_aggregate_closure_audit
                else verification.get("facility_aggregate_closure_audit_blocking_reason_count")
            ),
            "facility_component_contribution_audit_status": (
                facility_component_contribution_audit.get("status")
                if facility_component_contribution_audit
                else verification.get("facility_component_contribution_audit_status")
            ),
            "facility_component_contribution_audit_component_count": (
                facility_component_contribution_audit.get("component_count")
                if facility_component_contribution_audit
                else verification.get("facility_component_contribution_audit_component_count")
            ),
            "facility_component_contribution_audit_risk_atom_count": (
                facility_component_contribution_audit.get("risk_atom_count")
                if facility_component_contribution_audit
                else verification.get("facility_component_contribution_audit_risk_atom_count")
            ),
            "facility_component_contribution_audit_mismatch_count": (
                facility_component_contribution_audit.get("mismatch_count")
                if facility_component_contribution_audit
                else verification.get("facility_component_contribution_audit_mismatch_count")
            ),
            "facility_component_contribution_audit_blocking_reason_count": (
                len(facility_component_contribution_audit.get("blocking_reasons", []))
                if facility_component_contribution_audit
                else verification.get("facility_component_contribution_audit_blocking_reason_count")
            ),
            "facility_frequency_uncertainty_audit_status": (
                facility_frequency_uncertainty_audit.get("status")
                if facility_frequency_uncertainty_audit
                else verification.get("facility_frequency_uncertainty_audit_status")
            ),
            "facility_frequency_uncertainty_audit_scenario_count": (
                facility_frequency_uncertainty_audit.get("scenario_count")
                if facility_frequency_uncertainty_audit
                else verification.get("facility_frequency_uncertainty_audit_scenario_count")
            ),
            "facility_frequency_uncertainty_audit_risk_atom_count": (
                facility_frequency_uncertainty_audit.get("risk_atom_count")
                if facility_frequency_uncertainty_audit
                else verification.get("facility_frequency_uncertainty_audit_risk_atom_count")
            ),
            "facility_frequency_uncertainty_audit_mismatch_count": (
                facility_frequency_uncertainty_audit.get("mismatch_count")
                if facility_frequency_uncertainty_audit
                else verification.get("facility_frequency_uncertainty_audit_mismatch_count")
            ),
            "facility_frequency_uncertainty_audit_blocking_reason_count": (
                len(facility_frequency_uncertainty_audit.get("blocking_reasons", []))
                if facility_frequency_uncertainty_audit
                else verification.get("facility_frequency_uncertainty_audit_blocking_reason_count")
            ),
            "isolation_union_extension_status": (
                isolation_union_extension_verification.get("status")
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_status")
            ),
            "isolation_union_extension_merged_event_count": (
                isolation_union_extension_verification.get("merged_counts", {}).get("events")
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_merged_event_count")
            ),
            "isolation_union_extension_merged_case_count": (
                isolation_union_extension_verification.get("merged_counts", {}).get("cases")
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_merged_case_count")
            ),
            "isolation_union_extension_merged_risk_atom_count": (
                isolation_union_extension_verification.get("merged_counts", {}).get("risk_atoms")
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_merged_risk_atom_count")
            ),
            "isolation_union_extension_provider_response_consumed": (
                isolation_union_extension_verification.get("isolation_counts", {}).get(
                    "provider_response_consumed"
                )
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_provider_response_consumed")
            ),
            "isolation_union_extension_state_snapshot_bound_cases": (
                isolation_union_extension_verification.get("isolation_counts", {}).get(
                    "state_snapshot_bound_cases"
                )
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_state_snapshot_bound_cases")
            ),
            "isolation_union_extension_equipment_state_release_status": (
                isolation_union_extension_verification.get("equipment_state_release_status")
                if isolation_union_extension_verification
                else verification.get("isolation_union_extension_equipment_state_release_status")
            ),
            "isolation_union_extension_qualified_provider_packet_case_count": (
                isolation_union_extension_verification.get(
                    "qualified_provider_packet_case_count"
                )
                if isolation_union_extension_verification
                else verification.get(
                    "isolation_union_extension_qualified_provider_packet_case_count"
                )
            ),
        }
    )
    _save(output_dir / "validation_evidence_matrix.json", matrix)
    _save(output_dir / "ijhe_completion_audit.json", audit)
    _save(verification_path, verification)
    return {
        "status": audit["status"],
        "audit_check_count": len(audit["checks"]),
        "audit_pass_count": sum(row["status"] == "PASS" for row in audit["checks"]),
        "audit_blocked_count": sum(row["status"] == "BLOCKED" for row in audit["checks"]),
        "validation_matrix_status": matrix["status"],
        "validation_matrix_decision": matrix["decision"],
        "cache_hits": realtime.get("cache_hits") if realtime else None,
        "fresh_physics_meets_one_hz": realtime.get("fresh_physics_meets_one_hz") if realtime else None,
        "persistent_fresh_physics": realtime.get("persistent_fresh_physics") if realtime else None,
        "output": str(output_dir.resolve()),
        "source_audit_status": source_audit.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--union-dir", type=Path, required=True)
    parser.add_argument("--current-status", type=Path, required=True)
    parser.add_argument("--pool-record", type=Path, required=True)
    parser.add_argument("--equipment-audit", type=Path, required=True)
    parser.add_argument("--native-contract", type=Path, required=True)
    parser.add_argument("--external-sweep", type=Path, required=True)
    parser.add_argument("--ijhe-audit-source", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--diagnostic-adapter-registry", type=Path, required=True)
    parser.add_argument("--vertical-handoff-result", type=Path, required=True)
    parser.add_argument("--realtime-cache-benchmark", type=Path, required=True)
    parser.add_argument(
        "--native-full-bore-result",
        type=Path,
        default=None,
        help="Optional native finite full-bore diagnostic record; remains diagnostic-only.",
    )
    parser.add_argument(
        "--state-snapshot-binding-audit",
        type=Path,
        default=None,
        help="Optional canonical equipment-state handoff audit; remains diagnostic-only.",
    )
    parser.add_argument(
        "--native-state-snapshot-campaign-ledger",
        type=Path,
        default=None,
        help="Optional base native-campaign reconciliation of state and provider result digests.",
    )
    parser.add_argument(
        "--native-scope-packet-catalog-verification",
        type=Path,
        default=None,
        help="Optional exact native generic-scope packet catalog verification.",
    )
    parser.add_argument(
        "--native-model-contract-audit",
        type=Path,
        default=None,
        help="Optional native external-model contract audit.",
    )
    parser.add_argument(
        "--frequency-provenance-report",
        type=Path,
        default=None,
        help="Optional literature-frequency provenance report.",
    )
    parser.add_argument(
        "--diagnostic-worklist-evidence",
        type=Path,
        default=None,
        help="Optional diagnostic provider-worklist packet evidence.",
    )
    parser.add_argument(
        "--native-packet-campaign-ledger",
        type=Path,
        default=None,
        help="Optional native packet campaign ledger.",
    )
    parser.add_argument(
        "--native-binding-reconciliation",
        type=Path,
        default=None,
        help="Optional native model-binding reconciliation.",
    )
    parser.add_argument(
        "--domain-recovery-audit",
        type=Path,
        default=None,
        help="Optional domain-recovery sensitivity audit.",
    )
    parser.add_argument(
        "--observed-state-evidence",
        type=Path,
        default=None,
        help="Optional normalized observed equipment-state evidence ledger.",
    )
    parser.add_argument(
        "--observed-state-model-binding-audit",
        type=Path,
        default=None,
        help="Optional observed-state to facility-neutral normal-model binding audit.",
    )
    parser.add_argument(
        "--external-equipment-model-contract-audit",
        type=Path,
        default=None,
        help="Optional static audit of the external digital-twin accident-release contract.",
    )
    parser.add_argument(
        "--slabx-validation-evidence",
        type=Path,
        default=None,
        help="Optional restricted SLABx-LH2 consequence-component validation record.",
    )
    parser.add_argument(
        "--scope-ledger-consistency",
        type=Path,
        default=None,
        help="Optional current comparison of the merged scope matrix and facility ledger.",
    )
    parser.add_argument(
        "--risk-atom-chain-audit",
        type=Path,
        default=None,
        help="Optional case/atom-level release-to-final-damage chain audit.",
    )
    parser.add_argument(
        "--equipment-state-release-audit",
        type=Path,
        default=None,
        help="Optional case-level equipment-state to release-packet identity audit.",
    )
    parser.add_argument(
        "--facility-aggregate-closure-audit",
        type=Path,
        default=None,
        help="Optional independent facility IR/F-N aggregate closure audit.",
    )
    parser.add_argument(
        "--facility-component-contribution-audit",
        type=Path,
        default=None,
        help="Optional independent equipment contribution and ranking audit.",
    )
    parser.add_argument(
        "--facility-frequency-uncertainty-audit",
        type=Path,
        default=None,
        help="Optional independent literature-frequency sensitivity audit.",
    )
    parser.add_argument(
        "--isolation-union-extension-verification",
        type=Path,
        default=None,
        help="Optional namespaced isolation success/failure facility-extension verification.",
    )
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"native union evidence binding failed: {error}") from error
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
