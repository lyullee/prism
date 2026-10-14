"""Literature frequency provenance is explicit and fail-closed."""
from copy import deepcopy
import json
from pathlib import Path

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan, catalogue
from lh2_tno.frequency_provenance import build_frequency_provenance_report


ROOT = Path(__file__).parents[1]


def inputs():
    manifest = EquipmentManifest.from_json(ROOT / "examples/generic_lh2_full_scope_manifest.json")
    plan = FrequencyPlan.model_validate_json(
        (ROOT / "examples/generic_lh2_full_scope_frequency_plan.json").read_text(encoding="utf-8")
    )
    return manifest, plan


def test_report_traces_catalogue_hashes_and_generated_events():
    manifest, plan = inputs()
    report = build_frequency_provenance_report(manifest, plan)
    assert report["status"] == "PASS_WITH_SCOPE_LIMITATIONS"
    assert len(report["profile_provenance"]) == 7
    assert len(report["generated_events"]) == 24
    assert all(row["source_file_hash_registered"] for row in report["profile_provenance"])
    assert all(event["catalogue_digest"] == report["catalogue"]["digest"] for event in report["generated_events"])
    assert report["policy"]["field_frequency_collection_used"] is False
    assert report["policy"]["sensor_frequency_learning_used"] is False
    assert all(event["port_ids"] for event in report["generated_events"])
    assert all(
        event["port_ids"] == ["reliquefier-accident-out-1", "reliquefier-accident-out-2"]
        for event in report["generated_events"]
        if event["asset_id"] == "reliquefier" and event["loc"] in {"G4", "G5"}
    )
    assert all(
        event["port_ids"] == ["reliquefier-accident-out-1"]
        for event in report["generated_events"]
        if event["asset_id"] == "reliquefier" and event["loc"] == "G6"
    )


def test_report_fails_when_profile_source_hash_is_not_registered():
    manifest, plan = inputs()
    tampered = deepcopy(catalogue())
    tampered["profiles"]["LH2_VESSEL"]["source_sha256"] = "f" * 64
    report = build_frequency_provenance_report(manifest, plan, catalogue_data=tampered)
    assert report["status"] == "FAILED_PROVENANCE_INTEGRITY"
    assert any("source_sha256" in reason for reason in report["blocking_reasons"])


def test_report_traces_attached_external_catalogue_without_packaged_digest_mismatch():
    from lh2_tno.legacy_frequency_bridge import attach_precomputed_events, bridge_legacy_scenarios

    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(root / "examples/generic_lh2_full_scope_manifest.json")
    facility_plan = FrequencyPlan.model_validate_json(
        (root / "examples/generic_lh2_full_scope_frequency_plan.json").read_text(encoding="utf-8")
    )
    source_sha = "a" * 64
    events, _ = bridge_legacy_scenarios(
        [{
            "scenario_id": "external-storage-hole",
            "tag": "storage-tank-01",
            "primitive": "VESSEL",
            "service": "LH2",
            "bin_label": "1%",
            "hole_diameter_m": 0.01,
            "frequency_per_year": 2.5e-4,
            "release_kind": "CONTINUOUS",
            "release_path": "DIRECT",
            "physics_route": "SLABX_LH2",
        }],
        {"external-storage-hole": "storage-tank-01"},
        source_sha256=source_sha,
    )
    attached = attach_precomputed_events(
        facility_plan,
        events,
        provenance="external legacy event catalogue; source digest pinned",
    )

    report = build_frequency_provenance_report(manifest, attached)

    assert report["status"] == "PASS_WITH_SCOPE_LIMITATIONS"
    assert report["frequency_plan"]["event_generation_mode"] == "external_precomputed"
    assert report["catalogue"]["applied_to_event_rows"] is False
    assert report["external_event_catalogue"]["exact_replay_checked"] is True
    assert report["external_event_catalogue"]["frequency_arithmetic_owner"] == (
        "external_precomputed_event_generator"
    )
    assert report["policy"]["external_frequency_override_used"] is True
    assert report["policy"]["field_frequency_collection_used"] is False
    generated_check = next(
        check for check in report["checks"] if check["id"] == "generated_event_catalogue_digest"
    )
    assert generated_check["comparison_scope"] == "attached_external_event_catalogue"
