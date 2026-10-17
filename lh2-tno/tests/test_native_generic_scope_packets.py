from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.build_native_generic_scope_packet_catalog import _validate_packet
from scripts.build_native_generic_scope_packet_catalog import _spec
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.resolved_liquid_worker import dynamic_state_closure_status
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
    # Temperature/density are rebuilt from the averaged P/H state, so the
    # velocity must be checked against the retained mass/area closure rather
    # than against the pre-EOS synthetic fixture value.
    assert all(
        row["velocity_m_s"] == row["mass_flow_kg_s"] / (
            row["density_kg_m3"] * row["effective_area_m2"]
        )
        for row in compact
    )


def test_inventory_depletion_with_residual_provider_mass_is_fail_closed():
    packet = {
        "termination_basis": "inventory_depletion",
        "provider_mass_balance": {
            "initial_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.2,
            "final_mass_kg": 0.8,
            "cumulative_mass_in_kg": 0.0,
            "derived_accounting_residual_kg": 0.0,
            "dynamic_state_closure": {
                "inventory_feedback_closed": True,
                "pressure_feedback_closed": True,
                "state_history_digest": "a" * 64,
                "max_abs_inventory_residual_kg": 0.0,
                "inventory_tolerance_kg": 1.0e-8,
                "max_abs_pressure_residual_pa": 0.0,
                "pressure_tolerance_pa": 1.0,
            },
        },
    }
    audit = dynamic_state_closure_status(packet)
    assert audit["ready"] is False
    assert "inventory depletion requires provider final mass at or below tolerance" in audit[
        "blocking_reasons"
    ]


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


def _event(component_id: str, event_id: str, *, diameter: float = 0.0025, mode: str = "hole"):
    return SimpleNamespace(
        id=event_id,
        model_component_id=component_id,
        profile="diagnostic",
        loc="AREA_1%",
        release=SimpleNamespace(hole_diameter_m=diameter, mode=mode),
    )


def test_optional_isolation_catalog_selects_native_pipe_and_records_controls():
    manifest = EquipmentManifest.from_json(
        Path(__file__).parents[1] / "examples" / "generic_lh2_full_scope_manifest.json"
    )
    spec = _spec(
        _event("liquid-transfer-line-01", "facility/line/G1"),
        manifest,
        Path(".tmp"),
        Path("C:/lh2dt"),
        event_index=0,
        isolation_time_s=0.1,
        post_isolation_observation_s=0.2,
    )
    assert spec["script"] == "export_lh2dt_native_dynamic_pipe_prism_packet.py"
    assert "--isolation-time-s" in spec["command"]
    assert "--post-isolation-observation-s" in spec["command"]
    assert "--failure-opening-diameter-m" in spec["command"]


def test_optional_isolation_catalog_uses_native_pump_adapter():
    manifest = EquipmentManifest.from_json(
        Path(__file__).parents[1] / "examples" / "generic_lh2_full_scope_manifest.json"
    )
    spec = _spec(
        _event("liquid-transfer-pump-01", "facility/pump/G1"),
        manifest,
        Path(".tmp"),
        Path("C:/lh2dt"),
        event_index=0,
        isolation_time_s=0.1,
        post_isolation_observation_s=0.2,
    )
    assert spec["script"] == "export_lh2dt_native_mapped_pump_prism_packet.py"
    assert "--horizon-s" in spec["command"]
    assert "--isolation-time-s" in spec["command"]
