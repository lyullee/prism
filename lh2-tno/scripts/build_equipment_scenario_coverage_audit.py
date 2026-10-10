#!/usr/bin/env python3
"""Build a generic equipment-to-LH2-accident-scenario coverage audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_scenario_coverage_audit import (  # noqa: E402
    EquipmentScenarioCoverageAuditError,
    audit_equipment_scenario_coverage,
)


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value["_record_path"] = str(path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equipment-audit", type=Path, required=True)
    parser.add_argument("--kind-crosswalk", type=Path)
    parser.add_argument("--required-family", action="append", dest="required_families")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_equipment_scenario_coverage(
            _object(args.equipment_audit),
            kind_crosswalk=_object(args.kind_crosswalk) if args.kind_crosswalk else None,
            required_families=args.required_families,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError,
            EquipmentScenarioCoverageAuditError) as error:
        raise SystemExit(f"equipment scenario coverage audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "asset_count": report["asset_count"],
        "mapped_asset_count": report["mapped_asset_count"],
        "scenario_family_count": report["scenario_family_count"],
        "accident_release_packet_allowed": report["promotion_gates"]["accident_release_packet_allowed"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
