import json
from pathlib import Path

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan
from lh2_tno.provider_worklist import build_provider_release_worklist


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


def test_full_scope_provider_worklist_maps_every_frequency_event_without_fabricating_packets():
    manifest, plan = _full_scope_inputs()
    result = build_provider_release_worklist(manifest, plan)

    assert result["status"] == "READY_FOR_PROVIDER_PACKETS"
    assert result["generated_event_count"] == 24
    assert result["provider_packet_count"] == 0
    assert result["status_counts"] == {"UNCOMPUTED_PROVIDER_PACKET": 24}
    rows = result["work_items"]
    assert all(row["accident_port_ids"] for row in rows)
    assert all(row["status"] == "UNCOMPUTED_PROVIDER_PACKET" for row in rows)
    assert all(row["required_packet_fields"] for row in rows)
    assert {row["release_mode"] for row in rows} == {
        "hole",
        "instantaneous_inventory",
        "inventory_over_600s",
        "maximum_relief_discharge",
        "two_sided_rupture",
    }

    relief = [row for row in rows if row["release_mode"] == "maximum_relief_discharge"]
    assert relief and relief[0]["provider_event_kind"] == "emergency_relief"
    assert "failure_opening_diameter_m" not in relief[0]["required_packet_fields"]

    inventory = [row for row in rows if row["release_mode"] == "inventory_over_600s"]
    assert inventory and inventory[0]["required_duration_s"] == 600.0


def test_provider_worklist_does_not_replace_a_missing_accident_port_with_normal_port():
    manifest, plan = _full_scope_inputs()
    raw = manifest.model_dump(mode="json")
    raw["ports"] = [
        port for port in raw["ports"] if port["id"] != "line-accident-out"
    ]
    incomplete = EquipmentManifest.model_validate_json(json.dumps(raw))
    result = build_provider_release_worklist(incomplete, plan)

    assert result["status"] == "PARTIAL_MISSING_ACCIDENT_PORT"
    missing = [
        row for row in result["work_items"]
        if row["component_id"] == "liquid-transfer-line-01"
    ]
    assert missing
    assert all(row["status"] == "UNCOMPUTED_NO_ACCIDENT_PORT" for row in missing)
    assert all(not row["accident_port_ids"] for row in missing)


def test_provider_worklist_surfaces_state_only_model_binding_without_promoting_packets():
    manifest, plan = _full_scope_inputs()
    result = build_provider_release_worklist(
        manifest,
        plan,
        model_binding=Path(__file__).parents[1] / "examples" / "generic_lh2_model_binding.json",
    )

    assert result["model_binding_status"] == "STATE_ONLY_BOUND"
    assert result["model_binding_accident_release_supported_component_count"] == 0
    assert result["provider_packet_count"] == 0
    assert all(row["status"] == "UNCOMPUTED_PROVIDER_PACKET" for row in result["work_items"])
    assert all(row["model_binding_status"] == "STATE_ONLY_BOUND" for row in result["work_items"])
    assert all(row["model_accident_release_export_status"] == "missing" for row in result["work_items"])
    assert all(
        "no accident-release provider export" in reason
        for row in result["work_items"]
        for reason in row["blocking_reasons"]
    )
