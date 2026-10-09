import json

import pytest

from lh2_tno.compressible_source_adapter import (
    CompressibleSourceAdapterError,
    build_compressible_plane_handoff,
)
from lh2_tno.contracts import canonical_digest


class _State:
    def __init__(self, *, h, s=50000.0):
        self.temperature_K = 290.0
        self.density_kg_m3 = 0.1
        self.specific_enthalpy_J_kg = h
        self.specific_entropy_J_kgK = s
        self.phase = "gas"


class _Properties:
    def from_ph(self, pressure_pa, enthalpy_j_kg):
        return _State(h=enthalpy_j_kg)

    def from_ps(self, pressure_pa, entropy_j_kgk):
        return _State(h=3.9e6, s=entropy_j_kgk)


def _provider_and_packet():
    provider = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "provider_model": "synthetic-provider",
        "provider_source_digest": "a" * 64,
        "data": {
            "event_kind": "normal_vent",
            "event_id": "source-state-test",
            "component_id": "component",
            "port_id": "port",
            "duration_s": 0.1,
            "available_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.002,
            "cumulative_static_enthalpy_out_j": 7800.0,
            "termination_provenance": "synthetic clock",
            "steps": [{
                "time_s": 0.0,
                "mass_flow_kg_s": 0.02,
                "pressure_pa_abs": 101325.0,
                "specific_enthalpy_j_kg": 3.9e6,
                "temperature_k": 290.0,
                "density_kg_m3": 0.1,
                "effective_area_m2": 0.001,
                "velocity_m_s": 200.0,
                "area_provenance": "synthetic",
                "velocity_origin": "provider_resolved",
                "provider_source_state": {
                    "source_pressure_pa_abs": 120000.0,
                    "source_temperature_k": 300.0,
                    "source_density_kg_m3": 0.12,
                    "source_specific_enthalpy_j_kg": 3.9e6,
                    "source_specific_entropy_j_kgk": 50000.0,
                    "throat_pressure_pa_abs": 120000.0,
                    "throat_temperature_k": 300.0,
                    "throat_density_kg_m3": 0.12,
                    "throat_specific_enthalpy_j_kg": 3.9e6,
                    "throat_mass_flux_kg_m2_s": 20.0,
                    "choked": False,
                },
            }],
        },
    }
    packet = {
        "component_id": "component",
        "port_id": "port",
        "event_id": "source-state-test",
        "event_kind": "normal_vent",
        "upstream_service": "GH2",
        "upstream_service_provenance": "synthetic",
        "enthalpy_convention": "static_exit_enthalpy",
        "property_basis": {
            "fluid": "Hydrogen",
            "backend": "CoolProp-HEOS",
            "energy_reference": "CoolProp-HEOS:Hydrogen:native",
        },
        "provider_source_digest": "a" * 64,
        "provider_result_digest": canonical_digest(provider),
        "provider_boundary_reference": "synthetic",
        "input_origin": "synthetic",
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "duration_s": 0.1,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.002,
        "cumulative_static_enthalpy_out_j": 7800.0,
        "steps": [{
            "time_s": 0.0,
            "mass_flow_kg_s": 0.02,
            "pressure_pa_abs": 101325.0,
            "specific_enthalpy_j_kg": 3.9e6,
            "temperature_k": 290.0,
            "density_kg_m3": 0.1,
            "effective_area_m2": 0.001,
            "velocity_m_s": 200.0,
            "area_provenance": "synthetic",
            "velocity_origin": "provider_resolved",
        }],
        "termination_provenance": "synthetic clock",
    }
    return provider, packet


def test_source_state_adapter_binds_exact_provider_digest():
    provider, packet = _provider_and_packet()
    result = build_compressible_plane_handoff(
        packet, provider, properties=_Properties()
    )
    assert result.audit["status"] == "COMPRESSIBLE_PLANE_HANDOFF_GENERATED_SOURCE_STATE_BOUND"
    assert result.audit["interval_count"] == 1
    assert result.export["handoff"]["states"][0]["velocity_m_s"] > 0.0


def test_source_state_adapter_refuses_missing_source_state():
    provider, packet = _provider_and_packet()
    del provider["data"]["steps"][0]["provider_source_state"]
    provider_digest = canonical_digest(provider)
    packet["provider_result_digest"] = provider_digest
    with pytest.raises(CompressibleSourceAdapterError, match="provider_source_state"):
        build_compressible_plane_handoff(packet, provider, properties=_Properties())


def test_source_state_adapter_refuses_digest_mismatch():
    provider, packet = _provider_and_packet()
    packet["provider_result_digest"] = "b" * 64
    with pytest.raises(CompressibleSourceAdapterError, match="digest"):
        build_compressible_plane_handoff(packet, provider, properties=_Properties())


def test_source_state_adapter_preserves_zero_flow_termination_interval():
    provider, packet = _provider_and_packet()
    zero_provider_step = json.loads(json.dumps(provider["data"]["steps"][0]))
    zero_provider_step["time_s"] = 0.1
    zero_provider_step["mass_flow_kg_s"] = 0.0
    zero_provider_step["velocity_m_s"] = 0.0
    zero_provider_step["provider_source_state"].update(
        throat_pressure_pa_abs=101325.0,
        throat_temperature_k=290.0,
        throat_density_kg_m3=0.1,
        throat_specific_enthalpy_j_kg=3.9e6,
        throat_mass_flux_kg_m2_s=0.0,
        choked=False,
    )
    provider["data"]["duration_s"] = 0.2
    provider["data"]["steps"].append(zero_provider_step)
    packet["duration_s"] = 0.2
    packet["steps"].append({
        "time_s": 0.1,
        "mass_flow_kg_s": 0.0,
        "pressure_pa_abs": 101325.0,
        "specific_enthalpy_j_kg": 3.9e6,
        "temperature_k": 290.0,
        "density_kg_m3": 0.1,
        "effective_area_m2": 0.001,
        "velocity_m_s": 0.0,
        "area_provenance": "synthetic",
        "velocity_origin": "provider_resolved",
    })
    packet["provider_result_digest"] = canonical_digest(provider)
    result = build_compressible_plane_handoff(
        packet, provider, properties=_Properties()
    )
    assert result.audit["inactive_interval_count"] == 1
    assert result.export["handoff"]["states"][1]["velocity_m_s"] == 0.0
