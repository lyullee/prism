"""Rebuild a campaign using the exact strict packets selected by worklist evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.campaign_packet_rebind import (  # noqa: E402
    packet_rebind_provenance,
    rebind_campaign_to_worklist_packets,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--packet-evidence", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--provenance-output",
        type=Path,
        help="Optional JSON file for rebind provenance; the campaign output remains strict RiskCampaign JSON.",
    )
    args = parser.parse_args()
    try:
        campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
        evidence = json.loads(args.packet_evidence.read_text(encoding="utf-8"))
        if not isinstance(campaign, dict) or not isinstance(evidence, dict):
            raise ValueError("campaign and packet evidence must be JSON objects")
        rebound = rebind_campaign_to_worklist_packets(
            campaign,
            evidence,
            packet_root=args.packet_root,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"campaign packet rebind input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rebound, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    event_ids = [route["event_id"] for route in rebound.get("event_routes", [])]
    provenance = packet_rebind_provenance(evidence, event_ids)
    provenance_path = args.provenance_output or args.output.with_suffix(args.output.suffix + ".provenance.json")
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "REBIND_COMPILED",
        "output": str(args.output),
        "event_count": len(rebound.get("event_routes", [])),
        "provenance_output": str(provenance_path),
        "packet_rebind_provenance": provenance,
        "promotion_policy": "strict packet identity rebind does not qualify packets or facility QRA",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
