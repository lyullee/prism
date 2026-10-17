"""Explicitly rebaseline a diagnostic facility campaign."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.facility_campaign_rebaseline import (  # noqa: E402
    rebaseline_facility_campaign,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledged", action="store_true")
    parser.add_argument("--previous-source-digest")
    parser.add_argument("--current-source-digest")
    args = parser.parse_args()
    try:
        report = rebaseline_facility_campaign(
            args.previous,
            args.current,
            acknowledged=args.acknowledged,
            previous_source_digest=args.previous_source_digest,
            current_source_digest=args.current_source_digest,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SystemExit(f"facility campaign rebaseline error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_count": report["event_count"],
        "identity_match_count": report["identity_match_count"],
        "result_digest_changed_count": report["digest_comparison"]["result_digest_changed_count"],
        "facility_qra_allowed": report["promotion"]["facility_qra_allowed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
