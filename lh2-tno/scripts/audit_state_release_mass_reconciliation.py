"""Reconcile an authoritative mass mismatch with an explicit rebaseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.state_release_mass_reconciliation import (  # noqa: E402
    build_state_release_mass_reconciliation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative-audit", type=Path, required=True)
    parser.add_argument("--rebaseline-verification", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.authoritative_audit.read_text(encoding="utf-8"))
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.rebaseline_verification
    ]
    report = build_state_release_mass_reconciliation(audit, records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "authoritative_mismatch_count": report["authoritative_mismatch_count"],
        "resolved_mismatch_count": report["resolved_mismatch_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
