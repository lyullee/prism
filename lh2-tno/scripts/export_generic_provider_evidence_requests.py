"""Export closure and qualification requests for every generic LH2 packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.generic_provider_release_closure import (  # noqa: E402
    audit_generic_provider_release_closure,
    build_provider_release_closure_request,
    build_provider_qualification_request,
)


SCHEMA = "prism.generic_provider_evidence_requests.v1"


def _load_packet(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"provider packet must be an object: {path}")
    return value


def _provider_packets(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a flat packet or an explicit two-sided release set."""

    releases = packet.get("releases")
    if isinstance(releases, list) and releases and all(
        isinstance(item, dict) for item in releases
    ):
        return list(releases)
    return [packet]


def export_requests(
    packet_evidence: str | Path,
    *,
    packet_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return one evidence request for every packet, without promotion."""

    report = audit_generic_provider_release_closure(packet_evidence, packet_root=packet_root)
    requests: list[dict[str, Any]] = []
    closure_open_count = 0
    qualification_open_count = 0
    for event in report["event_rows"]:
        for packet_row in event["packet_rows"]:
            packet_path = packet_row.get("path")
            if not isinstance(packet_path, str):
                continue
            packet_path_obj = Path(packet_path)
            if not packet_path_obj.is_absolute():
                base = (
                    Path(packet_root).resolve()
                    if packet_root is not None
                    else Path(packet_evidence).resolve().parent
                )
                packet_path_obj = (base / packet_path_obj).resolve()
            packet_path = str(packet_path_obj)
            packet = _load_packet(packet_path_obj)
            provider_packets = _provider_packets(packet)
            closure_request = packet_row.get("closure_request")
            for packet_index, provider_packet in enumerate(provider_packets):
                if isinstance(closure_request, dict) and len(provider_packets) == 1:
                    request = dict(closure_request)
                    request["request_kind"] = "release_closure_and_qualification"
                    request["status"] = "OPEN_CLOSURE"
                    closure_open_count += 1
                elif packet_row.get("status") != "CLOSURE_READY_FOR_QUALIFICATION":
                    request = build_provider_release_closure_request(
                        provider_packet,
                        event_id=event.get("event_id"),
                        event_kind=provider_packet.get("event_kind"),
                        blocking_reasons=packet_row.get("blocking_reasons", ()),
                    )
                    request["request_kind"] = "release_closure_and_qualification"
                    request["status"] = "OPEN_CLOSURE"
                    closure_open_count += 1
                else:
                    request = build_provider_qualification_request(
                        provider_packet,
                        event_id=event.get("event_id"),
                        event_kind=provider_packet.get("event_kind"),
                        blocking_reasons=packet_row.get("blocking_reasons", ()),
                    )
                    request["request_kind"] = "qualification_only"
                    request["status"] = "OPEN_QUALIFICATION"
                    qualification_open_count += 1
                request["closure_status"] = packet_row.get("status")
                request["packet_path"] = packet_path
                request["packet_index"] = packet_index
                request["packet_count"] = len(provider_packets)
                if len(provider_packets) > 1:
                    request["request_id"] = (
                        f"{request['request_id']}::{provider_packet.get('port_id', packet_index)}"
                    )
                requests.append(request)
    return {
        "schema_version": SCHEMA,
        "status": "OPEN_PROVIDER_EVIDENCE_REQUESTS" if requests else "NO_PROVIDER_EVIDENCE_REQUESTS",
        "source_schema_version": report.get("schema_version"),
        "source_status": report.get("status"),
        "event_count": report.get("event_count", 0),
        "packet_count": report.get("provider_packet_count", 0),
        "packet_path_count": report.get("packet_path_count", 0),
        "request_count": len(requests),
        "closure_open_request_count": closure_open_count,
        "qualification_open_request_count": qualification_open_count,
        "qualified_provider_packet_count": report.get("qualified_provider_packet_count", 0),
        "requests": requests,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "diagnostic_only": True,
        "policy": (
            "Every generic provider packet is represented. Closure-open packets require termination, "
            "isolation and inventory evidence; closure-ready packets still require an exact qualification "
            "sidecar. No duration, inventory, frequency or facility QRA is inferred."
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
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "event_count": result["event_count"],
        "packet_count": result["packet_count"],
        "request_count": result["request_count"],
        "closure_open_request_count": result["closure_open_request_count"],
        "qualification_open_request_count": result["qualification_open_request_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
