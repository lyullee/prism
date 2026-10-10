#!/usr/bin/env python3
"""Rebind an orientation sensitivity to a hash-reverified field record."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.orientation_sweep_rebaseline import (  # noqa: E402
    OrientationSweepRebaselineError,
    rebaseline_orientation_sweep,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", type=Path, required=True)
    parser.add_argument("--field-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledge-rebaseline", action="store_true")
    args = parser.parse_args()
    try:
        report = rebaseline_orientation_sweep(
            args.sweep,
            args.field_evidence,
            acknowledged=args.acknowledge_rebaseline,
        )
    except (OrientationSweepRebaselineError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"orientation sweep rebaseline input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["rebaseline"]["status"],
        "field_evidence_status": report["field_evidence_status"],
        "bearing_sweep_deg": report["bearing_sweep_deg"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
