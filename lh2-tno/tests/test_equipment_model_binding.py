import json
from pathlib import Path

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.equipment_model_binding import (
    audit_equipment_model_binding,
)


ROOT = Path(__file__).resolve().parents[1]


def _catalog(*, release_status="missing", schema=None):
    return {
        "schema_version": "prism.equipment_model_binding.v1",
        "facility_neutral": True,
        "bindings": [{
            "component_kind": "storage_tank",
            "model_package": "test.model",
            "model_class": "Tank",
            "model_revision": "test-1",
            "state_export_status": "supported",
            "accident_release_export_status": release_status,
            "termination_ledger_status": "provider_termination_and_mass" if release_status == "supported" else "normal_flow_only",
            "provider_export_schema": schema,
        }],
    }


def test_model_binding_records_state_only_without_accident_claim():
    manifest = EquipmentManifest.from_json(ROOT / "examples" / "equipment_manifest.json")
    # The shipped manifest contains more than one kind; use a one-component fixture.
    manifest = manifest.model_copy(update={"components": (manifest.components[0],)})
    report = audit_equipment_model_binding(manifest, _catalog())
    assert report["status"] == "STATE_ONLY_BOUND"
    assert report["component_rows"][0]["status"] == "STATE_ONLY_BOUND"
    assert report["accident_release_claim"] is False
    assert report["frequency_inference_performed"] is False


def test_model_binding_requires_every_manifest_kind(tmp_path):
    manifest = EquipmentManifest.from_json(ROOT / "examples" / "equipment_manifest.json")
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8")
    report = audit_equipment_model_binding(manifest, path)
    assert report["status"] == "PARTIAL_MODEL_BINDING"
    assert any("no model binding" in reason for reason in report["blocking_reasons"])


def test_model_binding_release_interface_requires_schema():
    manifest = EquipmentManifest.from_json(ROOT / "examples" / "equipment_manifest.json")
    manifest = manifest.model_copy(update={"components": (manifest.components[0],)})
    report = audit_equipment_model_binding(
        manifest,
        _catalog(release_status="supported", schema=None),
    )
    assert report["status"] == "STATE_ONLY_BOUND"
    assert any("requires prism.resolved_release.v1" in reason for reason in report["blocking_reasons"])
