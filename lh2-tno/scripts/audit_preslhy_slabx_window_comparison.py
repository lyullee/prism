#!/usr/bin/env python3
"""Audit an external PRESLHY/SLABx sensor-window comparison bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.preslhy_slabx_window_audit import (  # noqa: E402
    audit_preslhy_slabx_window_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_preslhy_slabx_window_comparison(args.results_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
