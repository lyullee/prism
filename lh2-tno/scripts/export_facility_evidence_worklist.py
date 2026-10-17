"""Export a facility evidence request as JSON and optional CSV worklists."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.facility_evidence_worklist import build_facility_evidence_worklist  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    report = build_facility_evidence_worklist(request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "sequence", "request_id", "event_id", "component_id", "asset_id",
            "release_branch_id", "annual_condition_id", "scenario_families",
            "current_status", "gap_class", "required_input_origin",
            "port_ids", "termination_basis", "termination_time_s", "blocking_reasons",
            "required_provider_evidence",
        ]
        with args.csv_output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report["case_rows"]:
                boundary = row["release_boundary"]
                identity = row["exact_identity"]
                writer.writerow({
                    "sequence": row["sequence"],
                    "request_id": row["request_id"],
                    "event_id": row["event_id"],
                    "component_id": row["component_id"],
                    "asset_id": row["asset_id"],
                    "release_branch_id": row["release_branch_id"],
                    "annual_condition_id": row["annual_condition_id"],
                    "scenario_families": ";".join(row["scenario_families"]),
                    "current_status": row["current_status"],
                    "gap_class": row["gap_class"],
                    "required_input_origin": row["required_input_origin"],
                    "port_ids": ";".join(identity["port_ids"]),
                    "termination_basis": boundary["termination_basis"],
                    "termination_time_s": boundary["termination_time_s"],
                    "blocking_reasons": ";".join(row["blocking_reasons"]),
                    "required_provider_evidence": ";".join(row["required_provider_evidence"]),
                })
    print(json.dumps({
        "status": report["status"],
        "facility_id": report["facility_id"],
        "case_count": report["case_count"],
        "component_count": len(report["component_summary"]),
        "family_count": len(report["family_summary"]),
        "output": str(args.output),
        "csv_output": str(args.csv_output) if args.csv_output else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
