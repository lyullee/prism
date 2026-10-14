#!/usr/bin/env python3
"""Audit HAZOP scenario identity through campaign and provider-request ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.hazop_scenario_trace_audit import audit_hazop_scenario_trace  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--facility-evidence-request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_hazop_scenario_trace(
        _object(args.campaign_result),
        facility_evidence_request=(
            _object(args.facility_evidence_request)
            if args.facility_evidence_request
            else None
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 2 if report["status"] == "HAZOP_SCENARIO_TRACE_BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
