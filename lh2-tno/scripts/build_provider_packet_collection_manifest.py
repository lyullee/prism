"""Build a case-level worksheet for collecting qualified provider packets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_packet_collection_manifest import (  # noqa: E402
    build_provider_packet_collection_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence_request = json.loads(args.evidence_request.read_text(encoding="utf-8"))
        report = build_provider_packet_collection_manifest(evidence_request)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"provider packet collection input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "request_count": report["request_count"],
        "open_request_count": report["open_request_count"],
        "qualified_packet_count": report["qualified_packet_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "OPEN_PROVIDER_PACKET_COLLECTION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
