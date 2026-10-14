"""Build a fail-closed IJHE readiness audit from saved PRISM ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.completion_audit import build_ijhe_completion_audit  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit evidence required for an IJHE PRISM scope claim.")
    parser.add_argument("--current-status", type=Path, required=True)
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--uncertainty-result", type=Path)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument("--diagnostic-adapter-registry", type=Path)
    parser.add_argument("--diagnostic-adapter-execution", type=Path)
    parser.add_argument("--diagnostic-worklist-evidence", type=Path)
    parser.add_argument("--diagnostic-campaign-binding", type=Path)
    parser.add_argument("--facility-assessment", type=Path)
    parser.add_argument("--vertical-handoff-result", type=Path)
    parser.add_argument("--native-model-contract-audit", type=Path)
    parser.add_argument("--frequency-provenance-report", type=Path)
    parser.add_argument("--scenario-evidence-report", type=Path)
    parser.add_argument("--native-full-bore-result", type=Path)
    parser.add_argument("--native-full-bore-frequency-result", type=Path)
    parser.add_argument("--native-packet-coverage-ledger", type=Path)
    parser.add_argument("--native-packet-campaign-ledger", type=Path)
    parser.add_argument(
        "--provider-qualification-coverage",
        type=Path,
        help="optional provider_catalog_coverage report with qualification sidecars",
    )
    parser.add_argument(
        "--validation-evidence-matrix",
        type=Path,
        help="optional fail-closed component/observation/facility evidence matrix",
    )
    parser.add_argument(
        "--scope-ledger-consistency",
        type=Path,
        help="optional comparison of the declared scope matrix and merged facility ledger",
    )
    parser.add_argument(
        "--native-binding-reconciliation",
        type=Path,
        help="optional reconciliation of the native source audit and model-binding catalog",
    )
    parser.add_argument(
        "--facility-case-packet-coverage",
        type=Path,
        help="optional exact facility-case coverage audit against qualified provider packets",
    )
    parser.add_argument(
        "--combined-chain-closure",
        type=Path,
        help="optional combined packet/vertical diagnostic chain-closure audit",
    )
    parser.add_argument(
        "--slabx-validation-evidence",
        type=Path,
        help="optional digest-bound SLABx-LH2 consequence validation evidence",
    )
    parser.add_argument(
        "--realtime-cache-benchmark",
        type=Path,
        help="optional exact-cache versus fresh-physics realtime benchmark",
    )
    parser.add_argument(
        "--domain-recovery-audit",
        type=Path,
        help="optional baseline versus larger-domain sensitivity comparison",
    )
    parser.add_argument(
        "--native-scope-packet-catalog-verification",
        type=Path,
        help="optional exact native generic-scope catalog verification",
    )
    parser.add_argument(
        "--state-snapshot-binding-audit",
        type=Path,
        help="optional state-snapshot/provider-echo binding audit",
    )
    parser.add_argument(
        "--observed-state-evidence",
        type=Path,
        help="optional normalized observed equipment-state evidence ledger",
    )
    parser.add_argument(
        "--observed-state-model-binding-audit",
        type=Path,
        help="optional observed-state to facility-neutral normal-model binding audit",
    )
    parser.add_argument(
        "--external-equipment-model-contract-audit",
        type=Path,
        help="optional static audit of the external digital-twin accident-release contract",
    )
    parser.add_argument(
        "--facility-aggregate-closure-audit",
        type=Path,
        help="optional independent facility IR/F-N aggregate closure audit",
    )
    parser.add_argument(
        "--risk-atom-chain-audit",
        type=Path,
        help="optional case/atom-level release-to-final-damage chain audit",
    )
    parser.add_argument(
        "--equipment-state-release-audit",
        type=Path,
        help="optional equipment-state to release-packet identity audit",
    )
    parser.add_argument(
        "--facility-component-contribution-audit",
        type=Path,
        help="optional independent equipment contribution and ranking audit",
    )
    parser.add_argument(
        "--facility-frequency-uncertainty-audit",
        type=Path,
        help="optional independent literature-frequency sensitivity audit",
    )
    parser.add_argument(
        "--isolation-union-extension-verification",
        type=Path,
        help="optional namespaced isolation success/failure facility-extension verification",
    )
    parser.add_argument(
        "--hazop-forecast-scan",
        type=Path,
        help="optional predicted-state HAZOP trigger scan",
    )
    parser.add_argument(
        "--hazop-integrated-risk",
        type=Path,
        help="optional current/forecast integrated HAZOP risk ledger",
    )
    parser.add_argument(
        "--hazop-multiequipment-diagnostic",
        type=Path,
        help="optional multi-equipment HAZOP/provider/SLABx-LH2 diagnostic ledger",
    )
    parser.add_argument(
        "--hazop-scope-worklist",
        type=Path,
        help="optional HAZOP family/component to provider-event scope worklist",
    )
    parser.add_argument(
        "--hazop-event-mode-binding",
        type=Path,
        help="optional explicit HAZOP operating-mode/scenario binding audit",
    )
    parser.add_argument(
        "--hazop-operating-mode-evidence",
        type=Path,
        help="optional inspection-center qualitative HAZOP operating-mode evidence audit",
    )
    parser.add_argument(
        "--reviewed-signal-unit-evidence",
        type=Path,
        help="optional document-anchored reviewed signal-unit evidence audit",
    )
    parser.add_argument(
        "--realtime-hazop-mode-trace",
        type=Path,
        help="optional audit of HAZOP operating_mode at the realtime result boundary",
    )
    parser.add_argument(
        "--external-document-evidence",
        type=Path,
        help="optional provenance-only audit of external equipment documents",
    )
    parser.add_argument(
        "--external-release-artifact-intake",
        type=Path,
        help="optional provenance-only inventory of external release-shaped JSON artifacts",
    )
    parser.add_argument(
        "--external-model-root-review",
        type=Path,
        help="optional provenance-only review of the external LH2 digital-twin model root",
    )
    parser.add_argument(
        "--facility-evidence-request",
        type=Path,
        help="optional exact facility-case evidence-request coverage audit",
    )
    parser.add_argument(
        "--hazop-scenario-trace-audit",
        type=Path,
        help="optional fail-closed HAZOP scenario identity trace audit",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = _object(args.current_status)
        matrix = _object(args.scope_matrix)
        campaign = _object(args.campaign_result)
        uncertainty = _object(args.uncertainty_result) if args.uncertainty_result else None
        worklist = _object(args.provider_worklist) if args.provider_worklist else None
        registry = _object(args.diagnostic_adapter_registry) if args.diagnostic_adapter_registry else None
        diagnostic_execution = (
            _object(args.diagnostic_adapter_execution)
            if args.diagnostic_adapter_execution
            else None
        )
        if diagnostic_execution is not None:
            diagnostic_execution["_record_path"] = str(args.diagnostic_adapter_execution)
        worklist_evidence = (
            _object(args.diagnostic_worklist_evidence)
            if args.diagnostic_worklist_evidence
            else None
        )
        if worklist_evidence is not None:
            worklist_evidence["_record_path"] = str(args.diagnostic_worklist_evidence)
        campaign_binding = (
            _object(args.diagnostic_campaign_binding)
            if args.diagnostic_campaign_binding
            else None
        )
        if campaign_binding is not None:
            campaign_binding["_record_path"] = str(args.diagnostic_campaign_binding)
        facility_assessment = (
            _object(args.facility_assessment)
            if args.facility_assessment
            else None
        )
        if facility_assessment is not None:
            facility_assessment["_record_path"] = str(args.facility_assessment)
        vertical_handoff_result = (
            _object(args.vertical_handoff_result)
            if args.vertical_handoff_result
            else None
        )
        if vertical_handoff_result is not None:
            vertical_handoff_result["_record_path"] = str(args.vertical_handoff_result)
        native_model_contract_audit = (
            _object(args.native_model_contract_audit)
            if args.native_model_contract_audit
            else None
        )
        if native_model_contract_audit is not None:
            native_model_contract_audit["_record_path"] = str(args.native_model_contract_audit)
        frequency_provenance_report = (
            _object(args.frequency_provenance_report)
            if args.frequency_provenance_report
            else None
        )
        if frequency_provenance_report is not None:
            frequency_provenance_report["_record_path"] = str(args.frequency_provenance_report)
        scenario_evidence_report = (
            _object(args.scenario_evidence_report)
            if args.scenario_evidence_report
            else None
        )
        if scenario_evidence_report is not None:
            scenario_evidence_report["_record_path"] = str(args.scenario_evidence_report)
        native_full_bore_result = (
            _object(args.native_full_bore_result)
            if args.native_full_bore_result
            else None
        )
        if native_full_bore_result is not None:
            native_full_bore_result["_record_path"] = str(args.native_full_bore_result)
        native_full_bore_frequency_result = (
            _object(args.native_full_bore_frequency_result)
            if args.native_full_bore_frequency_result
            else None
        )
        if native_full_bore_frequency_result is not None:
            native_full_bore_frequency_result["_record_path"] = str(args.native_full_bore_frequency_result)
        native_packet_coverage_ledger = (
            _object(args.native_packet_coverage_ledger)
            if args.native_packet_coverage_ledger
            else None
        )
        if native_packet_coverage_ledger is not None:
            native_packet_coverage_ledger["_record_path"] = str(args.native_packet_coverage_ledger)
        native_packet_campaign_ledger = (
            _object(args.native_packet_campaign_ledger)
            if args.native_packet_campaign_ledger
            else None
        )
        if native_packet_campaign_ledger is not None:
            native_packet_campaign_ledger["_record_path"] = str(args.native_packet_campaign_ledger)
        provider_qualification_coverage = (
            _object(args.provider_qualification_coverage)
            if args.provider_qualification_coverage
            else None
        )
        if provider_qualification_coverage is not None:
            provider_qualification_coverage["_record_path"] = str(
                args.provider_qualification_coverage
            )
        validation_evidence_matrix = (
            _object(args.validation_evidence_matrix)
            if args.validation_evidence_matrix
            else None
        )
        if validation_evidence_matrix is not None:
            validation_evidence_matrix["_record_path"] = str(args.validation_evidence_matrix)
        scope_ledger_consistency = (
            _object(args.scope_ledger_consistency)
            if args.scope_ledger_consistency
            else None
        )
        if scope_ledger_consistency is not None:
            scope_ledger_consistency["_record_path"] = str(args.scope_ledger_consistency)
        native_binding_reconciliation = (
            _object(args.native_binding_reconciliation)
            if args.native_binding_reconciliation
            else None
        )
        if native_binding_reconciliation is not None:
            native_binding_reconciliation["_record_path"] = str(args.native_binding_reconciliation)
        facility_case_packet_coverage = (
            _object(args.facility_case_packet_coverage)
            if args.facility_case_packet_coverage
            else None
        )
        if facility_case_packet_coverage is not None:
            facility_case_packet_coverage["_record_path"] = str(args.facility_case_packet_coverage)
        combined_chain_closure = (
            _object(args.combined_chain_closure)
            if args.combined_chain_closure
            else None
        )
        if combined_chain_closure is not None:
            combined_chain_closure["_record_path"] = str(args.combined_chain_closure)
        slabx_validation_evidence = (
            _object(args.slabx_validation_evidence)
            if args.slabx_validation_evidence
            else None
        )
        if slabx_validation_evidence is not None:
            slabx_validation_evidence["_record_path"] = str(args.slabx_validation_evidence)
        realtime_cache_benchmark = (
            _object(args.realtime_cache_benchmark)
            if args.realtime_cache_benchmark
            else None
        )
        if realtime_cache_benchmark is not None:
            realtime_cache_benchmark["_record_path"] = str(args.realtime_cache_benchmark)
        domain_recovery_audit = (
            _object(args.domain_recovery_audit)
            if args.domain_recovery_audit
            else None
        )
        if domain_recovery_audit is not None:
            domain_recovery_audit["_record_path"] = str(args.domain_recovery_audit)
        native_scope_packet_catalog_verification = (
            _object(args.native_scope_packet_catalog_verification)
            if args.native_scope_packet_catalog_verification
            else None
        )
        if native_scope_packet_catalog_verification is not None:
            native_scope_packet_catalog_verification["_record_path"] = str(
                args.native_scope_packet_catalog_verification
            )
        state_snapshot_binding_audit = (
            _object(args.state_snapshot_binding_audit)
            if args.state_snapshot_binding_audit
            else None
        )
        if state_snapshot_binding_audit is not None:
            state_snapshot_binding_audit["_record_path"] = str(
                args.state_snapshot_binding_audit
            )
        observed_state_evidence = (
            _object(args.observed_state_evidence)
            if args.observed_state_evidence
            else None
        )
        if observed_state_evidence is not None:
            observed_state_evidence["_record_path"] = str(args.observed_state_evidence)
        observed_state_model_binding_audit = (
            _object(args.observed_state_model_binding_audit)
            if args.observed_state_model_binding_audit
            else None
        )
        if observed_state_model_binding_audit is not None:
            observed_state_model_binding_audit["_record_path"] = str(
                args.observed_state_model_binding_audit
            )
        external_equipment_model_contract_audit = (
            _object(args.external_equipment_model_contract_audit)
            if args.external_equipment_model_contract_audit
            else None
        )
        if external_equipment_model_contract_audit is not None:
            external_equipment_model_contract_audit["_record_path"] = str(
                args.external_equipment_model_contract_audit
            )
        facility_aggregate_closure_audit = (
            _object(args.facility_aggregate_closure_audit)
            if args.facility_aggregate_closure_audit
            else None
        )
        if facility_aggregate_closure_audit is not None:
            facility_aggregate_closure_audit["_record_path"] = str(
                args.facility_aggregate_closure_audit
            )
        facility_component_contribution_audit = (
            _object(args.facility_component_contribution_audit)
            if args.facility_component_contribution_audit
            else None
        )
        if facility_component_contribution_audit is not None:
            facility_component_contribution_audit["_record_path"] = str(
                args.facility_component_contribution_audit
            )
        risk_atom_chain_audit = (
            _object(args.risk_atom_chain_audit) if args.risk_atom_chain_audit else None
        )
        if risk_atom_chain_audit is not None:
            risk_atom_chain_audit["_record_path"] = str(args.risk_atom_chain_audit)
        equipment_state_release_audit = (
            _object(args.equipment_state_release_audit)
            if args.equipment_state_release_audit
            else None
        )
        if equipment_state_release_audit is not None:
            equipment_state_release_audit["_record_path"] = str(
                args.equipment_state_release_audit
            )
        facility_frequency_uncertainty_audit = (
            _object(args.facility_frequency_uncertainty_audit)
            if args.facility_frequency_uncertainty_audit
            else None
        )
        if facility_frequency_uncertainty_audit is not None:
            facility_frequency_uncertainty_audit["_record_path"] = str(
                args.facility_frequency_uncertainty_audit
            )
        isolation_union_extension_verification = (
            _object(args.isolation_union_extension_verification)
            if args.isolation_union_extension_verification
            else None
        )
        if isolation_union_extension_verification is not None:
            isolation_union_extension_verification["_record_path"] = str(
                args.isolation_union_extension_verification
            )
        hazop_forecast_scan = (
            _object(args.hazop_forecast_scan)
            if args.hazop_forecast_scan
            else None
        )
        if hazop_forecast_scan is not None:
            hazop_forecast_scan["_record_path"] = str(args.hazop_forecast_scan)
        hazop_integrated_risk = (
            _object(args.hazop_integrated_risk)
            if args.hazop_integrated_risk
            else None
        )
        if hazop_integrated_risk is not None:
            hazop_integrated_risk["_record_path"] = str(args.hazop_integrated_risk)
        hazop_multiequipment_diagnostic = (
            _object(args.hazop_multiequipment_diagnostic)
            if args.hazop_multiequipment_diagnostic
            else None
        )
        if hazop_multiequipment_diagnostic is not None:
            hazop_multiequipment_diagnostic["_record_path"] = str(
                args.hazop_multiequipment_diagnostic
            )
        hazop_scope_worklist = (
            _object(args.hazop_scope_worklist)
            if args.hazop_scope_worklist
            else None
        )
        if hazop_scope_worklist is not None:
            hazop_scope_worklist["_record_path"] = str(args.hazop_scope_worklist)
        hazop_event_mode_binding = (
            _object(args.hazop_event_mode_binding)
            if args.hazop_event_mode_binding
            else None
        )
        if hazop_event_mode_binding is not None:
            hazop_event_mode_binding["_record_path"] = str(args.hazop_event_mode_binding)
        hazop_operating_mode_evidence = (
            _object(args.hazop_operating_mode_evidence)
            if args.hazop_operating_mode_evidence
            else None
        )
        if hazop_operating_mode_evidence is not None:
            hazop_operating_mode_evidence["_record_path"] = str(args.hazop_operating_mode_evidence)
        reviewed_signal_unit_evidence = (
            _object(args.reviewed_signal_unit_evidence)
            if args.reviewed_signal_unit_evidence
            else None
        )
        if reviewed_signal_unit_evidence is not None:
            reviewed_signal_unit_evidence["_record_path"] = str(args.reviewed_signal_unit_evidence)
        realtime_hazop_mode_trace = (
            _object(args.realtime_hazop_mode_trace)
            if args.realtime_hazop_mode_trace
            else None
        )
        if realtime_hazop_mode_trace is not None:
            realtime_hazop_mode_trace["_record_path"] = str(args.realtime_hazop_mode_trace)
        external_document_evidence = (
            _object(args.external_document_evidence)
            if args.external_document_evidence
            else None
        )
        if external_document_evidence is not None:
            external_document_evidence["_record_path"] = str(args.external_document_evidence)
        external_release_artifact_intake = (
            _object(args.external_release_artifact_intake)
            if args.external_release_artifact_intake
            else None
        )
        if external_release_artifact_intake is not None:
            external_release_artifact_intake["_record_path"] = str(
                args.external_release_artifact_intake
            )
        external_model_root_review = (
            _object(args.external_model_root_review)
            if args.external_model_root_review
            else None
        )
        if external_model_root_review is not None:
            external_model_root_review["_record_path"] = str(args.external_model_root_review)
        facility_evidence_request = (
            _object(args.facility_evidence_request)
            if args.facility_evidence_request
            else None
        )
        if facility_evidence_request is not None:
            facility_evidence_request["_record_path"] = str(args.facility_evidence_request)
        hazop_scenario_trace_audit = (
            _object(args.hazop_scenario_trace_audit)
            if args.hazop_scenario_trace_audit
            else None
        )
        if hazop_scenario_trace_audit is not None:
            hazop_scenario_trace_audit["_record_path"] = str(args.hazop_scenario_trace_audit)
        report = build_ijhe_completion_audit(
            status,
            matrix,
            campaign,
            uncertainty,
            worklist,
            registry,
            diagnostic_execution,
            worklist_evidence,
            campaign_binding,
            facility_assessment,
            vertical_handoff_result,
            native_model_contract_audit,
            frequency_provenance_report,
            scenario_evidence_report,
            native_full_bore_result,
            native_full_bore_frequency_result,
            native_packet_coverage_ledger,
            native_packet_campaign_ledger,
            provider_qualification_coverage,
            validation_evidence_matrix,
            scope_ledger_consistency,
            native_binding_reconciliation,
            facility_case_packet_coverage,
            combined_chain_closure,
            risk_atom_chain_audit,
            equipment_state_release_audit,
            slabx_validation_evidence,
            realtime_cache_benchmark,
            domain_recovery_audit,
            state_snapshot_binding_audit,
            native_scope_packet_catalog_verification,
            observed_state_evidence,
            facility_aggregate_closure_audit,
            facility_component_contribution_audit,
            facility_frequency_uncertainty_audit,
            isolation_union_extension_verification,
            observed_state_model_binding_audit,
            external_equipment_model_contract_audit,
            hazop_forecast_scan=hazop_forecast_scan,
            hazop_integrated_risk=hazop_integrated_risk,
            realtime_hazop_mode_trace=realtime_hazop_mode_trace,
            external_document_evidence=external_document_evidence,
            external_release_artifact_intake=external_release_artifact_intake,
            external_model_root_review=external_model_root_review,
            hazop_multiequipment_diagnostic=hazop_multiequipment_diagnostic,
            hazop_scope_worklist=hazop_scope_worklist,
            hazop_event_mode_binding=hazop_event_mode_binding,
            hazop_operating_mode_evidence=hazop_operating_mode_evidence,
            reviewed_signal_unit_evidence=reviewed_signal_unit_evidence,
            facility_evidence_request=facility_evidence_request,
            hazop_scenario_trace_audit=hazop_scenario_trace_audit,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"IJHE completion audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "check_count": len(report["checks"]),
        "blocking_reason_count": len(report["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if report["status"] == "READY_FOR_IJHE_SCOPE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
