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


def build_manifest_template(catalogue_path: str | Path) -> dict[str, Any]:
    path = Path(catalogue_path).resolve()
    catalogue = _load(path)
    if catalogue.get("schema_version") != "prism.generic_provider_evidence_requests.v1":
        raise ValueError("unsupported provider evidence catalogue schema")
    requests = catalogue.get("requests")
    if not isinstance(requests, list):
        raise ValueError("catalogue requests must be an array")
    entries: list[dict[str, Any]] = []
    group_paths: dict[str, str] = {}
    for index, raw in enumerate(requests):
        if not isinstance(raw, dict):
            raise ValueError(f"catalogue request {index} must be an object")
        current = raw.get("current_packet")
        if not isinstance(current, dict):
            raise ValueError(f"catalogue request {index} lacks current_packet")
        packet_path = str(raw.get("packet_path", ""))
        group_key = packet_path or str(raw.get("request_id", index))
        sidecar_path = group_paths.setdefault(
            group_key,
            f"REPLACE_WITH_REVIEWED_SIDECARS/{_safe_name(group_key)}.json",
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
