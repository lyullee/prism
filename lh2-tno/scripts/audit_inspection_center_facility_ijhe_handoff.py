"""Audit the reconstructed facility bridge and campaign handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    from lh2_tno.inspection_center_facility_ijhe_audit import (
        build_inspection_center_facility_ijhe_audit,
    )

    result = build_inspection_center_facility_ijhe_audit(
        _object(args.bridge), _object(args.handoff)
    )
    result["input_evidence"] = {
        "bridge": str(args.bridge),
        "handoff": str(args.handoff),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", type=Path, default=ROOT / "examples/inspection_center_facility_hazop_bridge.json")
    parser.add_argument("--handoff", type=Path, default=ROOT / "examples/inspection_center_facility_campaign_handoff.json")
    parser.add_argument("--output", type=Path, default=ROOT / "examples/inspection_center_facility_ijhe_handoff_audit.json")
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        raise SystemExit(f"facility IJHE handoff audit failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "check_count": len(result["checks"]),
        "blocking_reason_count": len(result["blocking_reasons"]),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if result["status"] == "PASS_WITH_SCOPE_LIMITATIONS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
