"""Audit termination, inventory and isolation closure in a provider packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_release_closure import audit_provider_release_closure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_provider_release_closure(args.packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "packet_count": report["packet_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "CLOSURE_READY_FOR_QUALIFICATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
