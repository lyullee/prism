import json

from lh2_tno.provider_termination_evidence_catalog import (
    build_provider_termination_evidence_catalog,
)


def test_catalog_binds_storage_sidecar_and_inventory_response(tmp_path):
    storage = tmp_path / "storage"
    event_dir = storage / "events" / "000_storage"
    event_dir.mkdir(parents=True)
    packet = {
        "event_id": "storage/event",
        "component_id": "storage-tank-01",
        "provider_result_digest": "storage-digest",
    }
    verification = {
        "provider_result_digest": "storage-digest",
        "provider_run_meta": {
            "termination_basis": "inventory_depletion_positive_threshold",
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "threshold_mass_kg": 7.1,
            "remaining_mass_kg": 7.0,
            "max_abs_mass_residual_kg": 0.0,
        },
    }
    (event_dir / "resolved_release.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )
    (event_dir / "verification.json").write_text(
        json.dumps(verification), encoding="utf-8"
    )
    inventory_id = "equipment-inventory-campaign/terminal_pipe_asset/AREA_1%"
    report = build_provider_termination_evidence_catalog(
        storage_catalog_dir=storage,
        inventory_provider_responses={inventory_id: {
            "data": {
                "available_mass_kg": 4.0,
                "cumulative_mass_out_kg": 1.0,
                "remaining_inventory_kg": 3.0,
                "depletion_threshold_kg": 3.5,
                "max_total_mass_residual_kg": 0.0,
            }
        }},
        inventory_resolved_releases={inventory_id: {
            "provider_result_digest": "inventory-digest",
            "component_id": "terminal_pipe",
            "duration_s": 2.0,
            "termination_provenance": "positive threshold",
        }},
    )
    assert report["status"] == "EVIDENCE_CATALOG_READY"
    assert report["row_count"] == 2
    rows = {row["event_id"]: row for row in report["rows"]}
    assert rows["storage/event"]["provider_result_digest"] == "storage-digest"
    assert rows[
        "generic-lh2-full-scope-example/inventory-depletion/inventory-depletion/terminal_pipe_asset/AREA_1%"
    ]["provider_result_digest"] == "inventory-digest"
    assert report["provider_qualification_claim"] is False
    assert report["facility_qra_claim"] is False
