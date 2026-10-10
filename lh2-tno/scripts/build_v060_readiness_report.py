#!/usr/bin/env python3
"""Build the versioned PRISM v0.6.0 IJHE readiness report."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.v060_readiness import (  # noqa: E402
    build_v060_readiness_report,
    validate_v060_readiness_report,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _source_artifact(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    try:
        display_path = resolved.relative_to(ROOT).as_posix()
    except ValueError:
        display_path = str(resolved)
    return {"path": display_path, "sha256": digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective-audit", type=Path, required=True)
    parser.add_argument("--union-verification", type=Path, required=True)
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--completion-audit", type=Path, required=True)
    parser.add_argument("--validation-matrix", type=Path, required=True)
    parser.add_argument("--realtime-benchmark", type=Path, required=True)
    parser.add_argument(
        "--facility-evidence-request",
        type=Path,
        help="Optional current provider-evidence request ledger.",
    )
    parser.add_argument(
        "--scenario-evidence-audit",
        type=Path,
        help="Optional read-only scenario register/screening evidence summary.",
    )
    parser.add_argument(
        "--risk-atom-chain-audit",
        type=Path,
        help="Optional case/atom-level release-to-final-damage chain audit.",
    )
    parser.add_argument(
        "--equipment-state-release-audit",
        type=Path,
        help="Optional case-level equipment-state to release-packet identity audit.",
    )
    parser.add_argument(
        "--facility-aggregate-closure-audit",
        type=Path,
        help="Optional independent facility IR/F-N aggregate closure audit.",
    )
    parser.add_argument(
        "--facility-component-contribution-audit",
        type=Path,
        help="Optional independent equipment contribution and ranking audit.",
    )
    parser.add_argument(
        "--facility-frequency-uncertainty-audit",
        type=Path,
        help="Optional independent literature-frequency sensitivity audit.",
    )
    parser.add_argument(
        "--external-equipment-model-audit",
        type=Path,
        help="Optional external equipment/P&ID readiness audit.",
    )
    parser.add_argument(
        "--equipment-scenario-coverage-audit",
        type=Path,
        help="Optional equipment-to-accident-family coverage audit.",
    )
    parser.add_argument(
        "--equipment-frequency-binding-audit",
        type=Path,
        help="Optional literature-frequency-to-equipment binding audit.",
    )
    parser.add_argument(
        "--generic-equipment-scenario-coverage-audit",
        type=Path,
        help="Optional facility-neutral generic-manifest scenario coverage audit.",
    )
    parser.add_argument(
        "--generic-equipment-frequency-binding-audit",
        type=Path,
        help="Optional facility-neutral generic-manifest frequency binding audit.",
    )
    parser.add_argument(
        "--generic-diagnostic-campaign-binding",
        type=Path,
        help="Optional facility-neutral diagnostic packet-to-campaign binding audit.",
    )
    parser.add_argument(
        "--generic-chain-closure-audit",
        type=Path,
        help="Optional facility-neutral release-to-final-damage and IR/F-N closure audit.",
    )
    parser.add_argument(
        "--generic-provider-closure-audit",
        type=Path,
        help="Optional generic LH2 provider release-boundary closure audit.",
    )
    parser.add_argument(
        "--isolation-union-extension-verification",
        type=Path,
        help="Optional namespaced isolation success/failure facility-extension verification.",
    )
    parser.add_argument(
        "--release-closure-worklist",
        type=Path,
        help="Optional case-level release termination/isolation/inventory closure worklist.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_v060_readiness_report(
            objective_audit=_load(args.objective_audit),
            union_verification=_load(args.union_verification),
            scope_matrix=_load(args.scope_matrix),
            facility_assessment=_load(args.facility_assessment),
            completion_audit=_load(args.completion_audit),
            validation_matrix=_load(args.validation_matrix),
            realtime_benchmark=_load(args.realtime_benchmark),
            facility_evidence_request=(
                _load(args.facility_evidence_request)
                if args.facility_evidence_request is not None
                else None
            ),
            scenario_evidence_audit=(
                _load(args.scenario_evidence_audit)
                if args.scenario_evidence_audit is not None
                else None
            ),
            risk_atom_chain_audit=(
                _load(args.risk_atom_chain_audit)
                if args.risk_atom_chain_audit is not None
                else None
            ),
            equipment_state_release_audit=(
                _load(args.equipment_state_release_audit)
                if args.equipment_state_release_audit is not None
                else None
            ),
            facility_aggregate_closure_audit=(
                _load(args.facility_aggregate_closure_audit)
                if args.facility_aggregate_closure_audit is not None
                else None
            ),
            facility_component_contribution_audit=(
                _load(args.facility_component_contribution_audit)
                if args.facility_component_contribution_audit is not None
                else None
            ),
            facility_frequency_uncertainty_audit=(
                _load(args.facility_frequency_uncertainty_audit)
                if args.facility_frequency_uncertainty_audit is not None
                else None
            ),
            external_equipment_model_audit=(
                _load(args.external_equipment_model_audit)
                if args.external_equipment_model_audit is not None
                else None
            ),
            equipment_scenario_coverage_audit=(
                _load(args.equipment_scenario_coverage_audit)
                if args.equipment_scenario_coverage_audit is not None
                else None
            ),
            equipment_frequency_binding_audit=(
                _load(args.equipment_frequency_binding_audit)
                if args.equipment_frequency_binding_audit is not None
                else None
            ),
            generic_equipment_scenario_coverage_audit=(
                _load(args.generic_equipment_scenario_coverage_audit)
                if args.generic_equipment_scenario_coverage_audit is not None
                else None
            ),
            generic_equipment_frequency_binding_audit=(
                _load(args.generic_equipment_frequency_binding_audit)
                if args.generic_equipment_frequency_binding_audit is not None
                else None
            ),
            generic_diagnostic_campaign_binding=(
                _load(args.generic_diagnostic_campaign_binding)
                if args.generic_diagnostic_campaign_binding is not None
                else None
            ),
            generic_chain_closure_audit=(
                _load(args.generic_chain_closure_audit)
                if args.generic_chain_closure_audit is not None
                else None
            ),
            generic_provider_closure_audit=(
                _load(args.generic_provider_closure_audit)
                if args.generic_provider_closure_audit is not None
                else None
            ),
            isolation_union_extension_verification=(
                _load(args.isolation_union_extension_verification)
                if args.isolation_union_extension_verification is not None
                else None
            ),
            release_closure_worklist=(
                _load(args.release_closure_worklist)
                if args.release_closure_worklist is not None
                else None
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"v0.6.0 readiness input error: {error}") from error
    report["source_artifacts"] = {
        "objective_audit": _source_artifact(args.objective_audit),
        "union_verification": _source_artifact(args.union_verification),
        "scope_matrix": _source_artifact(args.scope_matrix),
        "facility_assessment": _source_artifact(args.facility_assessment),
        "completion_audit": _source_artifact(args.completion_audit),
        "validation_matrix": _source_artifact(args.validation_matrix),
        "realtime_benchmark": _source_artifact(args.realtime_benchmark),
    }
    if args.facility_evidence_request is not None:
        report["source_artifacts"]["facility_evidence_request"] = _source_artifact(
            args.facility_evidence_request
        )
    if args.scenario_evidence_audit is not None:
        report["source_artifacts"]["scenario_evidence_audit"] = _source_artifact(
            args.scenario_evidence_audit
        )
    if args.risk_atom_chain_audit is not None:
        report["source_artifacts"]["risk_atom_chain_audit"] = _source_artifact(
            args.risk_atom_chain_audit
        )
    if args.equipment_state_release_audit is not None:
        report["source_artifacts"]["equipment_state_release_audit"] = _source_artifact(
            args.equipment_state_release_audit
        )
    if args.facility_aggregate_closure_audit is not None:
        report["source_artifacts"]["facility_aggregate_closure_audit"] = _source_artifact(
            args.facility_aggregate_closure_audit
        )
    if args.facility_component_contribution_audit is not None:
        report["source_artifacts"]["facility_component_contribution_audit"] = _source_artifact(
            args.facility_component_contribution_audit
        )
    if args.facility_frequency_uncertainty_audit is not None:
        report["source_artifacts"]["facility_frequency_uncertainty_audit"] = _source_artifact(
            args.facility_frequency_uncertainty_audit
        )
    if args.external_equipment_model_audit is not None:
        report["source_artifacts"]["external_equipment_model_audit"] = _source_artifact(
            args.external_equipment_model_audit
        )
    if args.equipment_scenario_coverage_audit is not None:
        report["source_artifacts"]["equipment_scenario_coverage_audit"] = _source_artifact(
            args.equipment_scenario_coverage_audit
        )
    if args.equipment_frequency_binding_audit is not None:
        report["source_artifacts"]["equipment_frequency_binding_audit"] = _source_artifact(
            args.equipment_frequency_binding_audit
        )
    if args.generic_equipment_scenario_coverage_audit is not None:
        report["source_artifacts"]["generic_equipment_scenario_coverage_audit"] = _source_artifact(
            args.generic_equipment_scenario_coverage_audit
        )
    if args.generic_equipment_frequency_binding_audit is not None:
        report["source_artifacts"]["generic_equipment_frequency_binding_audit"] = _source_artifact(
            args.generic_equipment_frequency_binding_audit
        )
    if args.generic_diagnostic_campaign_binding is not None:
        report["source_artifacts"]["generic_diagnostic_campaign_binding"] = _source_artifact(
            args.generic_diagnostic_campaign_binding
        )
    if args.generic_chain_closure_audit is not None:
        report["source_artifacts"]["generic_chain_closure_audit"] = _source_artifact(
            args.generic_chain_closure_audit
        )
    if args.generic_provider_closure_audit is not None:
        report["source_artifacts"]["generic_provider_closure_audit"] = _source_artifact(
            args.generic_provider_closure_audit
        )
    if args.isolation_union_extension_verification is not None:
        report["source_artifacts"]["isolation_union_extension_verification"] = _source_artifact(
            args.isolation_union_extension_verification
        )
    if args.release_closure_worklist is not None:
        report["source_artifacts"]["release_closure_worklist"] = _source_artifact(
            args.release_closure_worklist
        )
    try:
        validation = validate_v060_readiness_report(report)
    except ValueError as error:
        raise SystemExit(f"v0.6.0 readiness invariant error: {error}") from error
    report["invariant_validation"] = validation
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["objective_status"],
        "conditional_chain_complete": report["conditional_chain_complete"],
        "event_count": report["chain"]["event_count"],
        "case_count": report["chain"]["case_count"],
        "risk_atom_count": report["chain"]["risk_atom_count"],
        "strict_blocking_check_ids": report["strict_blocking_check_ids"],
        "validation": validation,
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
