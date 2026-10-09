"""Audit provider-worklist event IDs against the facility campaign ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.diagnostic_campaign_binding import (  # noqa: E402
    build_diagnostic_campaign_binding,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-evidence", type=Path, required=True)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--provider-worklist", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        packet_evidence = json.loads(args.packet_evidence.read_text(encoding="utf-8"))
        campaign_result = json.loads(args.campaign_result.read_text(encoding="utf-8"))
        provider_worklist = (
            json.loads(args.provider_worklist.read_text(encoding="utf-8"))
            if args.provider_worklist
            else None
        )
        if not isinstance(packet_evidence, dict) or not isinstance(campaign_result, dict):
            raise ValueError("packet evidence and campaign result must be JSON objects")
        if provider_worklist is not None and not isinstance(provider_worklist, dict):
            raise ValueError("provider worklist must be a JSON object")
        report = build_diagnostic_campaign_binding(
            packet_evidence,
            campaign_result,
            provider_worklist,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"diagnostic campaign binding input error: {error}") from error
    report["packet_evidence_record"] = str(args.packet_evidence)
    report["campaign_result_record"] = str(args.campaign_result)
    if args.provider_worklist:
        report["provider_worklist_record"] = str(args.provider_worklist)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "packet_event_count": report["packet_event_count"],
        "campaign_event_count": report["campaign_event_count"],
        "campaign_case_count": report["campaign_case_count"],
        "campaign_risk_atom_count": report["campaign_risk_atom_count"],
        "structural_binding_complete": report["structural_binding_complete"],
        "packet_identity_consumed": report["packet_identity_consumed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"].startswith("PARTIAL_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
