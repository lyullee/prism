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
