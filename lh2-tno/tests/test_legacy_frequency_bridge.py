import pytest
import json

from lh2_tno.legacy_frequency_bridge import (
    attach_precomputed_events,
    bridge_digest,
    bridge_legacy_scenarios,
)
from lh2_tno.frequency import FrequencyPlan, generate_events


SOURCE_SHA = "a" * 64


def _row(scenario_id="S-001", *, release_kind="CONTINUOUS", tag="TK-101"):
    return {
        "scenario_id": scenario_id,
        "tag": tag,
        "primitive": "VESSEL",
        "service": "LH2",
        "bin_label": "1%",
        "hole_diameter_m": 0.01,
        "frequency_per_year": 2.5e-4,
        "frequency_fuel_proxy": "LH2",
        "release_kind": release_kind,
        "release_path": "DIRECT",
        "physics_route": "SLABX_LH2",
        "grade": "PUBLISHED_UNVALIDATED",
        "available_mass_kg": 10.0,
        "isolation_time_s": 30.0,
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
    }


def test_bridge_preserves_legacy_rate_and_does_not_apply_count_again():
    events, audit = bridge_legacy_scenarios(
        [_row()], {"S-001": "tank"}, source_sha256=SOURCE_SHA,
        basis={"S-001": "LH2_LITERATURE"},
    )
    assert len(events) == 1
    event = events[0]
    assert event.annual_frequency_per_year == pytest.approx(2.5e-4)
    assert event.exposure_multiplier == 1.0
    assert event.release.mode == "hole"
    assert event.release.hole_diameter_m == pytest.approx(0.01)
    assert audit["frequency_inference_performed"] is False
    assert audit["rows"][0]["legacy_release_path"] == "DIRECT"
    assert len(bridge_digest(audit)) == 64


def test_bridge_maps_instantaneous_legacy_release_without_making_a_hole():
    events, audit = bridge_legacy_scenarios(
        [_row("S-002", release_kind="INSTANTANEOUS")], {"S-002": "tank"},
        source_sha256=SOURCE_SHA,
    )
    assert events[0].release.mode == "instantaneous_inventory"
    assert events[0].release.hole_diameter_m is None
    assert audit["release_mode_counts"] == {"instantaneous_inventory": 1}


def test_bridge_requires_exact_component_mapping():
    with pytest.raises(ValueError, match="explicit nonempty legacy scenario component_map"):
        bridge_legacy_scenarios([_row()], {}, source_sha256=SOURCE_SHA)


def test_bridge_rejects_unknown_facility_component():
    from lh2_tno.contracts import Facility

    facility = Facility.model_validate_json(
        '{"id":"f","configuration_origin":"synthetic","environment":"outdoor",'
        '"components":[{"id":"tank","kind":"storage_tank","position_enu_m":[0,0,0],'
        '"property_basis":{"fluid":"Hydrogen","backend":"CoolProp-HEOS",'
        '"energy_reference":"CoolProp-HEOS:Hydrogen:native"},"parameters_si":{"volume_m3":1}}],'
        '"ports":[],"edges":[],"receptors":[]}'
    )
    with pytest.raises(ValueError, match="unknown facility component"):
        bridge_legacy_scenarios(
            [_row()], {"S-001": "missing"}, source_sha256=SOURCE_SHA, facility=facility
        )


def test_bridge_rejects_nonhex_source_digest():
    with pytest.raises(ValueError, match="64-character hexadecimal"):
        bridge_legacy_scenarios([_row()], {"S-001": "tank"}, source_sha256="bad")


def test_bridge_event_can_be_consumed_by_frequency_binding_contract():
    # This exercises the shared event contract without asserting that a
    # legacy scenario alone creates a provider packet or a facility QRA.
    events, _ = bridge_legacy_scenarios(
        [_row()], {"S-001": "storage"}, source_sha256=SOURCE_SHA,
    )
    assert events[0].model_component_id == "storage"
    assert events[0].id.startswith("legacy-tno/storage/")
    # A real consequence request/provider must still be supplied before
    # bind_event can be called; the bridge deliberately does not fabricate it.
    assert events[0].physical_validation_claim is False


def test_research_pipeline_exposes_legacy_event_handoff():
    from pathlib import Path
    from lh2_tno.contracts import Facility
    from lh2_tno.pipeline import ResearchPipeline

    root = Path(__file__).parents[1]
    facility = Facility.model_validate_json(
        (root / "examples/lh2_frequency_facility.json").read_text(encoding="utf-8")
    )
    events, audit = ResearchPipeline(facility, object()).legacy_frequency_events(
        [_row()], {"S-001": "tank"}, source_sha256=SOURCE_SHA,
    )
    assert len(events) == 1
    assert audit["mapped_component_ids"] == ["tank"]


def test_attached_catalogue_uses_external_rows_in_common_frequency_boundary():
    from pathlib import Path
    from lh2_tno.contracts import Facility

    root = Path(__file__).parents[1]
    facility = Facility.model_validate_json(
        (root / "examples/lh2_frequency_facility.json").read_text(encoding="utf-8")
    )
    plan = FrequencyPlan.model_validate_json(
        (root / "examples/lh2_frequency_plan.json").read_text(encoding="utf-8")
    )
    events, _ = bridge_legacy_scenarios(
        [_row()], {"S-001": "tank"}, source_sha256=SOURCE_SHA,
    )
    attached = attach_precomputed_events(
        plan, events, provenance="legacy bridge test; source digest pinned"
    )
    generated = generate_events(facility, attached)
    assert generated == events
    assert attached.precomputed_events_provenance.startswith("legacy bridge test")


def test_attached_external_catalogue_cannot_hide_unselected_or_excluded_component():
    from pathlib import Path
    from lh2_tno.contracts import Facility

    root = Path(__file__).parents[1]
    facility = Facility.model_validate_json(
        (root / "examples/lh2_frequency_facility.json").read_text(encoding="utf-8")
    )
    raw = __import__("json").loads(
        (root / "examples/lh2_frequency_plan.json").read_text(encoding="utf-8")
    )
    raw["excluded_model_components"] = {"tank": "outside test scope"}
    raw["assets"] = [asset for asset in raw["assets"] if asset["model_component_id"] != "tank"]
    # The event is explicitly mapped to tank; the attached plan must reject
    # the attempt to reintroduce an excluded component.
    plan = FrequencyPlan.model_validate_json(json.dumps(raw))
    events, _ = bridge_legacy_scenarios(
        [_row()], {"S-001": "tank"}, source_sha256=SOURCE_SHA,
    )
    attached = attach_precomputed_events(plan, events, provenance="scope test")
    with pytest.raises(ValueError, match="excluded component"):
        generate_events(facility, attached)
