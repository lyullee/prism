"""Scan predicted process frames against mode-specific HAZOP tables.

The command validates the forecast trigger path and writes explicit withheld
quantitative requests.  A provider/SLABx-LH2/facility evaluator is attached
through the Python API when numerical consequence results are required.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.hazop_forecast import run_hazop_forecast_risk_scan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", type=Path, required=True, help="JSON object keyed by component_id")
    parser.add_argument("--frames", type=Path, required=True, help="JSON array or {frames: [...]} forecast frames")
    parser.add_argument("--facility-id", required=True)
    parser.add_argument("--components", nargs="+", required=True)
    parser.add_argument("--evaluate-on", choices=("entry", "each_step"), default="entry")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tables = json.loads(args.tables.read_text(encoding="utf-8"))
    frames_payload = json.loads(args.frames.read_text(encoding="utf-8"))
    frames = frames_payload.get("frames") if isinstance(frames_payload, dict) else frames_payload
    result = run_hazop_forecast_risk_scan(
        facility_id=args.facility_id,
        tables_by_component=tables,
        forecast_frames=frames,
        expected_component_ids=tuple(args.components),
        evaluate_on=args.evaluate_on,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
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
