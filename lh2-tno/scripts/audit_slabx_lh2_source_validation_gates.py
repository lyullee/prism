#!/usr/bin/env python3
"""Audit the external SLABx-LH2 source-term validation gate ledger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.slabx_lh2_source_validation_gate_audit import (  # noqa: E402
    SlabxSourceValidationGateAuditError,
    audit_slabx_lh2_source_validation_gates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-ledger", type=Path, required=True)
    parser.add_argument("--casewise", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_slabx_lh2_source_validation_gates(
            args.gate_ledger,
            casewise_path=args.casewise,
            summary_path=args.summary,
        )
    except (OSError, UnicodeDecodeError, ValueError, SlabxSourceValidationGateAuditError) as error:
        raise SystemExit(f"SLABx-LH2 source validation gate audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "gate_count": report["gate_count"],
        "independent_quantitative_gate_count": report["independent_quantitative_gate_count"],
        "casewise_row_count": report["casewise_numerical_closure"]["row_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
