from types import SimpleNamespace

from lh2_tno.accident_scenario_catalog import (
    ACCIDENT_SCENARIO_CATALOG_SCHEMA,
    accident_scenario_catalog,
    audit_catalog_manifest,
    audit_worklist_scope_alignment,
    scenario_definition,
    scenario_families_for_release,
    scenario_families_for_request,
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


def test_release_event_family_mapping_keeps_cross_cutting_liquid_cases_explicit():
    assert scenario_families_for_release("storage_tank", "hole") == (
        "vessel_hole", "liquid_two_phase"
    )
    assert scenario_families_for_release("pipe", "two_sided_rupture") == (
        "two_sided_rupture",
    )


def test_two_sided_rupture_catalog_covers_reliquefier_events():
    definition = scenario_definition("two_sided_rupture")
    assert "reliquefier" in definition["equipment_kinds"]
    assert scenario_families_for_release("vent_stack", "maximum_relief_discharge") == (
        "vent_hole",
    )
    assert scenario_families_for_release("pipe", "inventory_over_600s") == (
        "inventory_over_600s", "liquid_two_phase"
    )


def test_consumed_provider_request_adds_vertical_handoff_family():
    request = SimpleNamespace(
        resolved_liquid_release=None,
        resolved_release_set=None,
        source_operator="integrated_transient",
        resolved_release=SimpleNamespace(
            vertical_handoff=SimpleNamespace(),
            event_kind="accidental_leak",
        ),
    )
    assert scenario_families_for_request("pipe", "hole", request) == (
        "pipe_hole", "liquid_two_phase", "vertical_handoff"
    )


def test_consumed_atmospheric_gas_packet_does_not_claim_liquid_two_phase():
    request = SimpleNamespace(
        resolved_liquid_release=None,
        resolved_release_set=None,
        source_operator="integrated_transient",
        resolved_release=SimpleNamespace(
            boundary_kind="resolved_atmospheric_gas_exit",
            vertical_handoff=None,
            compressible_plane_handoff=SimpleNamespace(),
            event_kind="accidental_leak",
        ),
    )
    assert scenario_families_for_request("pipe", "hole", request) == ("pipe_hole",)


def test_consumed_provider_request_keeps_two_sided_and_liquid_families_explicit():
    request = SimpleNamespace(
        resolved_liquid_release=SimpleNamespace(),
        resolved_release_set=SimpleNamespace(),
        source_operator="equipment_two_sided_rupture",
        resolved_release=None,
    )
    assert scenario_families_for_request("pipe", "two_sided_rupture", request) == (
        "two_sided_rupture", "liquid_two_phase"
    )


def test_worklist_scope_alignment_checks_primary_family_without_inventing_packets():
    report = audit_worklist_scope_alignment(
        {
            "work_items": [
                {
                    "id": "event-1/provider-release",
                    "event_id": "event-1",
                    "scenario_families": ["vessel_hole", "liquid_two_phase"],
                },
                {
                    "id": "event-2/provider-release",
                    "event_id": "event-2",
                    "scenario_families": ["pipe_hole"],
                },
            ]
        },
        {"event-1": {"vessel_hole"}, "event-2": {"pipe_hole"}},
    )
    assert report["status"] == "ALIGNED"
    assert report["aligned_event_count"] == 2
    assert report["provider_packet_created"] is False


def test_worklist_scope_alignment_checks_port_scoped_frequency_identity():
    worklist = {
        "work_items": [{
            "id": "event-1/provider-release",
            "event_id": "event-1",
            "scenario_families": ["vessel_hole"],
            "accident_port_ids": ["tank-accident-out"],
        }]
    }
    aligned = audit_worklist_scope_alignment(
        worklist,
        {"event-1": {"vessel_hole"}},
        {"event-1": ("tank-accident-out",)},
    )
    assert aligned["status"] == "ALIGNED"
    assert aligned["port_binding_mismatches"] == []
    mismatched = audit_worklist_scope_alignment(
        worklist,
        {"event-1": {"vessel_hole"}},
        {"event-1": ("tank-other-out",)},
    )
    assert mismatched["status"] == "PARTIAL_ALIGNMENT"
    assert mismatched["port_binding_mismatches"][0]["frequency_port_ids"] == ["tank-other-out"]
