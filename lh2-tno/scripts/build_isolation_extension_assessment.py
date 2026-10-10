"""Merge the diagnostic isolation branches into the current LH2 facility ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.isolation_extension import (  # noqa: E402
    build_isolation_union_extension,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-result", type=Path, required=True)
    parser.add_argument("--base-scope-matrix", type=Path, required=True)
    parser.add_argument("--isolation-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_isolation_union_extension(
            _object(args.base_result),
            _object(args.base_scope_matrix),
            _object(args.isolation_result),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"isolation extension input error: {error}") from error

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "campaign_result.json": report["merged_campaign_result"],
        "scope_matrix.json": report["scope_matrix"],
        "isolation_rebound_result.json": report["isolation_rebound_result"],
        "risk_atom_chain_audit.json": report["risk_atom_chain_audit"],
        "equipment_state_release_audit.json": report["equipment_state_release_audit"],
        "facility_aggregate_closure_audit.json": report[
            "facility_aggregate_closure_audit"
        ],
        "facility_component_contribution_audit.json": report[
            "facility_component_contribution_audit"
        ],
    }
    for name, value in artifacts.items():
        _write(output_dir / name, value)

    verification = {
        "schema": "prism.isolation_union_extension_verification.v1",
        "status": report["status"],
        "facility_id": report["facility_id"],
        "base_counts": {
            "events": report["base_event_count"],
            "cases": report["base_case_count"],
            "risk_atoms": report["base_risk_atom_count"],
        },
        "isolation_counts": {
            "events": report["isolation_event_count"],
            "cases": report["isolation_case_count"],
            "risk_atoms": report["isolation_risk_atom_count"],
            "success_cases": report["isolation_branch_case_counts"]["success"],
            "failure_cases": report["isolation_branch_case_counts"]["failure"],
        },
        "merged_counts": {
            "events": report["merged_event_count"],
            "cases": report["merged_case_count"],
            "risk_atoms": report["merged_risk_atom_count"],
        },
        "risk_atom_chain_status": report["risk_atom_chain_audit"]["status"],
        "equipment_state_release_status": report["equipment_state_release_audit"][
            "status"
        ],
        "equipment_state_release_complete_cases": report[
            "equipment_state_release_audit"
        ]["complete_case_count"],
        "equipment_state_release_incomplete_cases": report[
            "equipment_state_release_audit"
        ]["incomplete_case_count"],
        "facility_aggregate_closure_status": report[
            "facility_aggregate_closure_audit"
        ]["status"],
        "facility_component_contribution_status": report[
            "facility_component_contribution_audit"
        ]["status"],
        "qualified_provider_packet_case_count": report[
            "merged_qualified_provider_packet_case_count"
        ],
        "facility_total_risk_available": report[
            "merged_facility_total_risk_available"
        ],
        "complete_facility_qra_claim": report["merged_complete_facility_qra_claim"],
        "policy": report["policy"],
        "limitations": report["limitations"],
    }
    _write(output_dir / "verification.json", verification)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output_dir": str(output_dir),
                "merged_event_count": report["merged_event_count"],
                "merged_case_count": report["merged_case_count"],
                "merged_risk_atom_count": report["merged_risk_atom_count"],
                "risk_atom_chain_status": report["risk_atom_chain_audit"]["status"],
                "equipment_state_release_status": report[
                    "equipment_state_release_audit"
                ]["status"],
                "facility_qra_claim": report["merged_complete_facility_qra_claim"],
            },
            ensure_ascii=False,
        )
    )
    expected_diagnostic = (
        report["status"] == "ISOLATION_UNION_EXTENSION_DIAGNOSTIC"
        and report["risk_atom_chain_audit"]["status"]
        == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
        and report["facility_aggregate_closure_audit"]["status"]
        == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
        and report["facility_component_contribution_audit"]["status"]
        == "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
        and report["merged_complete_facility_qra_claim"] is False
    )
    return 0 if expected_diagnostic else 2


if __name__ == "__main__":
    raise SystemExit(main())
