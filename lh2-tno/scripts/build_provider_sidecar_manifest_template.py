"""Build a fillable qualification-sidecar manifest from a provider catalogue.

The template records the exact request identity and digest values that a
reviewed provider sidecar must bind.  Placeholder paths are intentionally not
treated as evidence by the audit until they point to real JSON files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


SCHEMA = "prism.provider_qualification_sidecar_manifest.v1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"catalogue must contain an object: {path}")
    return value


def _safe_name(path: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", path).strip("_")
    return value or "provider_packet"


def _flatten_requests(catalogue: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize legacy and native full-scope request catalogues.

    The native facility campaign groups one or more release requests under an
    event row so that the row can retain readiness blockers.  The generic
    catalogue is already flat.  The sidecar manifest needs the same flat
    packet identity list for both forms.
    """
    schema = catalogue.get("schema_version")
    if schema == "prism.generic_provider_evidence_requests.v1":
        requests = catalogue.get("requests")
        if not isinstance(requests, list):
            raise ValueError("catalogue requests must be an array")
        return [raw for raw in requests if isinstance(raw, dict)]
    if schema == "prism.native_full_scope_provider_qualification_requests.v1":
        rows = catalogue.get("requests")
        if not isinstance(rows, list):
            raise ValueError("native request rows must be an array")
        flattened: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"native request row {row_index} must be an object")
            nested = row.get("requests")
            if not isinstance(nested, list):
                raise ValueError(f"native request row {row_index} lacks requests")
            for request_index, raw in enumerate(nested):
                if not isinstance(raw, dict):
                    raise ValueError(
                        f"native request row {row_index} item {request_index} must be an object"
                    )
                current = raw.get("current_packet")
                if not isinstance(current, dict):
                    raise ValueError(
                        f"native request row {row_index} item {request_index} lacks current_packet"
                    )
                flattened.append(raw)
        return flattened
    if schema == "prism.facility_evidence_request.v1":
        # The generic facility request is the operator-facing intake contract,
        # rather than a provider packet catalogue.  Adapt each case into the
        # same flat identity shape used by the sidecar template while keeping
        # the original request metadata for the reviewer.
        rows = catalogue.get("case_requests")
        if not isinstance(rows, list):
            raise ValueError("facility evidence request case_requests must be an array")
        flattened = []
        for row_index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise ValueError(f"facility case request {row_index} must be an object")
            identity = raw.get("exact_match_required")
            if not isinstance(identity, dict):
                raise ValueError(
                    f"facility case request {row_index} lacks exact_match_required"
                )
            ports = identity.get("port_ids") or raw.get("provider_packet_port_ids")
            if not isinstance(ports, list) or not ports:
                raise ValueError(f"facility case request {row_index} lacks port_ids")
            # The existing audit accepts one flat packet row.  A facility case
            # can declare multiple ports, so retain the port list in the
            # sidecar template and use the first port for legacy identity.
            current = {
                "event_id": identity.get("event_id", raw.get("event_id")),
                "component_id": identity.get("component_id", raw.get("component_id")),
                "port_id": ports[0],
                "port_ids": ports,
                "provider_source_digest": (identity.get("provider_source_digests") or [None])[0],
                "provider_result_digest": (identity.get("provider_result_digests") or [None])[0],
            }
            flattened.append({
                "request_id": raw.get("request_id"),
                "packet_path": "",
                "packet_index": 0,
                "request_kind": raw.get("request_kind"),
                "closure_status": raw.get("current_status"),
                "current_packet": current,
                "facility_case_request": raw,
            })
        return flattened
    raise ValueError("unsupported provider evidence catalogue schema")


def build_manifest_template(catalogue_path: str | Path) -> dict[str, Any]:
    path = Path(catalogue_path).resolve()
    catalogue = _load(path)
    requests = _flatten_requests(catalogue)
    entries: list[dict[str, Any]] = []
    group_paths: dict[str, str] = {}
    for index, raw in enumerate(requests):
        current = raw.get("current_packet")
        if not isinstance(current, dict):
            raise ValueError(f"catalogue request {index} lacks current_packet")
        packet_path = str(raw.get("packet_path", ""))
        facility_case = raw.get("facility_case_request")
        if isinstance(facility_case, dict):
            # A facility request has no provider packet yet.  Give the
            # reviewer a deterministic placeholder that is safe to replace.
            packet_path = (
                "REPLACE_WITH_REVIEWED_PROVIDER_PACKETS/"
                f"{_safe_name(str(raw.get('request_id', index)))}.json"
            )
        group_key = packet_path or str(raw.get("request_id", index))
        sidecar_name = _safe_name(group_key)
        if sidecar_name.endswith(".json"):
            sidecar_name = sidecar_name[:-5]
        sidecar_path = group_paths.setdefault(
            group_key,
            f"REPLACE_WITH_REVIEWED_SIDECARS/{sidecar_name}.json",
        )
        entry = {
            "request_id": raw.get("request_id"),
            "qualification_sidecar_path": sidecar_path,
            "packet_path": packet_path,
            "packet_index": raw.get("packet_index", 0),
            "request_kind": raw.get("request_kind"),
            "closure_status": raw.get("closure_status"),
            "expected_identity": {
                "event_id": current.get("event_id"),
                "component_id": current.get("component_id"),
                "port_id": current.get("port_id"),
                "provider_source_digest": current.get("provider_source_digest"),
                "provider_result_digest": current.get("provider_result_digest"),
            },
            "reviewer_action": (
                "Replace the placeholder path with a reviewed prism.provider_qualification_evidence.v1 file. "
                "For an ordered release set, use the same sidecar path for every request sharing packet_path."
            ),
        }
        if isinstance(facility_case, dict):
            exact = facility_case.get("exact_match_required")
            entry.update({
                "facility_case_request_id": facility_case.get("request_id"),
                "asset_id": facility_case.get("asset_id"),
                "hazop_scenario_id": facility_case.get("hazop_scenario_id"),
                "operating_mode": facility_case.get("operating_mode"),
                "scenario_families": facility_case.get("scenario_families", []),
                "required_input_origin": facility_case.get("required_input_origin"),
                "frequency_port_ids": facility_case.get("frequency_port_ids", []),
                "provider_packet_port_ids": facility_case.get("provider_packet_port_ids", []),
                "requested_exact_identity": exact,
                "digest_note": (
                    "The diagnostic digests copied into expected_identity are a baseline. "
                    "A reviewed provider packet must be issued with its own digests and "
                    "the facility request must be re-baselined before qualification."
                ),
            })
        entries.append(entry)
    return {
        "schema_version": SCHEMA,
        "status": "TEMPLATE_ONLY",
        "catalogue_schema_version": catalogue.get("schema_version"),
        "catalogue_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entry_count": len(entries),
        "entries": entries,
        "diagnostic_only": True,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "promotion_allowed": False,
        "interpretation": (
            "This file is a submission template, not qualification evidence. "
            "Placeholder paths must be replaced with reviewed sidecars before audit."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_manifest_template(args.catalogue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "entry_count": result["entry_count"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
