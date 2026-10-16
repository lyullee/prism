"""Audit exact-keyed forecast quantitative evidence coverage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.forecast_handoff import audit_forecast_quantitative_evidence_coverage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--attachments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff: Any = json.loads(args.handoff.read_text(encoding="utf-8"))
    attachments: Any = json.loads(args.attachments.read_text(encoding="utf-8"))
    result = audit_forecast_quantitative_evidence_coverage(handoff, attachments)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "request_count": result["summary"]["request_count"],
        "evidence_complete_count": result["summary"]["evidence_complete_count"],
        "evidence_missing_count": result["summary"]["evidence_missing_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
