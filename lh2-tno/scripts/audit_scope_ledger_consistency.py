"""Audit that a scope matrix and merged facility ledger describe the same cases."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.scope_ledger_consistency import audit_scope_ledger_consistency  # noqa: E402


def _load_facility_ledger(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("facility ledger input must contain an object")
    # ``facility_assessment.json`` is the user-facing artifact and stores the
    # actual ledger under this wrapper.  Accepting it directly removes a
    # manual extraction step while preserving the same fail-closed audit.
    nested = value.get("facility_risk_ledger")
    if isinstance(nested, Mapping):
        return dict(nested)
    return dict(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a declared accident scope matrix with a facility risk ledger."
    )
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument(
        "--facility-ledger",
        type=Path,
        required=True,
        help="facility ledger JSON or facility_assessment.json containing facility_risk_ledger",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        scope_matrix = json.loads(args.scope_matrix.read_text(encoding="utf-8"))
        ledger = _load_facility_ledger(args.facility_ledger)
        result = audit_scope_ledger_consistency(scope_matrix, ledger)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"scope-ledger consistency input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output),
        "blocking_reason_count": len(result["blocking_reasons"]),
        "scope_event_count": result["scope_matrix_event_count"],
        "ledger_event_count": result["facility_ledger_event_count"],
    }, ensure_ascii=False))
    return 0 if result["status"] == "CONSISTENT_SCOPE_LEDGER" else 2


if __name__ == "__main__":
    raise SystemExit(main())
