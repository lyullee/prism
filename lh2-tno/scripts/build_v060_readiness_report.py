#!/usr/bin/env python3
"""Build the versioned PRISM v0.6.0 IJHE readiness report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.v060_readiness import build_v060_readiness_report  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective-audit", type=Path, required=True)
    parser.add_argument("--union-verification", type=Path, required=True)
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--facility-assessment", type=Path, required=True)
    parser.add_argument("--completion-audit", type=Path, required=True)
    parser.add_argument("--validation-matrix", type=Path, required=True)
    parser.add_argument("--realtime-benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_v060_readiness_report(
            objective_audit=_load(args.objective_audit),
            union_verification=_load(args.union_verification),
            scope_matrix=_load(args.scope_matrix),
            facility_assessment=_load(args.facility_assessment),
            completion_audit=_load(args.completion_audit),
            validation_matrix=_load(args.validation_matrix),
            realtime_benchmark=_load(args.realtime_benchmark),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"v0.6.0 readiness input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["objective_status"],
        "conditional_chain_complete": report["conditional_chain_complete"],
        "event_count": report["chain"]["event_count"],
        "case_count": report["chain"]["case_count"],
        "risk_atom_count": report["chain"]["risk_atom_count"],
        "strict_blocking_check_ids": report["strict_blocking_check_ids"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
