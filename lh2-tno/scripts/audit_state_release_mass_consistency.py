"""Audit numeric mass consistency between equipment snapshots and release packets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.state_release_mass_consistency_audit import (  # noqa: E402
    build_state_release_mass_consistency_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-result", type=Path, required=True)
    parser.add_argument("--relative-tolerance", type=float, default=1e-6)
    parser.add_argument("--absolute-tolerance", type=float, default=1e-9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        campaign = json.loads(args.campaign_result.read_text(encoding="utf-8"))
        if not isinstance(campaign, dict):
            raise ValueError("campaign result must be an object")
        report = build_state_release_mass_consistency_audit(
            campaign,
            relative_tolerance=args.relative_tolerance,
            absolute_tolerance=args.absolute_tolerance,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"state-release mass consistency audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "case_count": report["case_count"],
        "comparable_case_count": report["comparable_case_count"],
        "mismatch_case_count": report["mismatch_case_count"],
        "not_comparable_case_count": report["not_comparable_case_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
