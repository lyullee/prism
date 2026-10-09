from __future__ import annotations

from scripts.build_native_generic_scope_packet_catalog import _validate_packet
from scripts.export_lh2dt_dynamic_vaporizer_inventory_prism_packet import _coarsen_steps


def _step(time_s: float) -> dict:
    return {
        "time_s": time_s,
        "mass_flow_kg_s": 2.0,
        "pressure_pa_abs": 101325.0,
        "specific_enthalpy_j_kg": 4.0,
        "temperature_k": 300.0,
        "density_kg_m3": 2.0,
        "effective_area_m2": 0.5,
        "velocity_m_s": 2.0,
        "area_provenance": "diagnostic",
        "velocity_origin": "mass_continuity_from_declared_area",
        "provider_source_state": None,
    }


def test_inventory_trace_coarsening_preserves_clock_and_integrated_mass():
    steps = [_step(index * 0.1) for index in range(6000)]
    compact = _coarsen_steps(steps, duration_s=600.0)
    assert len(compact) == 96
    assert compact[0]["time_s"] == 0.0
    assert compact[-1]["time_s"] < 600.0
    mass = sum(
        row["mass_flow_kg_s"] * ((compact[i + 1]["time_s"] if i + 1 < len(compact) else 600.0) - row["time_s"])
        for i, row in enumerate(compact)
    )
    assert mass == 1200.0
    assert all(row["velocity_m_s"] == 2.0 for row in compact)


def test_native_packet_identity_validator_rejects_wrong_port():
    spec = {
        "event_id": "facility/pipe/G1",
        "component_id": "pipe-01",
        "port_id": "pipe-accident-out",
    }
    packet = {
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": "facility/pipe/G1",
        "component_id": "pipe-01",
        "port_id": "other-port",
    }
    assert _validate_packet(spec, "release", packet) == ["port_id mismatch"]
