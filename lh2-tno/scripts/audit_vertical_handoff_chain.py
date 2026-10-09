"""Audit the five operator-limited vertical-handoff events."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.vertical_handoff_chain_audit import build_vertical_handoff_chain_audit


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", required=True, type=Path)
    parser.add_argument("--release-catalog", required=True, type=Path)
    parser.add_argument("--base-chain-audit", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_vertical_handoff_chain_audit(
        _load(args.campaign_result),
        _load(args.release_catalog),
        base_chain_audit=_load(args.base_chain_audit) if args.base_chain_audit else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "vertical_event_count", "vertical_chain_closed_event_count",
        "vertical_case_count", "vertical_risk_atom_count", "all_declared_events_diagnostic_chain_closed",
    )}, ensure_ascii=False))
    return 0 if result["status"] == "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
