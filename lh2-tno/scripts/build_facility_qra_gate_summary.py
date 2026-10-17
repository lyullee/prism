#!/usr/bin/env python3
"""Build one fail-closed facility-QRA gate summary from saved evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_qra_gate import build_facility_qra_gate_summary  # noqa: E402


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", required=True, type=Path)
    parser.add_argument("--provider-audit", required=True, type=Path)
    parser.add_argument("--validation-matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_facility_qra_gate_summary(
        _object(args.assessment),
        _object(args.provider_audit),
        _object(args.validation_matrix),
        assessment_record=str(args.assessment),
        provider_audit_record=str(args.provider_audit),
        validation_record=str(args.validation_matrix),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "promotion_allowed": result["promotion_allowed"],
        "blocking_reason_count": len(result["blocking_reasons"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if result["promotion_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
