"""Audit HAZOP operating-mode identity in a saved realtime monitor result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.realtime_mode_trace import audit_realtime_hazop_mode_trace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="saved realtime monitor result")
    parser.add_argument("--output", type=Path, required=True, help="audit JSON output")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        report = audit_realtime_hazop_mode_trace(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"realtime HAZOP mode trace input error: {error}") from error
    report["input_record"] = str(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "row_count": report["row_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "REALTIME_HAZOP_MODE_TRACE_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
