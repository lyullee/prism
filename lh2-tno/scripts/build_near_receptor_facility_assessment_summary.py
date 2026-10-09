"""Build a compact F/N proof from one near-receptor campaign result.

The input is an already executed campaign result.  This script does not run
SLABx-LH2 or a consequence model; it only passes the saved risk atoms through
the same facility ledger used by the generic facility assessment and records
the resulting nonzero diagnostic IR/F/N.  It is intended for the synthetic
near-receptor wiring check, not for facility-total promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize a saved near-receptor campaign as a diagnostic facility F/N proof."
    )
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--expected-component-id", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = args.campaign_result.read_bytes()
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise SystemExit("campaign result must contain one JSON object")
    assessment = build_facility_assessment(
        [result], expected_component_ids=tuple(args.expected_component_id)
    )
    ledger = assessment["facility_risk_ledger"]
    coverage = assessment["conditional_diagnostic_facility_coverage"]
    summary = {
        "schema_version": "prism.near_receptor_facility_assessment_summary.v1",
        "source_campaign_result": args.campaign_result.as_posix(),
        "source_campaign_result_sha256": hashlib.sha256(raw).hexdigest(),
        "assessment_digest": assessment["assessment_digest"],
        "facility_id": assessment["facility_id"],
        "status": assessment["status"],
        "conditional_diagnostic_facility_risk_available": assessment[
            "conditional_diagnostic_facility_risk_available"
        ],
        "conditional_diagnostic_facility_annual_ir_low_high": assessment[
            "conditional_diagnostic_facility_annual_ir_low_high"
        ],
        "conditional_diagnostic_facility_expected_death_fn_low_high": assessment[
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        ],
        "conditional_diagnostic_facility_expected_death_fn_diagnostics": assessment[
            "conditional_diagnostic_facility_expected_death_fn_diagnostics"
        ],
        "facility_total_risk_available": assessment["facility_total_risk_available"],
        "complete_facility_qra_claim": assessment["complete_facility_qra_claim"],
        "risk_atom_count": coverage["risk_atom_count"],
        "case_count": coverage["case_count"],
        "conditional_executed_case_count": coverage["conditional_executed_case_count"],
        "strict_uncomputed_case_count": coverage["strict_uncomputed_case_count"],
        "fresh_physics_executed": assessment["fresh_physics_executed"],
        "physical_validation_claim": assessment["physical_validation_claim"],
        "interpretation": (
            "A near-receptor synthetic geometry produces a nonzero diagnostic IR/F/N "
            "through the saved facility ledger. It is evidence of chain connectivity; "
            "it is not a complete facility QRA or provider-qualified result."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
