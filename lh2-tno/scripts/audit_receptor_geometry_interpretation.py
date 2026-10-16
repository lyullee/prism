"""Audit the geometry meaning of conditional full-scope and near-receptor results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.receptor_geometry_interpretation import (  # noqa: E402
    build_receptor_geometry_interpretation_from_paths,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explain zero/full-scope versus near-receptor conditional IR/F-N without facility-QRA promotion."
    )
    parser.add_argument("--full-scope-assessment", type=Path, required=True)
    parser.add_argument("--near-receptor-verification", type=Path, required=True)
    parser.add_argument("--full-scope-manifest", type=Path, required=True)
    parser.add_argument("--near-receptor-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_receptor_geometry_interpretation_from_paths(
        args.full_scope_assessment,
        args.near_receptor_verification,
        args.full_scope_manifest,
        args.near_receptor_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output), "blocking_reason_count": len(result["blocking_reasons"])}, ensure_ascii=False))
    return 0 if result["status"] == "PASS_DIAGNOSTIC_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
