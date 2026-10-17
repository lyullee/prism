"""Audit candidate dynamic-closure reclassification without changing QRA status."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_dynamic_closure_reclassification import (  # noqa: E402
    build_dynamic_closure_reclassification_audit,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-result", type=Path, required=True)
    parser.add_argument("--candidate-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_dynamic_closure_reclassification_audit(
        _load(args.current_result),
        _load(args.candidate_result),
        current_record=args.current_result.as_posix(),
        candidate_record=args.candidate_result.as_posix(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: report[k] for k in (
        "status", "matched_case_count", "candidate_eligible_case_count",
        "promotion_allowed",
    )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
