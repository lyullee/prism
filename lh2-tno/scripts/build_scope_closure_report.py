"""Build an explicit outdoor accident-scope closure report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.scope_closure_report import build_scope_closure_report


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument(
        "--frequency-scenarios",
        type=Path,
        help="Optional frequency scenario ledger produced by the facility-chain runner",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frequency_scenarios = (
        _object(args.frequency_scenarios) if args.frequency_scenarios else None
    )
    report = build_scope_closure_report(
        _object(args.scope_matrix), _object(args.facility_assessment), frequency_scenarios
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output),
                "declared_family_count": report["declared_family_count"],
                "declared_event_count": report["declared_event_count"],
                "strict_uncomputed_case_count": report["strict_uncomputed_case_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
