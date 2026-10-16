"""Audit an equipment-twin state and explicit operating-mode HAZOP handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_hazop_handoff import (  # noqa: E402
    EquipmentHazopHandoffError,
    build_equipment_hazop_mode_handoff,
)


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EquipmentHazopHandoffError(f"cannot read {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise EquipmentHazopHandoffError(f"{path} must contain a JSON object")
    return value


def run(
    *,
    manifest_path: Path,
    runtime_frames_path: Path,
    hazop_table_set_path: Path,
    now_s: float,
    output_path: Path,
) -> dict[str, Any]:
    result = build_equipment_hazop_mode_handoff(
        _load(manifest_path),
        _load(runtime_frames_path),
        _load(hazop_table_set_path),
        now_s=now_s,
    )
    result["input_paths"] = {
        "manifest": str(manifest_path),
        "runtime_frames": str(runtime_frames_path),
        "hazop_table_set": str(hazop_table_set_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-frames", type=Path, required=True)
    parser.add_argument("--hazop-table-set", type=Path, required=True)
    parser.add_argument("--now-s", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(
            manifest_path=args.manifest,
            runtime_frames_path=args.runtime_frames,
            hazop_table_set_path=args.hazop_table_set,
            now_s=args.now_s,
            output_path=args.output,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"equipment-to-HAZOP handoff failed: {error}") from error
    print(
        json.dumps(
            {
                "status": result["status"],
                "facility_id": result["facility_id"],
                "component_coverage": result["component_coverage"],
                "selected_scenario_count": result["hazop_runtime_audit"].get(
                    "selected_scenario_count"
                ),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] == "EQUIPMENT_HAZOP_MODE_HANDOFF_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
