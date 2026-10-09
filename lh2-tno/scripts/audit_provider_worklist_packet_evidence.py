"""Audit saved external-provider packets against the generic LH2 worklist."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_worklist_evidence import (  # noqa: E402
    build_provider_worklist_packet_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        worklist = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        if not isinstance(worklist, dict):
            raise ValueError("provider worklist must contain a JSON object")
        report = build_provider_worklist_packet_evidence(worklist, args.results_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"provider worklist evidence input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "worklist_event_count": report["worklist_event_count"],
        "candidate_event_count": report["candidate_event_count"],
        "exact_match_event_count": report["exact_match_event_count"],
        "strict_packet_valid_event_count": report["strict_packet_valid_event_count"],
        "consequence_chain_event_count": report["consequence_chain_event_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
