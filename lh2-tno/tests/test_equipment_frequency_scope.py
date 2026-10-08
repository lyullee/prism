import json
from pathlib import Path

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan


def _inputs():
    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(root / "examples" / "equipment_manifest.json")
    plan = FrequencyPlan.model_validate_json(
        (root / "examples" / "equipment_frequency_plan.json").read_text(encoding="utf-8")
    )
    return root, manifest, plan


def test_generic_manifest_frequency_scope_generates_events():
    from lh2_tno.frequency_scope import audit_frequency_scope

    _, manifest, plan = _inputs()
    result = audit_frequency_scope(manifest, plan)
    assert result["status"] == "EXECUTABLE"
    assert result["generated_event_count"] > 0
    assert {row["status"] for row in result["component_coverage"]} == {"SELECTED", "EXCLUDED"}
    assert result["physical_validation_claim"] is False


def test_frequency_scope_does_not_infer_unmapped_component(tmp_path):
    from lh2_tno.frequency_scope import audit_frequency_scope

    _, manifest, plan = _inputs()
    raw = plan.model_dump(mode="json")
    raw["excluded_model_components"].pop("liquid-demand-boundary")
    incomplete = FrequencyPlan.model_validate_json(json.dumps(raw))
    result = audit_frequency_scope(manifest, incomplete)
    assert result["status"] == "PARTIAL"
    assert "UNCOMPUTED" in {row["status"] for row in result["component_coverage"]}
    assert any("no selected frequency asset" in reason for reason in result["blocking_reasons"])


def test_partial_manifest_blocks_frequency_event_generation():
    from lh2_tno.frequency_scope import audit_frequency_scope

    _, manifest, plan = _inputs()
    raw = manifest.model_dump(mode="json")
    raw["components"][0].pop("property_basis")
    partial = EquipmentManifest.model_validate_json(json.dumps(raw))
    result = audit_frequency_scope(partial, plan)
    assert result["status"] == "PARTIAL"
    assert result["generated_event_count"] == 0
    assert "EXECUTABLE" in result["blocking_reasons"][0]
