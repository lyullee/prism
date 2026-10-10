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


def _full_scope_inputs():
    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(
        root / "examples" / "generic_lh2_full_scope_manifest.json"
    )
    plan = FrequencyPlan.model_validate_json(
        (root / "examples" / "generic_lh2_full_scope_frequency_plan.json").read_text(
            encoding="utf-8"
        )
    )
    return manifest, plan


def test_generic_manifest_frequency_scope_generates_events():
    from lh2_tno.frequency_scope import audit_frequency_scope

    _, manifest, plan = _inputs()
    result = audit_frequency_scope(manifest, plan)
    assert result["status"] == "EXECUTABLE"
    assert result["generated_event_count"] > 0
    assert result["frequency_port_binding"]["port_unbound_event_count"] == result["generated_event_count"]
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


def test_full_scope_example_covers_reviewed_equipment_profiles_and_excludes_gaps():
    from lh2_tno.frequency_scope import audit_frequency_scope

    manifest, plan = _full_scope_inputs()
    result = audit_frequency_scope(manifest, plan)

    assert result["status"] == "EXECUTABLE"
    assert result["generated_event_count"] == 24
    rows = {row["component_id"]: row for row in result["component_coverage"]}
    assert {row["status"] for row in rows.values()} == {"SELECTED", "EXCLUDED"}
    assert rows["transfer-valve-01"]["profiles"] == ["LH2_VALVE"]
    assert rows["pressure-relief-vent-01"]["profiles"] == ["TNO_RELIEF_DEVICE"]
    assert rows["liquid-transfer-pump-01"]["profiles"] == ["TNO_PUMP_STANDARD"]
    assert rows["ambient-vaporizer-01"]["profiles"] == ["TNO_HX_OUTSIDE_TUBES"]
    assert rows["reliquefier-01"]["profiles"] == ["TNO_HX_INSIDE_WEAK_SHELL"]

    profiles = {event["profile"] for event in result["events"]}
    assert profiles == {
        "LH2_VESSEL",
        "LH2_PIPE",
        "LH2_VALVE",
        "TNO_RELIEF_DEVICE",
        "TNO_PUMP_STANDARD",
        "TNO_HX_OUTSIDE_TUBES",
        "TNO_HX_INSIDE_WEAK_SHELL",
    }
    assert {event["release"]["mode"] for event in result["events"]} == {
        "hole",
        "instantaneous_inventory",
        "inventory_over_600s",
        "maximum_relief_discharge",
        "two_sided_rupture",
    }
    # Scope auditing creates initiating events only.  It does not manufacture
    # provider release ledgers or consequence requests for these events.
    assert result["promotion_policy"]["consequence_requests_are_not_created_by_this_audit"] is True


def test_full_scope_example_has_explicit_accident_ports_for_selected_equipment():
    manifest, _ = _full_scope_inputs()
    selected_components = {
        "storage-tank-01",
        "liquid-transfer-line-01",
        "transfer-valve-01",
        "pressure-relief-vent-01",
        "liquid-transfer-pump-01",
        "ambient-vaporizer-01",
        "reliquefier-01",
    }
    accident_ports = {
        port.component_id
        for port in manifest.ports
        if "accident" in port.id
    }
    assert accident_ports == selected_components
    assert "receiving-boundary-01" not in accident_ports
