#!/usr/bin/env python3
"""Verify source hashes and optional regeneration of observed-state evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.observed_state_replay import audit_observed_state_replay  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--regenerated-evidence", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_observed_state_replay(
            args.manifest,
            args.evidence,
            regenerated_evidence=args.regenerated_evidence,
            source_root=args.source_root,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"observed state replay audit failed: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "source_count": report["source_count"],
        "matched_source_count": report["matched_source_count"],
        "regeneration_match": report["regeneration"]["canonical_digest_match"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if report["status"] == "SOURCE_REPLAY_MATCHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
