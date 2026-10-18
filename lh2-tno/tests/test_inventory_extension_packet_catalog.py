from __future__ import annotations

import json
from pathlib import Path

from scripts.materialize_inventory_extension_packet_catalog import materialize


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_inventory_extension_packets_are_materialized_with_explicit_rebind(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    releases: dict[str, dict] = {}
    responses: dict[str, dict] = {}
    snapshots: dict[str, dict] = {}
    cases: list[dict] = []
    for index, area in enumerate(("0.01", "0.1", "1", "10", "100")):
        source_id = f"equipment-inventory-campaign/terminal_pipe_asset/AREA_{area}%"
        event_id = f"facility/inventory-depletion/terminal_pipe_asset/AREA_{area}%"
        result_digest = f"{index + 1:064x}"
        source_digest = f"{index + 101:064x}"
        duration = 1.0 + index
        available = 10.0 + index
        released = 0.1 + index
        provenance = f"threshold {index}"
        releases[source_id] = {
            "provider_export_schema": "prism.resolved_release.v1",
            "event_id": source_id,
            "component_id": "terminal_pipe",
            "port_id": "terminal_pipe.out",
            "provider_source_digest": source_digest,
            "provider_result_digest": result_digest,
            "duration_s": duration,
            "available_mass_kg": available,
            "cumulative_mass_out_kg": released,
            "termination_basis": "inventory_depletion",
            "termination_provenance": provenance,
        }
        responses[source_id] = {"ok": True, "data": {}}
        snapshots[source_id] = {"schema_version": "prism.equipment_state_snapshot.v1"}
        cases.append({
            "event_id": event_id,
            "release_branch_id": "provider-inventory-depletion",
            "provider_packet_identity": {
                "component_id": "inventory-depletion-pipe-01",
                "provider_source_digests": [source_digest],
                "provider_result_digests": [result_digest],
                "duration_s": [duration],
                "available_mass_kg": [available],
                "cumulative_mass_out_kg": [released],
                "termination_bases": ["inventory_depletion"],
                "termination_provenances": [provenance],
            },
        })
    _write(source / "resolved_releases.json", releases)
    _write(source / "provider_responses.json", responses)
    _write(source / "state_snapshots.json", snapshots)
    _write(source / "verification.json", {"limitations": ["synthetic"]})
    rebound = tmp_path / "rebound.json"
    _write(rebound, {"facility_id": "facility", "cases": cases})

    output = tmp_path / "catalog"
    manifest = materialize(source, rebound, output)

    assert manifest["event_count"] == 5
    assert manifest["exact_rebound_packet_count"] == 5
    packet = json.loads(next((output / "events").glob("*/resolved_release.json")).read_text())
    assert packet["event_id"].startswith("facility/inventory-depletion/")
    assert packet["component_id"] == "inventory-depletion-pipe-01"
    assert manifest["rows"][0]["evidence"]["namespace_rebind"] is True
