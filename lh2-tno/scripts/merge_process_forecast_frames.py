"""Merge saved component process forecasts on one exact time grid.

The merger is a deterministic facility input boundary. It requires one
``PROCESS_FORECAST_FRAMES_READY`` record per component and refuses to
interpolate, drop components, infer frequencies, or create a quantitative
release/facility risk result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.process_forecast import merge_forecast_frame_sets  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frames",
        type=Path,
        action="append",
        required=True,
        help="saved PROCESS_FORECAST_FRAMES_READY JSON; repeat once per component",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = merge_forecast_frame_sets([_load(path) for path in args.frames])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "component_count": len(result["component_ids"]),
        "frame_count": len(result["frames"]),
        "time_count": len(result["time_grid_s"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
