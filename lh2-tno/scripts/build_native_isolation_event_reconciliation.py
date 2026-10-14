"""Build the diagnostic per-event reconciliation for a native isolation catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lh2_tno.native_isolation_reconciliation import build_native_isolation_event_reconciliation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_native_isolation_event_reconciliation(args.catalog_dir)
    result["catalog_dir"] = str(args.catalog_dir)
    result["_record_path"] = str(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output),
        "event_count": result["event_count"],
        "mismatch_count": result["mismatch_count"],
    }, ensure_ascii=False))
    return 0 if result["status"] == "NATIVE_ISOLATION_EVENT_ROWS_RECONCILED_DIAGNOSTIC" else 2


if __name__ == "__main__":
    raise SystemExit(main())
