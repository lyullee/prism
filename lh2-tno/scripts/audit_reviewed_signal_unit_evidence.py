"""Audit engineering-document anchors for a reviewed signal-unit map."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.reviewed_signal_unit_evidence import audit_reviewed_signal_unit_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-map", type=Path, required=True)
    parser.add_argument("--source-document", type=Path, required=True)
    parser.add_argument("--timeseries-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_reviewed_signal_unit_evidence(
            args.unit_map,
            source_document=args.source_document,
            timeseries_audit=args.timeseries_audit,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"reviewed signal-unit evidence input error: {error}") from error
    report["source_records"] = {
        "unit_map": str(args.unit_map),
        "source_document": str(args.source_document),
        "timeseries_audit": str(args.timeseries_audit) if args.timeseries_audit else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "signal_count": report["signal_count"],
        "reviewed_signal_count": report["reviewed_signal_count"],
        "observed_unmapped_tags": report["observed_unmapped_tags"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "REVIEWED_SIGNAL_UNIT_EVIDENCE_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
