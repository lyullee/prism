"""Run a fail-closed facility HAZOP scan from a merged forecast frame set.

This command consumes the exact-grid output of
``merge_process_forecast_frames.py`` and a component-keyed HAZOP table set.
It performs qualitative state/mode selection for every component and time;
without an explicit quantitative callback, release, frequency, SLABx-LH2 and
facility IR/F-N results remain withheld.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.hazop_forecast import run_hazop_forecast_risk_scan  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build_scan(frame_record: Mapping[str, Any], tables: Mapping[str, Any]) -> dict[str, Any]:
    """Scan every component in a merged exact-grid frame record."""
    if frame_record.get("schema_version") != "prism.process_forecast_frame_set.v1":
        raise ValueError("frame record has an unsupported schema_version")
    if frame_record.get("status") != "PROCESS_FORECAST_FRAME_SET_MERGED":
        raise ValueError("frame record must be PROCESS_FORECAST_FRAME_SET_MERGED")
    facility_id = frame_record.get("facility_id")
    component_ids = frame_record.get("component_ids")
    frames = frame_record.get("frames")
    if not isinstance(facility_id, str) or not facility_id.strip():
        raise ValueError("frame record facility_id is required")
    if not isinstance(component_ids, list) or not component_ids or not all(
        isinstance(value, str) and value.strip() for value in component_ids
    ):
        raise ValueError("frame record component_ids must be a non-empty list")
    if len(set(component_ids)) != len(component_ids):
        raise ValueError("frame record component_ids must be unique")
    if not isinstance(frames, list) or not frames:
        raise ValueError("frame record must contain a non-empty frames array")
    table_map = tables.get("tables") if isinstance(tables.get("tables"), Mapping) else tables
    if not isinstance(table_map, Mapping) or set(table_map) != set(component_ids):
        raise ValueError("tables must cover exactly the merged component_ids")
    result = run_hazop_forecast_risk_scan(
        facility_id=facility_id,
        tables_by_component={component_id: table_map[component_id] for component_id in component_ids},
        forecast_frames=frames,
        expected_component_ids=component_ids,
    )
    result["input_frame_set"] = {
        "schema_version": frame_record["schema_version"],
        "status": frame_record["status"],
        "component_ids": list(component_ids),
        "operating_modes_by_component": frame_record.get("operating_modes_by_component"),
        "time_grid_s": frame_record.get("time_grid_s"),
        "frame_count": len(frames),
        "source": frame_record.get("source"),
    }
    result["policy"]["quantitative_callback_supplied"] = False
    result["policy"]["provider_release_created_by_cli"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_scan(_load(args.frames), _load(args.tables))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "component_count": len(result["input_frame_set"]["component_ids"]),
        "frame_count": result["input_frame_set"]["frame_count"],
        "trigger_count": result["trigger_count"],
        "evaluated_count": result["evaluated_count"],
        "withheld_count": result["withheld_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
