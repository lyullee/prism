"""Bind audited equipment-state snapshots into a native LH2 campaign.

The native packet campaign already consumes strict provider release packets,
but its historical consequence requests did not carry the state snapshot that
was checked beside each packet.  This compiler joins the exact provider result
digest(s) in each request to the packet-directory verification record and
embeds the canonical state snapshot in the request.  It is deliberately
fail-closed: a missing digest, mismatched component, failed provider echo, or
ambiguous packet match stops compilation instead of guessing a state.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.state_snapshot import EquipmentStateSnapshot  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _packet_result_digests(request: dict[str, Any]) -> tuple[str, ...]:
    releases: list[dict[str, Any]] = []
    for key in ("resolved_release", "resolved_liquid_release"):
        value = request.get(key)
        if isinstance(value, dict):
            releases.append(value)
    release_set = request.get("resolved_release_set")
    if isinstance(release_set, dict):
        values = release_set.get("releases")
        if not isinstance(values, list):
            raise ValueError("resolved_release_set.releases must be an array")
        releases.extend(value for value in values if isinstance(value, dict))
    digests = tuple(
        str(value["provider_result_digest"])
        for value in releases
        if isinstance(value.get("provider_result_digest"), str)
    )
    if not digests or len(digests) != len(releases):
        raise ValueError("every resolved release must carry provider_result_digest")
    return digests


def _echoes(verification: dict[str, Any], digest: str) -> tuple[str, ...]:
    handoff = verification.get("state_snapshot_handoff")
    if not isinstance(handoff, dict):
        raise ValueError("verification lacks state_snapshot_handoff")
    if handoff.get("digest") != digest or handoff.get("digest_match") is not True:
        raise ValueError("state snapshot handoff digest is not verified")
    raw = handoff.get("provider_echo_digest")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and raw and all(isinstance(item, str) for item in raw):
        return tuple(raw)
    raise ValueError("verification provider_echo_digest must be a digest or nonempty digest array")


def _build_index(packet_root: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    events_root = packet_root / "events"
    paths = sorted(events_root.glob("*/verification.json"))
    if not paths:
        raise ValueError(f"no event verification records found below {events_root}")
    for verification_path in paths:
        verification = _load(verification_path)
        raw_snapshot = verification.get("state_snapshot")
        if not isinstance(raw_snapshot, dict):
            raise ValueError(f"{verification_path} lacks state_snapshot")
        snapshot = EquipmentStateSnapshot.from_mapping(raw_snapshot)
        digest = snapshot.digest()
        handoff = verification.get("state_snapshot_handoff")
        if not isinstance(handoff, dict) or handoff.get("digest") != digest:
            raise ValueError(f"{verification_path} state snapshot digest does not close")
        keys: set[str] = set()
        direct = verification.get("provider_result_digest")
        if isinstance(direct, str):
            keys.add(direct)
        for name in ("resolved_release.json", "resolved_release_set.json"):
            sibling = verification_path.parent / name
            if not sibling.exists():
                continue
            payload = _load(sibling)
            if name == "resolved_release_set.json":
                releases = payload.get("releases")
                if not isinstance(releases, list):
                    raise ValueError(f"{sibling} releases must be an array")
                keys.update(
                    str(item["provider_result_digest"])
                    for item in releases
                    if isinstance(item, dict) and isinstance(item.get("provider_result_digest"), str)
                )
            elif isinstance(payload.get("provider_result_digest"), str):
                keys.add(str(payload["provider_result_digest"]))
        if not keys:
            raise ValueError(f"{verification_path} has no provider result digest key")
        echoes = _echoes(verification, digest)
        record = {
            "verification_path": str(verification_path),
            "snapshot": snapshot.to_mapping(),
            "snapshot_digest": digest,
            "provider_echo_digests": list(echoes),
            "component_id": snapshot.component_id,
        }
        for key in sorted(keys):
            index[key].append(record)
    return dict(index)


def bind(campaign: dict[str, Any], packet_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    output = copy.deepcopy(campaign)
    routes = output.get("event_routes")
    if not isinstance(routes, list):
        raise ValueError("campaign event_routes must be an array")
    index = _build_index(packet_root)
    rows: list[dict[str, Any]] = []
    for route in routes:
        if not isinstance(route, dict) or not isinstance(route.get("event_id"), str):
            raise ValueError("campaign route must contain event_id")
        event_id = route["event_id"]
        branches = route.get("branches")
        if not isinstance(branches, list):
            raise ValueError(f"route branches must be an array: {event_id}")
        request_branches = [
            branch for branch in branches
            if isinstance(branch, dict) and isinstance(branch.get("request"), dict)
        ]
        if len(request_branches) != 1:
            raise ValueError(f"state binding requires exactly one request branch: {event_id}")
        request = request_branches[0]["request"]
        digests = _packet_result_digests(request)
        candidates = [record for digest in digests for record in index.get(digest, [])]
        unique: dict[tuple[str, str], dict[str, Any]] = {
            (record["verification_path"], record["snapshot_digest"]): record
            for record in candidates
        }
        if not unique:
            raise ValueError(f"no verified packet state matches provider result digest(s): {event_id}")
        if len({record["snapshot_digest"] for record in unique.values()}) != 1:
            raise ValueError(f"provider packets disagree on equipment state snapshot: {event_id}")
        record = next(iter(unique.values()))
        if record["component_id"] != request.get("component_id"):
            raise ValueError(f"state snapshot component mismatch: {event_id}")
        echoes = tuple(record["provider_echo_digests"])
        if len(echoes) != len(digests):
            raise ValueError(
                f"provider echo count does not match release endpoint count: {event_id} "
                f"({len(echoes)} != {len(digests)})"
            )
        if any(value != record["snapshot_digest"] for value in echoes):
            raise ValueError(f"provider state echo disagrees with snapshot: {event_id}")
        request["state_snapshot"] = record["snapshot"]
        request["state_snapshot_digest"] = record["snapshot_digest"]
        request["provider_state_snapshot_digest"] = record["snapshot_digest"]
        if len(echoes) > 1:
            request["provider_state_snapshot_digests"] = list(echoes)
        else:
            request.pop("provider_state_snapshot_digests", None)
        rows.append({
            "source": "diagnostic_record",
            "record": record["verification_path"],
            "event_id": event_id,
            "component_id": request["component_id"],
            # Keep the historical scalar for one-endpoint packets.  A
            # two-sided packet has no single provider result digest, so its
            # endpoint list remains authoritative.
            "provider_result_digest": digests[0] if len(digests) == 1 else None,
            "provider_result_digests": list(digests),
            "state_snapshot_digest": record["snapshot_digest"],
            "provider_state_snapshot_digests": list(echoes),
            "verification_path": record["verification_path"],
            "snapshot_present": True,
            "snapshot_schema_version": record["snapshot"]["schema_version"],
            "declared_digest": record["snapshot_digest"],
            "computed_digest": record["snapshot_digest"],
            "provider_echo_digest": echoes[0] if len(echoes) == 1 else list(echoes),
            "provider_source_digest": None,
            "digest_match": True,
            "status": "BOUND_AND_ECHOED",
            "reason": "canonical snapshot was validated at the request boundary and echoed by the provider",
        })
    validated = RiskCampaign.model_validate_json(json.dumps(output, ensure_ascii=False, allow_nan=False))
    result = validated.model_dump(mode="json")
    audit = {
        "schema_version": "prism.state_snapshot_binding_audit.v1",
        "status": "STATE_SNAPSHOT_BOUND_AND_ECHOED",
        "policy": {
            "canonical_schema": "prism.equipment_state_snapshot.v1",
            "digest_only_is_binding": False,
            "provider_echo_required": True,
            "diagnostic_only": True,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
        "record_count": len(rows),
        "bound_count": len(rows),
        "echo_match_count": len(rows),
        "digest_mismatch_count": 0,
        "declared_digest_only_count": 0,
        "unbound_count": 0,
        "snapshot_requested_no_echo_count": 0,
        "status_counts": {"BOUND_AND_ECHOED": len(rows)},
        "event_count": len(rows),
        "rows": rows,
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "provider_packet_promoted": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Canonical equipment state snapshots and provider echoes are carried into the "
            "native consequence requests. This proves request-level state identity; it does "
            "not qualify the provider packet or create an independent physical validation."
        ),
    }
    return result, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        campaign = _load(args.campaign)
        rebound, audit = bind(campaign, args.packet_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"native campaign state binding input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rebound, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "event_count": audit["event_count"], "output": str(args.output), "audit_output": str(args.audit_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
