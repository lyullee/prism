"""Audit the restricted independent FFI Test 6 SLABx comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.slabx_lh2_independent_comparison_audit import (  # noqa: E402
    SlabxIndependentComparisonAuditError,
    audit_slabx_lh2_independent_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--numerical-gate", type=Path)
    parser.add_argument("--source-ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_slabx_lh2_independent_comparison(
            args.predictions,
            args.summary,
            numerical_gate_path=args.numerical_gate,
            source_ledger_path=args.source_ledger,
        )
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"independent comparison audit input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output.resolve()),
        "row_count": report["metrics"]["row_count"],
        "mae_vol_pct": report["metrics"]["MAE_vol_pct"],
        "rmse_vol_pct": report["metrics"]["RMSE_vol_pct"],
        "lfl": [report["metrics"]["observed_LFL_pairs"], report["metrics"]["predicted_LFL_pairs"]],
        "blocking_reason_count": len(report["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if report["status"] == "INDEPENDENT_COMPARISON_REVIEW_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
