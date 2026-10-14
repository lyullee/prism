"""Audit inspection-center operating-sequence and HAZOP evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.hazop_operating_mode_evidence_audit import audit_hazop_operating_mode_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--timeseries-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_hazop_operating_mode_evidence(
            args.source_root,
            timeseries_audit_path=args.timeseries_audit,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"HAZOP operating-mode evidence input error: {error}") from error
    report["source_records"] = {
        "source_root": str(args.source_root),
        "timeseries_audit": str(args.timeseries_audit) if args.timeseries_audit else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "sequence_row_count": report["sequence_row_count"],
        "operating_mode_counts": report["operating_mode_counts"],
        "numeric_state_binding_allowed": report["timeseries_audit"]["numeric_state_binding_allowed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "HAZOP_OPERATING_MODE_EVIDENCE_AUDIT_WITH_STATE_BINDING_ALLOWED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
