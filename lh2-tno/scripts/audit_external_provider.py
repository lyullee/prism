"""Audit an external LH2 digital-twin provider export without promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_evidence import audit_provider_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_provider_root(args.provider_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output), "blocking_reasons": report["blocking_reasons"]}, ensure_ascii=False))
    return 0 if report["status"] == "EXECUTABLE_PROVIDER" else 2


if __name__ == "__main__":
    raise SystemExit(main())
