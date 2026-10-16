#!/usr/bin/env python3
"""Independently reproduce the conditional facility IR/F-N ledger.

This command reads an existing facility assessment and recomputes its
conditional IR/F-N values from the saved risk atoms.  It does not execute a
provider or consequence model and never promotes a facility QRA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_aggregate_closure_audit import (  # noqa: E402
    build_facility_aggregate_closure_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.facility_assessment.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("facility assessment must contain one JSON object")
    source = value.get("facility_risk_ledger")
    if not isinstance(source, dict):
        source = value
    report = build_facility_aggregate_closure_audit(source)
    report["source_facility_assessment"] = args.facility_assessment.as_posix()
    report["source_facility_assessment_sha256"] = __import__("hashlib").sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "risk_atom_count": report["risk_atom_count"],
        "ir_mismatch_count": report["ir_mismatch_count"],
        "fn_mismatch_count": report["fn_mismatch_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC" else 2


if __name__ == "__main__":
    raise SystemExit(main())
