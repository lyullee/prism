"""Build one auditable PRISM facility assessment from campaign results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.facility_ledger import FacilityLedgerError  # noqa: E402
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _scenarios(path: Path | None) -> tuple[LiteratureFrequencyScenario, ...]:
    if path is None:
        return ()
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("scenarios") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a scenario array or {{\"scenarios\": [...]}}")
    return tuple(LiteratureFrequencyScenario.model_validate(row) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a fail-closed facility assessment from evaluated PRISM campaigns."
    )
    parser.add_argument("--campaign-result", type=Path, action="append", required=True)
    parser.add_argument("--expected-component-id", action="append", default=[])
    parser.add_argument("--scope-matrix", type=Path, action="append", default=[])
    parser.add_argument("--required-accident-family", action="append", default=[])
    parser.add_argument("--scenarios", type=Path)
    parser.add_argument(
        "--provider-qualification-coverage",
        type=Path,
        help="optional provider_catalog_coverage report to reconcile qualified packets",
    )
    parser.add_argument(
        "--facility-case-packet-coverage",
        type=Path,
        help="optional exact facility-case coverage audit against qualified provider packets",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        results = [_object(path) for path in args.campaign_result]
        matrices = [_object(path) for path in args.scope_matrix]
        provider_qualification_coverage = (
            _object(args.provider_qualification_coverage)
            if args.provider_qualification_coverage
            else None
        )
        facility_case_packet_coverage = (
            _object(args.facility_case_packet_coverage)
            if args.facility_case_packet_coverage
            else None
        )
        assessment = build_facility_assessment(
            results,
            expected_component_ids=tuple(args.expected_component_id),
            scope_matrices=matrices,
            required_accident_families=tuple(args.required_accident_family),
            frequency_scenarios=_scenarios(args.scenarios),
            provider_qualification_coverage=provider_qualification_coverage,
            facility_case_packet_coverage=facility_case_packet_coverage,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, FacilityLedgerError) as error:
        raise SystemExit(f"facility assessment input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(assessment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    uncertainty = assessment["frequency_uncertainty"]
    coverage = assessment["conditional_diagnostic_facility_coverage"]
    print(json.dumps({
        "status": assessment["status"],
        "output": str(args.output),
        "facility_total_risk_available": assessment["facility_total_risk_available"],
        "conditional_diagnostic_facility_risk_available": assessment[
            "conditional_diagnostic_facility_risk_available"
        ],
        "conditional_diagnostic_operator_limited_case_count": coverage.get(
            "operator_limited_case_count", 0
        ),
        "conditional_diagnostic_case_count": coverage.get(
            "conditional_case_count", coverage.get("case_count", 0)
        ),
        "conditional_diagnostic_uncomputed_case_count": coverage.get(
            "conditional_uncomputed_case_count", coverage.get("uncomputed_case_count", 0)
        ),
        "strict_uncomputed_case_count": coverage.get(
            "strict_uncomputed_case_count", coverage.get("uncomputed_case_count", 0)
        ),
        "campaign_count": len(assessment["facility_risk_ledger"]["campaign_ids"]),
        "component_contribution_count": len(assessment["facility_risk_ledger"]["component_contributions"]),
        "scope_matrix_count": len(assessment["facility_risk_ledger"]["scope_matrix_digests"]),
        "frequency_scenario_count": len(uncertainty["scenarios"]) if uncertainty else 0,
        "fresh_physics_executed": assessment["fresh_physics_executed"],
        "source_campaign_physics": assessment["source_campaign_physics"],
        "provider_qualification_coverage_complete": (
            assessment["provider_qualification_coverage"]["complete"]
            if assessment["provider_qualification_coverage"] is not None
            else None
        ),
        "facility_case_packet_coverage_complete": (
            assessment["facility_case_packet_coverage"]["complete"]
            if assessment["facility_case_packet_coverage"] is not None
            else None
        ),
    }, ensure_ascii=False))
    return 0 if assessment["status"] == "FACILITY_SCOPE_EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
