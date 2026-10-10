"""Export only the open, equipment-specific provider-closure requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.generic_provider_release_closure import (  # noqa: E402
    audit_generic_provider_release_closure,
)


SCHEMA = "prism.generic_provider_release_closure_requests.v1"


def export_requests(
    packet_evidence: str | Path,
    *,
    packet_root: str | Path | None = None,
) -> dict[str, object]:
    """Audit packets and retain the request block for every open packet."""

    report = audit_generic_provider_release_closure(
        packet_evidence,
        packet_root=packet_root,
    )
    requests: list[dict[str, object]] = []
    for event in report["event_rows"]:
        for packet in event["packet_rows"]:
            request = packet.get("closure_request")
            if isinstance(request, dict):
                requests.append(dict(request))
    return {
        "schema_version": SCHEMA,
        "status": "OPEN_PROVIDER_CLOSURE_REQUESTS" if requests else "NO_OPEN_PROVIDER_CLOSURE_REQUESTS",
        "source_schema_version": report.get("schema_version"),
        "source_status": report.get("status"),
        "event_count": report.get("event_count", 0),
        "open_request_count": len(requests),
        "qualified_provider_packet_count": report.get("qualified_provider_packet_count", 0),
        "requests": requests,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "diagnostic_only": True,
        "policy": (
            "Requests state the exact provider evidence still required. They do not "
            "infer termination, inventory, frequency or qualification."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-evidence", required=True, type=Path)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = export_requests(args.packet_evidence, packet_root=args.packet_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "event_count": result["event_count"],
        "open_request_count": result["open_request_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
