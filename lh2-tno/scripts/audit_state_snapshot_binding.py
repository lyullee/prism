#!/usr/bin/env python3
"""Audit canonical equipment-state handoff into PRISM accident exports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.state_snapshot_binding_audit import (  # noqa: E402
    build_state_snapshot_binding_audit,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value["_record_path"] = str(path)
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    campaign = _load(args.campaign) if args.campaign is not None else None
    records = [_load(path) for path in args.diagnostic_record]
    report = build_state_snapshot_binding_audit(campaign, records)
    report["inputs"] = {
        "campaign": str(args.campaign) if args.campaign is not None else None,
        "diagnostic_records": [str(path) for path in args.diagnostic_record],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=None)
    parser.add_argument("--diagnostic-record", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"state snapshot binding audit failed: {error}") from error
    print(json.dumps({
        "status": report["status"],
        "record_count": report["record_count"],
        "bound_count": report["bound_count"],
        "digest_mismatch_count": report["digest_mismatch_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
