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
