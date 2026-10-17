#!/usr/bin/env python3
"""Audit dynamic-state closure counts in campaign and facility ledgers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.dynamic_state_closure_audit import (  # noqa: E402
    build_dynamic_state_closure_ledger_audit,
)


def _read(path: Path) -> tuple[object, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _unwrap_campaign(value: object) -> object:
    """Accept a direct campaign or an explicit ``{"result": ...}`` wrapper."""
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        return value["result"]
    return value


def _unwrap_facility(value: object) -> object:
    """Accept a direct ledger or a facility-assessment ledger wrapper."""
    if isinstance(value, dict) and isinstance(value.get("facility_risk_ledger"), dict):
        return value["facility_risk_ledger"]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign",
        action="append",
        type=Path,
        default=[],
        help="campaign JSON ledger; repeat for every campaign merged into the facility ledger",
    )
    parser.add_argument("--facility", type=Path, help="optional facility JSON ledger")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    campaigns: list[object] = []
    campaign_digests: list[str] = []
    for path in args.campaign:
        value, digest = _read(path)
        campaigns.append(_unwrap_campaign(value))
        campaign_digests.append(digest)
    facility = None
    facility_digest = None
    if args.facility is not None:
        facility, facility_digest = _read(args.facility)
        facility = _unwrap_facility(facility)
    if any(not isinstance(value, dict) for value in campaigns):
        raise SystemExit("each campaign file must contain one JSON object")
    if facility is not None and not isinstance(facility, dict):
        raise SystemExit("facility file must contain one JSON object")
    report = build_dynamic_state_closure_ledger_audit(
        campaign_results=campaigns,
        facility_result=facility,
    )
    report["source_campaigns"] = [path.as_posix() for path in args.campaign]
    report["source_campaign_sha256"] = campaign_digests
    report["source_facility"] = args.facility.as_posix() if args.facility else None
    report["source_facility_sha256"] = facility_digest
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "check_count": report["check_count"],
                "blocking_reason_count": report["blocking_reason_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
