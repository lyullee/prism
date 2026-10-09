from lh2_tno.accident_scenario_catalog import (
    ACCIDENT_SCENARIO_CATALOG_SCHEMA,
    accident_scenario_catalog,
    audit_catalog_manifest,
    scenario_definition,
)


def test_catalog_declares_all_outdoor_major_families_with_packet_contracts():
    rows = accident_scenario_catalog()
    assert len(rows) == 12
    assert {row["family"] for row in rows} == {
        "vessel_hole", "pipe_hole", "valve_hole", "vent_hole", "pump_hole",
        "vaporizer_hole", "reliquefier_hole", "liquid_two_phase",
        "inventory_depletion", "inventory_over_600s", "two_sided_rupture",
        "vertical_handoff",
    }
    for row in rows:
        assert row["equipment_kinds"]
        assert row["release_modes"]
        assert row["provider_schemas"]
        assert row["termination_bases"]
        assert row["required_source_operators"]
        assert row["consequence_path"]
        assert row["uncomputed_default_reason"]


def test_catalog_returns_deep_copies_and_rejects_unknown_family():
    first = scenario_definition("two_sided_rupture")
    first["release_modes"] = ("invalid",)
    assert "invalid" not in scenario_definition("two_sided_rupture")["release_modes"]
    try:
        accident_scenario_catalog(("not_a_family",))
    except ValueError as error:
        assert "unknown accident scenario families" in str(error)
    else:
        raise AssertionError("unknown family must fail closed")


def test_catalog_manifest_audit_maps_equipment_to_scenarios():
    result = audit_catalog_manifest((row for row in [
        {"id": "tank-01", "kind": "storage_tank"},
        {"id": "pipe-01", "kind": "pipe"},
        {"id": "vent-01", "kind": "vent_stack"},
    ]), ("vessel_hole", "pipe_hole", "vertical_handoff"))
    assert result["schema"] == ACCIDENT_SCENARIO_CATALOG_SCHEMA
    rows = {row["family"]: row for row in result["rows"]}
    assert rows["vessel_hole"]["applicable_component_ids"] == ["tank-01"]
    assert rows["pipe_hole"]["applicable_component_ids"] == ["pipe-01"]
    assert rows["vertical_handoff"]["applicable_component_ids"] == ["pipe-01", "vent-01"]
