"""Merge disjoint outdoor accident-scope matrices for one facility."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.scope_matrix_merge import merge_scope_matrices  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-matrix", type=Path, action="append", required=True)
    parser.add_argument("--facility-id", required=True)
    parser.add_argument("--required-accident-family", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        matrices = []
        for path in args.scope_matrix:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"{path} must contain a JSON object")
            matrices.append(value)
        merged = merge_scope_matrices(
            matrices,
            facility_id=args.facility_id,
            required_families=tuple(args.required_accident_family),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"scope matrix merge input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "MERGED_SCOPE_MATRIX",
        "output": str(args.output),
        "facility_id": merged["facility_id"],
        "source_matrix_count": merged["source_matrix_count"],
        "matrix_complete": merged["matrix_complete"],
        "blocking_reason_count": len(merged["blocking_reasons"]),
    }, ensure_ascii=False))
    return 0 if merged["matrix_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
