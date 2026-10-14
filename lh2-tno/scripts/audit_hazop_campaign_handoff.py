"""Audit embedded diagnostics in one HAZOP facility handoff."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.hazop_campaign_handoff_audit import audit_hazop_campaign_handoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    report = audit_hazop_campaign_handoff(handoff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 2 if report["status"] == "HAZOP_CAMPAIGN_HANDOFF_AUDIT_BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
