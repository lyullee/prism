"""Audit current provider evidence and legacy outputs in one report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_artifact_search import audit_provider_artifact_roots  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_provider_artifact_roots(args.current_root, tuple(args.legacy_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        **report["summary"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "QUALIFIED_PROVIDER_PACKET_FOUND" else 2


if __name__ == "__main__":
    raise SystemExit(main())
