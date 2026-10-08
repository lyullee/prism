"""Audit scenario registers and time-series files without provider promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.scenario_evidence import audit_scenario_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_scenario_root(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "csv_rows": report.get("files", {}).get("csv_rows"),
        "scenario_rows": report.get("files", {}).get("scenario_rows"),
        "workbook_count": report.get("files", {}).get("workbook_count"),
        "qualified_packet_count": report.get("provider_promotion", {}).get("qualified_packet_count"),
    }, ensure_ascii=False))
    return 0 if report["status"] == "SCENARIO_EVIDENCE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

