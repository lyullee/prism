"""Compare one outdoor LH2 field bundle with an explicit model prediction."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.field_model_comparison import (  # noqa: E402
    FieldModelComparisonError,
    build_field_model_comparison_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-evidence", type=Path, required=True)
    parser.add_argument("--model-prediction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = build_field_model_comparison_record(
            args.field_evidence,
            args.model_prediction,
        )
    except (FieldModelComparisonError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"field/model comparison input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": record["status"],
        "matched_row_count": record["matching"]["matched_row_count"],
        "rmse_vol_pct": record["metrics"]["rmse_vol_pct"],
        "physical_validation_claim": record["physical_validation_claim"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if record["status"].startswith("RESTRICTED_FIELD_MODEL_COMPARISON") else 2


if __name__ == "__main__":
    raise SystemExit(main())
