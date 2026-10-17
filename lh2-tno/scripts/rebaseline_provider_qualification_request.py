"""Explicitly rebaseline one native-provider qualification request.

The command preserves the previous request and keeps qualification, frequency,
physical-validation, and facility-QRA promotion closed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_request_rebaseline import (  # noqa: E402
    ProviderRequestRebaselineError,
    rebaseline_provider_request_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--acknowledged",
        action="store_true",
        help="explicitly acknowledge digest drift; never opens a promotion gate",
    )
    parser.add_argument("--additional-blocker", action="append", default=[])
    args = parser.parse_args()
    try:
        report = rebaseline_provider_request_catalog(
            args.catalog,
            args.packet,
            event_id=args.event_id,
            acknowledged=args.acknowledged,
            additional_blockers=args.additional_blocker,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SystemExit(f"provider request rebaseline error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_id": report["event_id"],
        "previous_provider_source_digest": report["rebaseline"]["previous_provider_source_digest"],
        "current_provider_source_digest": report["rebaseline"]["current_provider_source_digest"],
        "promotion_allowed": report["rebaseline"]["promotion_allowed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
