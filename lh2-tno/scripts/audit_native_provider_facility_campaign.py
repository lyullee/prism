"""Independently audit a native multi-equipment facility campaign.

The audit consumes the saved facility ledger inside ``facility_assessment``.
It recomputes equipment contributions from risk atoms and literature-frequency
sensitivity from the same saved atoms.  It accepts a partial campaign only
when withheld opening bins remain explicit; it never turns a partial ledger
into a facility-QRA claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.facility_component_contribution_audit import (  # noqa: E402
    build_facility_component_contribution_audit,
)
from lh2_tno.facility_frequency_uncertainty_audit import (  # noqa: E402
    build_facility_frequency_uncertainty_audit,
)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run(campaign_result_path: Path, facility_assessment_path: Path) -> dict[str, Any]:
    campaign_result = _object(campaign_result_path)
    assessment = _object(facility_assessment_path)
    ledger = assessment.get("facility_risk_ledger")
    if not isinstance(ledger, dict):
        raise ValueError("facility_assessment.facility_risk_ledger is required")
    uncertainty = assessment.get("frequency_uncertainty")
    if not isinstance(uncertainty, dict):
        raise ValueError("facility_assessment.frequency_uncertainty is required")
    rows = uncertainty.get("scenarios")
    if not isinstance(rows, list) or not rows:
        raise ValueError("facility_assessment.frequency_uncertainty.scenarios is required")
    scenario_source = {
        "scenarios": [row.get("scenario") for row in rows if isinstance(row, dict)],
        "frequency_inference_performed": False,
        "facility_credible_interval": uncertainty.get("facility_credible_interval") is True,
    }
    if len(scenario_source["scenarios"]) != len(rows):
        raise ValueError("every frequency uncertainty row must contain a scenario")
    component_audit = build_facility_component_contribution_audit(ledger)
    frequency_audit = build_facility_frequency_uncertainty_audit(
        ledger,
        scenario_source,
        uncertainty,
    )
    blocking_reasons = [
        *component_audit.get("blocking_reasons", []),
        *frequency_audit.get("blocking_reasons", []),
    ]
    status = (
        "NATIVE_PROVIDER_MULTI_EQUIPMENT_AUDIT_CLOSED_DIAGNOSTIC"
        if not blocking_reasons
        else "BLOCKED_NATIVE_PROVIDER_MULTI_EQUIPMENT_AUDIT"
    )
    return {
        "schema_version": "prism.native_provider_multi_equipment_facility_audit.v1",
        "status": status,
        "facility_id": ledger.get("facility_id"),
        "campaign_result_path": str(campaign_result_path),
        "facility_assessment_path": str(facility_assessment_path),
        "campaign_result_status": campaign_result.get("status"),
        "ledger_status": ledger.get("status"),
        "component_contribution_audit": component_audit,
        "frequency_uncertainty_audit": frequency_audit,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "diagnostic_only": True,
        "frequency_inference_performed": False,
        "facility_credible_interval": False,
        "physical_validation_claim": False,
        "qualified_provider_packet": False,
        "facility_qra_claim": False,
        "interpretation": (
            "The saved partial facility ledger independently reproduces equipment contributions "
            "and literature-frequency sensitivity. Withheld bins remain explicit and no facility "
            "QRA or physical-validation claim is promoted."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.campaign_result, args.facility_assessment)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"native provider facility audit failed: {error}") from error
    _save(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "component_audit_status": result["component_contribution_audit"]["status"],
        "frequency_audit_status": result["frequency_uncertainty_audit"]["status"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
