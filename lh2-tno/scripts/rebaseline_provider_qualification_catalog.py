"""Explicitly rebaseline a provider qualification request catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_request_rebaseline import (  # noqa: E402
    rebaseline_provider_request_catalog_batch,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acknowledged", action="store_true")
    args = parser.parse_args()
    packets: dict[str, Path] = {}
    for path in sorted(args.packet_root.glob("events/*/resolved_release*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        event_id = value.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise SystemExit(f"packet has no event_id: {path}")
        releases = value.get("releases")
        if isinstance(releases, list):
            for release in releases:
                if not isinstance(release, dict) or not isinstance(release.get("port_id"), str):
                    raise SystemExit(f"two-sided packet has invalid endpoint: {path}")
                key = f"{event_id}::{release['port_id']}"
                if key in packets:
                    raise SystemExit(f"duplicate packet request key: {key}")
                # Use the endpoint object so its result digest is bound to the
                # matching endpoint request rather than to the shared set.
                packets[key] = release
        else:
            if event_id in packets:
                raise SystemExit(f"duplicate packet event_id: {event_id}")
            packets[event_id] = value
    try:
        report = rebaseline_provider_request_catalog_batch(
            args.catalog, packets, acknowledged=args.acknowledged
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SystemExit(f"provider request catalog rebaseline error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "event_count": report["event_count"],
        "identity_match_count": report["identity_match_count"],
        "result_digest_changed_count": report["result_digest_changed_count"],
        "facility_qra_allowed": report["facility_qra_allowed"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
