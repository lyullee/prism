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


def test_catalog_reads_native_isolation_and_two_sided_set_artifacts(tmp_path):
    storage = tmp_path / "native"
    isolation = storage / "events" / "001_line"
    two_sided = storage / "events" / "002_set"
    isolation.mkdir(parents=True)
    two_sided.mkdir(parents=True)
    (isolation / "resolved_release.json").write_text(json.dumps({
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": "native/line",
        "component_id": "line-1",
        "provider_result_digest": "line-result",
    }), encoding="utf-8")
    (isolation / "verification.json").write_text(json.dumps({
        "provider_result_digest": "line-result",
        "termination_basis": "reviewed_isolation_success",
        "isolation_success": True,
        "isolation_time_s": 0.1,
        "post_isolation_observation_s": 0.2,
        "physical_validation_claim": False,
        "mass_residual_kg": 0.0,
    }), encoding="utf-8")
    (isolation / "provider_response.json").write_text(json.dumps({
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {
            "event_id": "native/line",
            "component_id": "line-1",
            "termination_basis": "reviewed_isolation_success",
            "termination_provenance": "provider outlet closed",
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "duration_s": 0.3,
            "provider_meta": {"isolation_success": True},
        },
    }), encoding="utf-8")
    (two_sided / "resolved_release_set.json").write_text(json.dumps({
        "provider_export_schema": "prism.resolved_release_set.v1",
        "event_id": "native/set",
        "component_id": "reliquefier-1",
        "rupture_mode": "two_sided_rupture",
        "provider_result_digest": "set-result",
        "inventory_provenance": "shared provider inventory",
        "releases": [
            {"provider_result_digest": "left", "available_mass_kg": 10.0, "cumulative_mass_out_kg": 3.0, "duration_s": 0.5},
            {"provider_result_digest": "right", "available_mass_kg": 10.0, "cumulative_mass_out_kg": 3.0, "duration_s": 0.5},
        ],
    }), encoding="utf-8")
    (two_sided / "verification.json").write_text(json.dumps({
        "strict_packet_endpoint_count": 2,
        "strict_packet_mass_residual_kg": 0.0,
        "physical_validation_claim": False,
    }), encoding="utf-8")

    report = build_provider_termination_evidence_catalog(storage_catalog_dir=storage)
    assert report["status"] == "EVIDENCE_CATALOG_READY"
    assert report["row_count"] == 2
    rows = {row["event_id"]: row for row in report["rows"]}
    assert rows["native/line"]["termination_basis"] == "reviewed_isolation_success"
    assert rows["native/set"]["provider_result_digests"] == ["left", "right"]


def test_catalog_accepts_multiple_storage_directories(tmp_path):
    first = tmp_path / "first" / "events" / "one"
    second = tmp_path / "second" / "events" / "two"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    for event_dir, event_id in ((first, "first/event"), (second, "second/event")):
        (event_dir / "resolved_release.json").write_text(json.dumps({
            "event_id": event_id,
            "component_id": "pipe-1",
            "provider_result_digest": f"{event_id}-digest",
        }), encoding="utf-8")
        (event_dir / "verification.json").write_text(json.dumps({
            "provider_result_digest": f"{event_id}-digest",
            "provider_run_meta": {
                "termination_basis": "inventory_depletion_positive_threshold",
                "available_mass_kg": 1.0,
                "cumulative_mass_out_kg": 0.5,
                "threshold_mass_kg": 0.1,
                "remaining_mass_kg": 0.5,
                "max_abs_mass_residual_kg": 0.0,
            },
        }), encoding="utf-8")
    report = build_provider_termination_evidence_catalog(
        storage_catalog_dir=first.parent.parent,
        additional_storage_catalog_dirs=[second.parent.parent],
    )
    assert report["status"] == "EVIDENCE_CATALOG_READY"
    assert report["event_count"] == 2


def test_catalog_preserves_distinct_provider_replays_for_one_event(tmp_path):
    first = tmp_path / "first" / "events" / "one"
    second = tmp_path / "second" / "events" / "two"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    for event_dir, digest in ((first, "old-digest"), (second, "new-digest")):
        (event_dir / "resolved_release.json").write_text(json.dumps({
            "event_id": "same/event",
            "component_id": "tank-1",
            "provider_result_digest": digest,
        }), encoding="utf-8")
        (event_dir / "verification.json").write_text(json.dumps({
            "provider_result_digest": digest,
            "provider_run_meta": {
                "termination_basis": "inventory_depletion_positive_threshold",
                "available_mass_kg": 1.0,
                "cumulative_mass_out_kg": 0.5,
                "threshold_mass_kg": 0.1,
                "remaining_mass_kg": 0.5,
                "max_abs_mass_residual_kg": 0.0,
            },
        }), encoding="utf-8")
    report = build_provider_termination_evidence_catalog(
        storage_catalog_dir=first.parent.parent,
        additional_storage_catalog_dirs=[second.parent.parent],
    )
    assert report["status"] == "EVIDENCE_CATALOG_READY"
    assert report["row_count"] == 2
    assert report["event_count"] == 1
    assert report["duplicate_event_ids"] == []
    assert report["variant_event_ids"] == ["same/event"]


def test_catalog_accepts_single_direct_provider_bundle(tmp_path):
    packet = {
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": "direct/event",
        "component_id": "tank-1",
        "provider_result_digest": "direct-digest",
    }
    verification = {
        "provider_result_digest": "direct-digest",
        "termination_basis": "reviewed_isolation_success",
        "isolation_success": True,
        "isolation_time_s": 0.1,
        "post_isolation_observation_s": 0.2,
        "mass_residual_kg": 0.0,
    }
    (tmp_path / "resolved_release.json").write_text(json.dumps(packet), encoding="utf-8")
    (tmp_path / "verification.json").write_text(json.dumps(verification), encoding="utf-8")
    (tmp_path / "provider_response.json").write_text(json.dumps({
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {
            "event_id": "direct/event",
            "component_id": "tank-1",
            "termination_basis": "reviewed_isolation_success",
            "termination_provenance": "direct replay",
            "available_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.1,
            "duration_s": 0.3,
            "provider_meta": {"isolation_success": True},
        },
    }), encoding="utf-8")
    report = build_provider_termination_evidence_catalog(storage_catalog_dir=tmp_path)
    assert report["status"] == "EVIDENCE_CATALOG_READY"
    assert report["event_count"] == 1
    assert report["rows"][0]["event_id"] == "direct/event"
