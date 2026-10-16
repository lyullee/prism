"""Build a quantitative request worklist from a saved forecast HAZOP scan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.forecast_handoff import build_forecast_quantitative_handoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scan: Any = json.loads(args.scan.read_text(encoding="utf-8"))
    result = build_forecast_quantitative_handoff(scan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "request_count": result["summary"]["request_count"],
        "ready_for_quantitative_evaluation_count": result["summary"]["ready_for_quantitative_evaluation_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
