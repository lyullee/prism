"""Rebind one native LH2 campaign event to an explicit compressible handoff."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.campaign_packet_rebind import (  # noqa: E402
    rebind_campaign_to_compressible_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--handoff-packet", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
        handoff = json.loads(args.handoff_packet.read_text(encoding="utf-8"))
        if not isinstance(campaign, dict) or not isinstance(handoff, dict):
            raise ValueError("campaign and handoff packet must be JSON objects")
        rebound, provenance = rebind_campaign_to_compressible_handoff(
            campaign, handoff, event_id=args.event_id
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"compressible handoff rebind input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rebound, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.provenance_output.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "COMPRESSIBLE_HANDOFF_REBOUND",
        "output": str(args.output),
        "provenance_output": str(args.provenance_output),
        "event_id": args.event_id,
        "provider_packet_promoted": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
