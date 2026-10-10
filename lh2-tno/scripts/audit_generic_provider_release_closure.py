"""Audit provider release-boundary closure across a generic LH2 packet campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.generic_provider_release_closure import (  # noqa: E402
    audit_generic_provider_release_closure,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-evidence", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_generic_provider_release_closure(
        args.packet_evidence,
        packet_root=args.packet_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_count": report["event_count"],
        "closure_ready_event_count": report["closure_ready_event_count"],
        "closure_open_event_count": report["closure_open_event_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
