"""Reconcile external provider responses with the facility evidence worklist."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_response_facility_reconciliation import (  # noqa: E402
    reconcile_provider_responses,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response-gap-audit", type=Path, required=True)
    parser.add_argument("--facility-evidence-request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = reconcile_provider_responses(
        _load(args.response_gap_audit),
        _load(args.facility_evidence_request),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "response_count": report["response_count"],
        "facility_case_count": report["facility_case_count"],
        "exact_case_match_count": report["exact_case_match_count"],
        "qualified_exact_case_match_count": report["qualified_exact_case_match_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
