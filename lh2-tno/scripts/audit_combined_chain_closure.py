"""Combine PRISM packet and vertical-handoff chain closure records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.combined_chain_closure_audit import build_combined_chain_closure_audit  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-chain-audit", required=True, type=Path)
    parser.add_argument("--vertical-handoff-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_combined_chain_closure_audit(
        _load(args.packet_chain_audit), _load(args.vertical_handoff_audit)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "declared_event_count", "packet_subset_closed_event_count",
        "vertical_handoff_closed_event_count", "combined_diagnostic_closed_event_count",
        "qualified_provider_packet_count", "facility_qra_claim",
    )}, ensure_ascii=False))
    return 0 if result["status"] == "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
