"""Build the fail-closed gate for a forecast facility campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.forecast_handoff import (  # noqa: E402
    build_forecast_facility_campaign_evidence_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    coverage: Any = json.loads(args.coverage.read_text(encoding="utf-8"))
    gate = build_forecast_facility_campaign_evidence_gate(coverage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": gate["status"],
        "facility_id": gate["facility_id"],
        "request_count": gate["summary"]["request_count"],
        "evidence_complete_count": gate["summary"]["evidence_complete_count"],
        "evidence_missing_count": gate["summary"]["evidence_missing_count"],
        "downstream_campaign_input_allowed": gate["downstream_campaign_input_allowed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
