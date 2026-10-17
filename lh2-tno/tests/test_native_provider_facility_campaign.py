from __future__ import annotations

from types import SimpleNamespace
import json

from scripts.run_native_provider_facility_campaign import (
    _dynamic_state_closure_dump,
    _facility_frequency_scenarios,
    _has_explicit_provider_source_states,
    _packet_event_match,
    _bind_hazop_event_modes,
)


def test_multi_equipment_frequency_scenarios_keep_missing_bounds_fixed() -> None:
    events = [
        {"asset_id": "pump", "marginal_p05_per_year": None, "marginal_p95_per_year": None},
        {"asset_id": "valve", "marginal_p05_per_year": 1.0e-5, "marginal_p95_per_year": 1.0e-3},
        {"asset_id": "valve", "marginal_p05_per_year": 2.0e-6, "marginal_p95_per_year": 2.0e-4},
    ]

    scenarios = _facility_frequency_scenarios(events)

    assert [scenario.id for scenario in scenarios] == [
        "native-provider-facility-published",
        "native-provider-facility-p05",
        "native-provider-facility-p95",
    ]
    assert all(scenario.asset_quantiles["pump"] == "fixed" for scenario in scenarios)
    assert scenarios[0].asset_quantiles["valve"] == "published"
    assert scenarios[1].asset_quantiles["valve"] == "p05"
    assert scenarios[2].asset_quantiles["valve"] == "p95"
    assert all("no frequency inference" in scenario.provenance for scenario in scenarios)


def test_multi_equipment_frequency_scenarios_use_fixed_when_no_bounds_exist() -> None:
    scenarios = _facility_frequency_scenarios([
        {"asset_id": "pump", "marginal_p05_per_year": None, "marginal_p95_per_year": None},
    ])

    assert len(scenarios) == 1
    assert scenarios[0].id == "native-provider-facility-fixed"
    assert scenarios[0].asset_quantiles == {"pump": "fixed"}
    assert "no frequency inference" in scenarios[0].provenance


def test_emergency_relief_packet_matches_relief_event_without_opening() -> None:
    packet = SimpleNamespace(
        event_kind="emergency_relief",
        event_id="facility/vent/G1",
        component_id="pressure-relief-vent-01",
        failure_opening_diameter_m=None,
    )
    relief_event = SimpleNamespace(
        id="facility/vent/G1",
        model_component_id="pressure-relief-vent-01",
        release=SimpleNamespace(mode="maximum_relief_discharge", hole_diameter_m=None),
    )

    assert _packet_event_match(packet, [relief_event]).id == "facility/vent/G1"


def test_inventory_packet_matches_exact_termination_event_without_opening() -> None:
    packet = SimpleNamespace(
        event_id="facility/vaporizer/G1",
        component_id="vaporizer",
        failure_opening_diameter_m=None,
        termination_basis="inventory_depletion",
    )
    inventory_event = SimpleNamespace(
        id="facility/vaporizer/G1",
        model_component_id="vaporizer",
        release=SimpleNamespace(mode="instantaneous_inventory"),
    )
    assert _packet_event_match(packet, [inventory_event]).id == "facility/vaporizer/G1"


def test_low_speed_gas_packet_requires_provider_source_state_for_slabx_path() -> None:
    state = object()
    packet = SimpleNamespace(
        boundary_kind="resolved_atmospheric_gas_exit",
        steps=[SimpleNamespace(provider_source_state=state), SimpleNamespace(provider_source_state=state)],
    )
    assert _has_explicit_provider_source_states(packet) is True
    packet.steps[1].provider_source_state = None
    assert _has_explicit_provider_source_states(packet) is False


def test_dynamic_state_closure_dump_preserves_provider_evidence() -> None:
    closure = SimpleNamespace(
        model_dump=lambda mode: {
            "schema_version": "prism.provider_dynamic_state_closure.v1",
            "state_history_digest": "b" * 64,
        }
    )
    packet = SimpleNamespace(provider_mass_balance=SimpleNamespace(dynamic_state_closure=closure))
    assert _dynamic_state_closure_dump(packet)["state_history_digest"] == "b" * 64
    assert _dynamic_state_closure_dump(SimpleNamespace(provider_mass_balance=None)) is None


def test_hazop_event_mode_binding_requires_exact_event_identity(tmp_path) -> None:
    event = SimpleNamespace(
        id="plan/tank/G1",
        model_component_id="tank",
        release=SimpleNamespace(mode="hole"),
        operating_mode=None,
        hazop_scenario_id=None,
    )
    path = tmp_path / "binding.json"
    path.write_text(json.dumps({"event_rows": [{
        "event_id": "plan/tank/G1",
        "component_id": "tank",
        "release_mode": "hole",
        "operating_mode": "receiving",
        "hazop_scenario_id": "tank-receiving-g1",
    }]}), encoding="utf-8")
    bound, audit = _bind_hazop_event_modes((event,), path)
    assert bound[0].operating_mode == "receiving"
    assert bound[0].hazop_scenario_id == "tank-receiving-g1"
    assert audit["bound_event_count"] == 1
    assert audit["unbound_event_count"] == 0


def test_hazop_event_mode_binding_does_not_infer_unmatched_events(tmp_path) -> None:
    event = SimpleNamespace(
        id="plan/tank/G1",
        model_component_id="tank",
        release=SimpleNamespace(mode="hole"),
        operating_mode=None,
        hazop_scenario_id=None,
    )
    path = tmp_path / "binding.json"
    path.write_text(json.dumps({"event_rows": [{
        "event_id": "plan/tank/G2",
        "component_id": "tank",
        "release_mode": "hole",
        "operating_mode": "receiving",
        "hazop_scenario_id": "tank-receiving-g2",
    }]}), encoding="utf-8")
    bound, audit = _bind_hazop_event_modes((event,), path)
    assert bound[0].operating_mode is None
    assert bound[0].hazop_scenario_id is None
    assert audit["bound_event_count"] == 0
    assert audit["orphan_binding_count"] == 1
