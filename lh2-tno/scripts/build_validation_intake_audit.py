"""Build the fail-closed validation-input inventory for PRISM."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.validation_intake_audit import audit_validation_intake_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspection-timeseries-audit",
        type=Path,
        required=True,
        help="inspection-centre timeseries audit JSON",
    )
    parser.add_argument(
        "--equipment-validation-audit",
        type=Path,
        help="optional external equipment validation audit JSON",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_validation_intake_files(
        args.inspection_timeseries_audit,
        args.equipment_validation_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
