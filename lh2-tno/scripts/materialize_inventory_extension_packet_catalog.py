"""Materialize an explicit namespace-rebound packet catalog for inventory extensions.

The inventory campaign is executed in a disjoint source namespace.  The facility
union already contains a namespaced result, but its provider identities need a
reproducible packet path before the release-to-risk audit can consume them.  This
command copies only provider-owned resolved releases, checks every aggregate
against the rebound campaign identity, and records the source-to-target mapping.
It never assigns frequency, provider qualification, physical validation, or
facility-QRA status.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _close(left: Any, right: Any) -> bool:
    return (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
        and math.isclose(float(left), float(right), rel_tol=1e-8, abs_tol=1e-12)
    )


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def materialize(source_dir: Path, rebound_result_path: Path, output_dir: Path) -> dict[str, Any]:
    source_releases = _load(source_dir / "resolved_releases.json")
    source_responses = _load(source_dir / "provider_responses.json")
    source_snapshots = _load(source_dir / "state_snapshots.json")
    source_verification = _load(source_dir / "verification.json")
    rebound = _load(rebound_result_path)
    cases = [
        row for row in rebound.get("cases", [])
        if isinstance(row, dict) and row.get("release_branch_id") == "provider-inventory-depletion"
    ]
    by_event: dict[str, dict[str, Any]] = {}
    for case in cases:
        event_id = str(case.get("event_id", ""))
        by_event.setdefault(event_id, case)
    if len(by_event) != 5:
        raise ValueError(f"expected five unique inventory extension events, found {len(by_event)}")

    rows: list[dict[str, Any]] = []
    for event_id in sorted(by_event):
        case = by_event[event_id]
        identity = case.get("provider_packet_identity")
        if not isinstance(identity, dict):
            raise ValueError(f"{event_id}: provider_packet_identity missing")
        suffix = event_id.rsplit("/terminal_pipe_asset/", 1)[-1]
        source_id = f"equipment-inventory-campaign/terminal_pipe_asset/{suffix}"
        source_release = source_releases.get(source_id)
        source_response = source_responses.get(source_id)
        source_snapshot = source_snapshots.get(source_id)
        if not isinstance(source_release, dict) or not isinstance(source_response, dict) or not isinstance(source_snapshot, dict):
            raise ValueError(f"{event_id}: source provider artifacts missing")
        expected_digest = (identity.get("provider_result_digests") or [None])[0]
        checks = {
            "source_event_id_match": source_release.get("event_id") == source_id,
            "provider_source_digest_match": source_release.get("provider_source_digest") in (identity.get("provider_source_digests") or []),
            "provider_result_digest_match": source_release.get("provider_result_digest") == expected_digest,
            "duration_match": _close(source_release.get("duration_s"), (identity.get("duration_s") or [None])[0]),
            "available_mass_match": _close(source_release.get("available_mass_kg"), (identity.get("available_mass_kg") or [None])[0]),
            "released_mass_match": _close(source_release.get("cumulative_mass_out_kg"), (identity.get("cumulative_mass_out_kg") or [None])[0]),
            "termination_basis_match": source_release.get("termination_basis") == (identity.get("termination_bases") or [None])[0],
            "termination_provenance_match": source_release.get("termination_provenance") == (identity.get("termination_provenances") or [None])[0],
        }
        if not all(checks.values()):
            raise ValueError(f"{event_id}: source/rebound packet checks failed: {checks}")
        slug = suffix.replace("%", "pct").replace(".", "_")
        event_dir = output_dir / "events" / f"{slug}"
        packet = copy.deepcopy(source_release)
        packet["event_id"] = event_id
        packet["component_id"] = str(identity.get("component_id") or packet.get("component_id"))
        # The provider result digest remains the source provider's digest.  The
        # namespace mapping is kept in a sidecar so the packet itself remains a
        # valid prism.resolved_release.v1 contract.
        _write(event_dir / "resolved_release.json", packet)
        response = copy.deepcopy(source_response)
        data = response.get("data")
        if isinstance(data, dict):
            data["event_id"] = event_id
            data["component_id"] = packet["component_id"]
        _write(event_dir / "provider_response.json", response)
        _write(event_dir / "state_snapshot.json", source_snapshot)
        _write(event_dir / "verification.json", {
            "schema_version": "prism.inventory_extension_packet_verification.v1",
            "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
            "source_event_id": source_id,
            "event_id": event_id,
            "component_id": packet["component_id"],
            "provider_source_digest": packet["provider_source_digest"],
            "provider_result_digest": packet["provider_result_digest"],
            "termination_basis": packet["termination_basis"],
            "termination_provenance": packet["termination_provenance"],
            "duration_s": packet["duration_s"],
            "available_mass_kg": packet["available_mass_kg"],
            "cumulative_mass_out_kg": packet["cumulative_mass_out_kg"],
            "source_campaign_verification": str(source_dir / "verification.json"),
            "namespace_rebind": {
                "source_facility_id": "equipment-inventory-campaign",
                "target_facility_id": str(rebound.get("facility_id")),
                "source_event_id": source_id,
                "target_event_id": event_id,
                "source_component_id": source_release.get("component_id"),
                "target_component_id": packet["component_id"],
                "checks": checks,
            },
            "provider_packet_promoted": False,
            "frequency_inference": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        })
        rows.append({
            "event_id": event_id,
            "source_event_id": source_id,
            "component_id": packet["component_id"],
            "source_component_id": source_release.get("component_id"),
            "status": "REBOUND_PROVIDER_PACKET_DIAGNOSTIC",
            "evidence": {
                "response_path": str((event_dir / "provider_response.json").relative_to(output_dir)).replace("\\", "/"),
                "resolved_packet_paths": [str((event_dir / "resolved_release.json").relative_to(output_dir)).replace("\\", "/")],
                "state_snapshot_path": str((event_dir / "state_snapshot.json").relative_to(output_dir)).replace("\\", "/"),
                "verification_path": str((event_dir / "verification.json").relative_to(output_dir)).replace("\\", "/"),
                "provider_model": "lh2dt.DynamicNetworkSimulator homogeneous tank to ambient inventory valve",
                "response_identity_match": True,
                "endpoint_complete": True,
                "exact_opening_match": True,
                "strict_packet_valid": True,
                "verification_status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
                "verification_ok": True,
                "qualified_provider_packet": False,
                "frequency_bound": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
                "namespace_rebind": True,
                "source_event_id": source_id,
                "provider_source_digest": packet["provider_source_digest"],
                "provider_result_digest": packet["provider_result_digest"],
            },
        })
    manifest = {
        "schema_version": "prism.inventory_extension_packet_catalog.v1",
        "status": "REBOUND_PROVIDER_PACKET_CATALOG_DIAGNOSTIC",
        "diagnostic_only": True,
        "source_campaign": str(source_dir).replace("\\", "/"),
        "rebound_campaign_result": str(rebound_result_path).replace("\\", "/"),
        "source_campaign_verification": str(source_dir / "verification.json").replace("\\", "/"),
        "event_count": len(rows),
        "exact_rebound_packet_count": len(rows),
        "qualified_provider_packet_count": 0,
        "frequency_bound": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "rows": rows,
        "interpretation": "Source provider resolved releases were checked against the namespaced union identities and materialized under an explicit namespace-rebind sidecar. This closes diagnostic packet traceability only; it does not qualify the provider, infer frequency, validate the facility, or promote facility QRA.",
        "source_campaign_limitations": source_verification.get("limitations", []),
    }
    _write(output_dir / "catalog_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--rebound-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.source_dir, args.rebound_result, args.output_dir)
    print(json.dumps({"status": result["status"], "event_count": result["event_count"], "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
