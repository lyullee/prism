"""Run a fail-closed HAZOP forecast scan from a saved process-frame set.

The input frame set is produced by ``build_process_forecast_frames.py``. This
command performs the qualitative state/mode-to-scenario scan and writes the
trigger ledger. A quantitative evaluator (provider release, SLABx-LH2 and
facility campaign) remains an explicit application callback; this CLI never
creates a release, infers a frequency, or promotes facility IR/F-N.
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
    """Run the saved-frame HAZOP scan without a quantitative callback."""
    if frame_record.get("schema_version") != "prism.process_forecast_frame_set.v1":
        raise ValueError("frame record has an unsupported schema_version")
    frames = frame_record.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("frame record must contain a non-empty frames array")
    facility_id = frame_record.get("facility_id")
    component_id = frame_record.get("component_id")
    if not isinstance(facility_id, str) or not facility_id.strip():
        raise ValueError("frame record facility_id is required")
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError("frame record component_id is required")
    table_map = tables.get("tables") if isinstance(tables.get("tables"), Mapping) else tables
    if not isinstance(table_map, Mapping) or component_id not in table_map:
        raise ValueError(f"tables must contain HAZOP table for {component_id}")
    result = run_hazop_forecast_risk_scan(
        facility_id=facility_id,
        tables_by_component={component_id: table_map[component_id]},
        forecast_frames=frames,
        expected_component_ids=(component_id,),
    )
    result["input_frame_set"] = {
        "schema_version": frame_record["schema_version"],
        "component_id": component_id,
        "origin": frame_record.get("origin"),
        "operating_mode": frame_record.get("operating_mode"),
        "source": frame_record.get("source"),
        "frame_count": len(frames),
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
        "trigger_count": result["trigger_count"],
        "evaluated_count": result["evaluated_count"],
        "withheld_count": result["withheld_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
