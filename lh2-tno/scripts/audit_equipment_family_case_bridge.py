#!/usr/bin/env python3
"""Audit the explicit bridge between equipment scenario coverage and case worklist."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_family_case_bridge_audit import (  # noqa: E402
    EquipmentFamilyCaseBridgeAuditError,
    audit_equipment_family_case_bridge,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value["_record_path"] = str(path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equipment-scenario-coverage", type=Path, required=True)
    parser.add_argument("--release-closure-worklist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_equipment_family_case_bridge(
            _object(args.equipment_scenario_coverage),
            _object(args.release_closure_worklist),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError,
            EquipmentFamilyCaseBridgeAuditError) as error:
        raise SystemExit(f"equipment family case bridge audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "asset_count": report["asset_count"],
        "case_count": report["case_count"],
        "case_assets_outside_scope": report["case_assets_outside_scope"],
        "scope_mismatch_case_count": report["scope_mismatch_case_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
