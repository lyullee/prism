#!/usr/bin/env python3
"""Evaluate explicit operating-mode HAZOP selection on runtime frames."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.observed_hazop_runtime import audit_observed_hazop_runtime  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-frames", type=Path, required=True)
    parser.add_argument("--hazop-table-set", type=Path, required=True)
    parser.add_argument("--now-s", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_observed_hazop_runtime(
            _load(args.runtime_frames),
            _load(args.hazop_table_set),
            now_s=args.now_s,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"observed HAZOP runtime audit failed: {error}") from error
    report["runtime_frames_record"] = str(args.runtime_frames)
    report["hazop_table_set_record"] = str(args.hazop_table_set)
    report["now_s"] = args.now_s
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "runtime_frame_count": report["runtime_frame_count"],
        "selected_scenario_count": report["selected_scenario_count"],
        "operating_mode_counts": report["operating_mode_counts"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if report["status"] == "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
