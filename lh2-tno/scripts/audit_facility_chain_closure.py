"""Audit release-packet to final facility-harm closure for a saved ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.chain_closure_audit import (  # noqa: E402
    ChainClosureAuditError,
    build_chain_closure_audit,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--packet-evidence", type=Path)
    parser.add_argument("--packet-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        campaign = _object(args.campaign_result)
        evidence = _object(args.packet_evidence) if args.packet_evidence else None
        result = build_chain_closure_audit(
            campaign,
            packet_evidence=evidence,
            packet_root=args.packet_root,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, ChainClosureAuditError) as error:
        raise SystemExit(f"facility chain closure audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "packet_event_count": result["packet_event_count"],
        "packet_chain_closed_event_count": result["packet_chain_closed_event_count"],
        "campaign_events_without_packet_count": result["campaign_events_without_packet_count"],
        "facility_ir_aggregate_closed": result["facility_ir_aggregate_closed"],
        "facility_fn_aggregate_closed": result["facility_fn_aggregate_closed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if result["status"] == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
