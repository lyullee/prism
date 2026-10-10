"""Audit the accepted same-operator FFI Test 4 SLABx-LH2 comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.slabx_lh2_direct_comparison_audit import (  # noqa: E402
    SlabxDirectComparisonAuditError,
    audit_slabx_lh2_direct_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--readme", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_slabx_lh2_direct_comparison(
            args.predictions,
            args.refinement,
            readme_path=args.readme,
            provenance_path=args.provenance,
        )
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"SLABx direct comparison audit input error: {error}") from error
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
    return 0 if report["status"] == "DIRECT_COMPONENT_COMPARISON_REVIEW_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
