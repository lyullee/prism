"""Audit provider_meta mass ledgers from an LH2 digital-twin export folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_mass_balance_audit import audit_provider_mass_balance_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = sorted(args.input_root.glob("*/provider_response.json"))
    records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    result = audit_provider_mass_balance_records(
        records,
        source_root=str(args.input_root.resolve()),
    )
    result["source_files"] = [str(path.resolve()) for path in files]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: result[key] for key in ("record_count", "status_counts", "promotion_allowed")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
