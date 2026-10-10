#!/usr/bin/env python3
"""Export a compact conditional facility IR/F-N view from a saved assessment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.conditional_facility_risk_view import (  # noqa: E402
    build_conditional_facility_risk_view,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--provider-mass-balance-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.facility_assessment.read_bytes()
    assessment = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(assessment, dict):
        raise SystemExit("facility assessment must contain one JSON object")
    mass_balance_audit = None
    audit_raw = None
    if args.provider_mass_balance_audit is not None:
        audit_raw = args.provider_mass_balance_audit.read_bytes()
        mass_balance_audit = json.loads(audit_raw.decode("utf-8-sig"))
        if not isinstance(mass_balance_audit, dict):
            raise SystemExit("provider mass-balance audit must contain one JSON object")
    view = build_conditional_facility_risk_view(
        assessment,
        provider_mass_balance_audit=mass_balance_audit,
    )
    view["source_assessment_path"] = args.facility_assessment.as_posix()
    view["source_assessment_sha256"] = hashlib.sha256(raw).hexdigest()
    if args.provider_mass_balance_audit is not None and audit_raw is not None:
        view["provider_mass_balance_audit_path"] = args.provider_mass_balance_audit.as_posix()
        view["provider_mass_balance_audit_sha256"] = hashlib.sha256(audit_raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": view["status"],
                "facility_id": view["facility_id"],
                "event_count": view["event_count"],
                "case_count": view["case_count"],
                "risk_atom_count": view["risk_atom_count"],
                "promotion_allowed": view["qualification"]["promotion_allowed"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
