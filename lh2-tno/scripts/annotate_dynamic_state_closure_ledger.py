#!/usr/bin/env python3
"""Annotate missing dynamic-state fields without inferring provider closure."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.dynamic_state_closure_audit import (  # noqa: E402
    annotate_missing_dynamic_state_closure_fields,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    source = json.loads(raw.decode("utf-8"))
    if not isinstance(source, dict):
        raise SystemExit("input must contain one JSON object")
    result = annotate_missing_dynamic_state_closure_fields(source)
    result["dynamic_state_closure_normalization"]["source_path"] = args.input.as_posix()
    result["dynamic_state_closure_normalization"]["source_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    meta = result["dynamic_state_closure_normalization"]
    print(
        json.dumps(
            {
                "status": meta["status"],
                "annotated_case_count": meta["annotated_case_count"],
                "annotated_uncomputed_case_count": meta[
                    "annotated_uncomputed_case_count"
                ],
                "closure_inferred": meta["closure_inferred"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
