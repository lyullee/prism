"""Rebuild a facility assessment with the native qualification audit gate.

This command reuses the saved facility risk ledger and frequency scenarios. It
does not rerun equipment physics or alter risk atoms; it makes the provider
qualification audit an explicit assessment gate and keeps QRA fail-closed.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def reconcile_assessment(
    assessment: dict[str, Any],
    audit: dict[str, Any],
    *,
    assessment_record: str,
    audit_record: str,
) -> dict[str, Any]:
    if assessment.get("schema_version") != "prism.facility_assessment.v1":
        raise ValueError("assessment must use prism.facility_assessment.v1")
    if audit.get("schema_version") != "prism.native_full_scope_provider_qualification_audit.v1":
        raise ValueError("audit must use the native provider qualification audit schema")
    ledger = assessment.get("facility_risk_ledger")
    if not isinstance(ledger, dict):
        raise ValueError("assessment lacks facility_risk_ledger")
    coverage = copy.deepcopy(audit)
    scenarios: list[LiteratureFrequencyScenario] = []
    uncertainty = assessment.get("frequency_uncertainty")
    if isinstance(uncertainty, dict):
        for row in uncertainty.get("scenarios", ()):
            if isinstance(row, dict) and isinstance(row.get("scenario"), dict):
                scenarios.append(LiteratureFrequencyScenario.model_validate(row["scenario"]))
    result = build_facility_assessment(
        [ledger],
        provider_qualification_coverage=coverage,
        frequency_scenarios=tuple(scenarios),
    )
    result["source_assessment_record"] = assessment_record
    result["provider_qualification_audit_record"] = audit_record
    result["provider_qualification_audit_status"] = audit.get("status")
    result["provider_qualification_audit_release_identity_count"] = audit.get(
        "release_identity_request_count"
    )
    result["provider_qualification_audit_exact_match_count"] = audit.get("exact_match_count")
    result["provider_qualification_audit_qualified_provider_packet_count"] = audit.get(
        "qualified_provider_packet_count"
    )
    result["provider_qualification_audit_facility_qra_allowed"] = False
    result["facility_qra_claim"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = reconcile_assessment(
        _object(args.assessment),
        _object(args.audit),
        assessment_record=str(args.assessment),
        audit_record=str(args.audit),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = result["provider_qualification_coverage"]
    print(json.dumps({
        "status": result["status"],
        "provider_qualification_coverage_complete": gate["complete"],
        "qualified_provider_packet_count": gate["qualified_provider_packet_count"],
        "facility_qra_allowed": result["provider_qualification_audit_facility_qra_allowed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if result["status"] == "FACILITY_SCOPE_EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
