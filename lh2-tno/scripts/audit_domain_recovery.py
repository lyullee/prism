"""Audit whether an explicit larger-domain campaign resolves domain blockers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.domain_recovery_audit import build_domain_recovery_audit  # noqa: E402


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-campaign", type=Path, required=True)
    parser.add_argument("--recovery-campaign", type=Path, required=True)
    parser.add_argument("--baseline-defaults", type=Path, required=True)
    parser.add_argument("--recovery-defaults", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_domain_recovery_audit(
        _load(args.baseline_campaign),
        _load(args.recovery_campaign),
        _load(args.baseline_defaults),
        _load(args.recovery_defaults),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_count": report["event_count"],
        "baseline_domain_incomplete_event_count": report[
            "baseline_domain_incomplete_event_count"
        ],
        "recovery_domain_incomplete_event_count": report[
            "recovery_domain_incomplete_event_count"
        ],
        "recovered_event_count": len(report["recovered_event_ids"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
