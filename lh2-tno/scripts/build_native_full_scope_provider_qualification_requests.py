"""Build fail-closed qualification requests from a native full-scope readiness audit.

The output is an evidence-intake catalog.  It never changes a release packet,
assigns a frequency, or promotes a provider result.  Exact diagnostic packets
receive a qualification-only request only when the packet carries the
family-specific closed termination ledger; every other packet receives a
closure-and-qualification request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.generic_provider_release_closure import (  # noqa: E402
    build_provider_qualification_request,
    build_provider_release_closure_request,
)


SCHEMA = "prism.native_full_scope_provider_qualification_requests.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_packet_path(raw: str, readiness_path: Path) -> Path:
    path = Path(raw)
    candidates = [
        path,
        Path.cwd() / path,
        readiness_path.parent / path,
        readiness_path.parent.parent.parent.parent / path,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"resolved packet path is not available: {raw}")


def _releases(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = packet.get("releases")
    if isinstance(values, list) and values and all(isinstance(item, Mapping) for item in values):
        return list(values)
    return [packet]


def build_requests(readiness: Mapping[str, Any], *, readiness_path: Path) -> dict[str, Any]:
    rows = readiness.get("rows")
    if not isinstance(rows, list):
        raise ValueError("readiness.rows must be an array")
    requests: list[dict[str, Any]] = []
    qualification_only_count = 0
    closure_open_count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("readiness row must be an object")
        evidence = row.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        paths = evidence.get("resolved_packet_paths")
        if not isinstance(paths, list) or not paths:
            continue
        packet_path = _resolve_packet_path(str(paths[0]), readiness_path)
        packet = _load(packet_path)
        if not isinstance(packet, Mapping):
            raise ValueError(f"resolved packet must be an object: {packet_path}")
        exact = row.get("status") == "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC"
        generated: list[dict[str, Any]] = []
        for index, release in enumerate(_releases(packet)):
            if exact:
                qualification_request = build_provider_qualification_request(
                    release,
                    event_id=row.get("event_id"),
                    event_kind=release.get("event_kind"),
                    blocking_reasons=(evidence.get("qualification_readiness", {}) or {}).get(
                        "blockers", ()
                    ),
                )
                if qualification_request["acceptance"].get(
                    "termination_evidence_already_closed"
                ) is True:
                    request = qualification_request
                    kind = "qualification_only"
                else:
                    request = build_provider_release_closure_request(
                        release,
                        event_id=row.get("event_id"),
                        event_kind=release.get("event_kind"),
                        blocking_reasons=(evidence.get("qualification_readiness", {}) or {}).get(
                            "blockers", ()
                        ),
                    )
                    kind = "release_closure_and_qualification"
            else:
                request = build_provider_release_closure_request(
                    release,
                    event_id=row.get("event_id"),
                    event_kind=release.get("event_kind"),
                    blocking_reasons=(evidence.get("qualification_readiness", {}) or {}).get(
                        "blockers", ()
                    ),
                )
                kind = "release_closure_and_qualification"
            if kind == "qualification_only":
                qualification_only_count += 1
            else:
                closure_open_count += 1
            request["request_kind"] = kind
            request["readiness_status"] = row.get("status")
            request["packet_path"] = str(packet_path)
            request["packet_index"] = index
            request["packet_count"] = len(_releases(packet))
            generated.append(request)
        requests.append(
            {
                "event_id": row.get("event_id"),
                "component_id": row.get("component_id"),
                "readiness_status": row.get("status"),
                "readiness_blockers": list(
                    (evidence.get("qualification_readiness", {}) or {}).get("blockers", ())
                ),
                "packet_path": str(packet_path),
                "request_kind": (
                    generated[0]["request_kind"] if generated else "release_closure_and_qualification"
                ),
                "requests": generated,
            }
        )
    return {
        "schema_version": SCHEMA,
        "status": "OPEN_PROVIDER_QUALIFICATION_REQUESTS" if requests else "NO_PROVIDER_REQUESTS",
        "source_readiness_status": readiness.get("status"),
        "source_readiness_record": str(readiness_path),
        "request_count": len(requests),
        "qualification_only_request_count": qualification_only_count,
        "closure_and_qualification_request_count": closure_open_count,
        "qualified_provider_packet_count": 0,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "physical_validation_claim": False,
        "requests": requests,
        "policy": (
            "Requests preserve exact packet identity and digest references. They do not infer "
            "termination, inventory, frequency, physical validation, or facility QRA."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    readiness = _load(args.readiness)
    if not isinstance(readiness, Mapping):
        raise SystemExit("readiness must contain an object")
    report = build_requests(readiness, readiness_path=args.readiness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "request_count": report["request_count"],
        "qualification_only_request_count": report["qualification_only_request_count"],
        "closure_and_qualification_request_count": report["closure_and_qualification_request_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
