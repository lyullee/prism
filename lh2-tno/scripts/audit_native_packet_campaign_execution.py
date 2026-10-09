"""Audit consumption of native LH2 packets by a facility campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.native_packet_campaign import (  # noqa: E402
    build_native_packet_campaign_execution_ledger,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    campaign = _object(args.campaign)
    result = _object(args.result)
    provenance = _object(args.provenance) if args.provenance else None
    ledger = build_native_packet_campaign_execution_ledger(campaign, result, provenance)
    ledger["campaign_record"] = str(args.campaign)
    ledger["result_record"] = str(args.result)
    ledger["provenance_record"] = str(args.provenance) if args.provenance else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": ledger["status"],
        "event_count": ledger.get("event_count"),
        "case_count": ledger.get("case_count"),
        "chain_executed_case_count": ledger.get("chain_executed_case_count"),
        "failed_case_count": ledger.get("failed_case_count"),
        "packet_identity_consumed": ledger.get("packet_identity_consumed"),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if ledger["status"] == "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
