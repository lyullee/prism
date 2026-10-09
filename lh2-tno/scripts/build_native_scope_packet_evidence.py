#!/usr/bin/env python3
"""Build strict packet-rebind evidence from a native generic-scope catalog.

The catalog is the source of packet paths; the separate state-snapshot audit
is checked before a row is marked exact.  This command never assigns a rate or
turns synthetic diagnostics into qualified provider evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build_evidence(catalog_path: Path, audit_path: Path, output_path: Path) -> dict[str, Any]:
    catalog = _load(catalog_path)
    audit = _load(audit_path)
    rows = catalog.get("event_rows")
    audit_rows = audit.get("rows")
    if not isinstance(rows, list) or not isinstance(audit_rows, list):
        raise ValueError("catalog event_rows and state audit rows must be arrays")
    audit_by_event = {
        row.get("event_id"): row
        for row in audit_rows
        if isinstance(row, dict) and isinstance(row.get("event_id"), str)
    }
    output_rows: list[dict[str, Any]] = []
    blocking: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            blocking.append("malformed catalog row")
            continue
        event_id = row.get("event_id")
        event_dir = row.get("event_dir")
        if not isinstance(event_id, str) or not isinstance(event_dir, str):
            blocking.append(str(event_id))
            continue
        event_root = catalog_path.parent / event_dir
        packet_name = (
            "resolved_release_set.json"
            if (event_root / "resolved_release_set.json").exists()
            else "resolved_release.json"
        )
        packet_path = event_root / packet_name
        snapshot_row = audit_by_event.get(event_id)
        exact = (
            row.get("status") == "EXACT_NATIVE_PACKET"
            and packet_path.exists()
            and isinstance(snapshot_row, dict)
            and snapshot_row.get("status") == "BOUND_AND_ECHOED"
            and snapshot_row.get("component_id") == row.get("component_id")
        )
        if not exact:
            blocking.append(event_id)
        output_rows.append({
            "event_id": event_id,
            "component_id": row.get("component_id"),
            "evidence": {
                "exact_opening_match": exact,
                "strict_packet_valid": exact,
                "resolved_packet_paths": [
                    str(packet_path.relative_to(catalog_path.parent)).replace("\\", "/")
                ] if packet_path.exists() else [],
                "state_snapshot_binding_status": snapshot_row.get("status") if isinstance(snapshot_row, dict) else None,
            },
        })
    result = {
        "schema_version": "prism.native_scope_packet_evidence.v1",
        "status": "EXACT_NATIVE_SCOPE_PACKET_EVIDENCE" if not blocking else "PARTIAL_NATIVE_SCOPE_PACKET_EVIDENCE",
        "rows": output_rows,
        "event_count": len(output_rows),
        "exact_event_count": len(output_rows) - len(blocking),
        "blocking_event_ids": blocking,
        "frequency_bound": False,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "catalog_record": str(catalog_path),
        "state_snapshot_audit_record": str(audit_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--state-snapshot-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_evidence(args.catalog, args.state_snapshot_audit, args.output)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"native scope packet evidence failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "event_count": result["event_count"],
        "exact_event_count": result["exact_event_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if result["status"] == "EXACT_NATIVE_SCOPE_PACKET_EVIDENCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
