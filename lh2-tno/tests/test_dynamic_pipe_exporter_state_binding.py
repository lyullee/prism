from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot


_SCRIPT = Path(__file__).parents[1] / "scripts" / "export_lh2dt_dynamic_pipe_prism_packet.py"
_SPEC = importlib.util.spec_from_file_location("dynamic_pipe_packet", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_dynamic_pipe_export_request_contains_canonical_state_payload():
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": "pipe-1",
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": 250000.0,
        "temperature_k": 20.5,
    })
    request = _MODULE._request(
        provider_source_digest="a" * 64,
        component_id="pipe-1",
        port_id="pipe-1.out",
        event_id="pipe-1/event-1",
        opening_diameter_m=0.002,
        position_enu_m=[0.0, 0.0, 1.0],
        model_revision="test",
        state_snapshot=snapshot,
    )
    assert request.state_snapshot is not None
    assert request.state_snapshot.digest() == snapshot.digest()
    assert request.state_snapshot_digest == snapshot.digest()


def test_dynamic_pipe_history_coarsening_preserves_mass_and_energy():
    steps = []
    for index in range(101):
        steps.append({
            "time_s": index * 0.01,
            "total_mass_flow_kg_s": 2.0,
            "gas_mass_flow_kg_s": 1.0,
            "ground_liquid_mass_flow_kg_s": 1.0,
            "airborne_liquid_mass_flow_kg_s": 0.0,
            "specific_enthalpy_j_kg": 10.0,
            "gas_pressure_pa_abs": 101325.0,
            "gas_temperature_k": 20.0,
            "gas_density_kg_m3": 1.0,
            "gas_effective_area_m2": 1.0,
            "gas_velocity_m_s": 1.0,
            "gas_velocity_origin": "mass_continuity_from_declared_area",
            "droplet_class_outcomes": [{
                "ground_liquid_mass_flow_kg_s": 1.0,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "flight_time_s": 0.0,
                "impact_position_m": [0.0, 0.0, 0.0],
                "droplet_diameter_m": 0.001,
            }],
        })

    coarsened = _MODULE._coarsen_steps(steps, duration_s=1.01)

    assert len(coarsened) <= 100
    mass = sum(
        row["total_mass_flow_kg_s"]
        * ((coarsened[index + 1]["time_s"] if index + 1 < len(coarsened) else 1.01) - row["time_s"])
        for index, row in enumerate(coarsened)
    )
    energy = sum(
        row["total_mass_flow_kg_s"]
        * row["specific_enthalpy_j_kg"]
        * ((coarsened[index + 1]["time_s"] if index + 1 < len(coarsened) else 1.01) - row["time_s"])
        for index, row in enumerate(coarsened)
    )
    assert mass == pytest.approx(2.02)
    assert energy == pytest.approx(20.2)
