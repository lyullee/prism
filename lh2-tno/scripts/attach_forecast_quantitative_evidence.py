"""Attach exact-keyed provider/frequency/consequence/facility evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.forecast_handoff import attach_forecast_quantitative_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--attachments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff: Any = json.loads(args.handoff.read_text(encoding="utf-8"))
    attachments: Any = json.loads(args.attachments.read_text(encoding="utf-8"))
    result = attach_forecast_quantitative_evidence(handoff, attachments)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "evidence_attached_count": result["summary"]["evidence_attached_count"],
        "facility_qra_promotion": result["policy"]["facility_qra_promotion"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
