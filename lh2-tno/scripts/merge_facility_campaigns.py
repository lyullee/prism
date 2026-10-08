"""Merge already evaluated equipment campaign ledgers at facility scope."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_ledger import (  # noqa: E402
    FacilityLedgerError,
    merge_facility_campaign_results,
)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge disjoint equipment campaign results into a fail-closed facility ledger."
    )
    parser.add_argument(
        "--campaign-result", type=Path, action="append", required=True,
        help="evaluated campaign result JSON; repeat once per disjoint equipment campaign",
    )
    parser.add_argument(
        "--expected-component-id", action="append", default=[],
        help="full-facility model component ID; repeat for every expected component",
    )
    parser.add_argument(
        "--scope-matrix", type=Path, action="append", default=[],
        help="optional major-accident scope matrix JSON; repeat per campaign",
    )
    parser.add_argument(
        "--required-accident-family", action="append", default=[],
        help="accident family that must be EXECUTED in a supplied scope matrix",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        results = [_json(path) for path in args.campaign_result]
        matrices = [_json(path) for path in args.scope_matrix]
        report = merge_facility_campaign_results(
            results,
            expected_component_ids=tuple(args.expected_component_id),
            scope_matrices=matrices,
            required_accident_families=tuple(args.required_accident_family),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, FacilityLedgerError) as error:
        raise SystemExit(f"facility ledger input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "campaign_count": len(report["campaign_ids"]),
        "event_count": report["event_count"],
        "known_receptor_count": len(report["known_contribution_annual_ir_low_high"]),
        "facility_total_risk_available": report["facility_total_risk_available"],
        "blocking_reason_count": len(report["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if report["status"] == "FACILITY_SCOPE_EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
