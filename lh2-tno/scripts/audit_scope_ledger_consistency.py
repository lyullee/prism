"""Audit that a scope matrix and merged facility ledger describe the same cases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.scope_ledger_consistency import audit_scope_ledger_consistency  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a declared accident scope matrix with a facility risk ledger."
    )
    parser.add_argument("--scope-matrix", type=Path, required=True)
    parser.add_argument("--facility-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        scope_matrix = json.loads(args.scope_matrix.read_text(encoding="utf-8"))
        ledger = json.loads(args.facility_ledger.read_text(encoding="utf-8"))
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
