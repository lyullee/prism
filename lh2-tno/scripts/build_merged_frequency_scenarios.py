#!/usr/bin/env python3
"""Extend generic literature scenarios to cover the merged vertical scope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.frequency_scenario_extension import (
    extend_frequency_scenarios_for_vertical_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add fixed declared vertical-handoff rates to generic frequency scenarios."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    result = extend_frequency_scenarios_for_vertical_handoff(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "scenario_count": len(result["scenarios"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
