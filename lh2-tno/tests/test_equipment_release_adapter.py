import pytest

from lh2_tno.equipment_release_adapter import (
    EquipmentReleaseExportError,
    build_resolved_gas_release_from_provider_response,
)


def _response():
    return {
        "operation": "equipment_dynamic_inventory",
        "data": {
            "event_kind": "accidental_leak",
            "duration_s": 0.2,
            "available_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.015,
            "cumulative_static_enthalpy_out_j": 15000.0,
            "termination_provenance": "provider positive-mass threshold",
            "steps": [
                {
                    "time_s": 0.0,
                    "mass_flow_kg_s": 0.1,
                    "pressure_pa_abs": 100000.0,
                    "specific_enthalpy_j_kg": 1.0e6,
                    "temperature_k": 20.5,
                    "density_kg_m3": 0.2,
                    "effective_area_m2": 0.01,
                    "velocity_m_s": 50.0,
                    "area_provenance": "provider nozzle area",
                    "velocity_origin": "mass_continuity_from_declared_area",
                },
                {
                    "time_s": 0.1,
                    "mass_flow_kg_s": 0.05,
                    "pressure_pa_abs": 100000.0,
                    "specific_enthalpy_j_kg": 1.0e6,
                    "temperature_k": 20.5,
                    "density_kg_m3": 0.2,
                    "effective_area_m2": 0.01,
                    "velocity_m_s": 25.0,
                    "area_provenance": "provider nozzle area",
                    "velocity_origin": "mass_continuity_from_declared_area",
                },
            ],
        },
    }


def _build(response=None):
    return build_resolved_gas_release_from_provider_response(
        _response() if response is None else response,
        component_id="tank-1",
        port_id="tank-1.leak",
        event_id="tank-1/leak/area-1",
        provider_source_digest="a" * 64,
        upstream_service_provenance="provider tank state",
        provider_boundary_reference="provider accidental outlet",
        input_origin="synthetic",
        position_enu_m=[0.0, 0.0, 1.0],
        direction_enu=[1.0, 0.0, 0.0],
        ambient_pressure_pa_abs=100000.0,
        ambient_temperature_k=288.15,
        failure_opening_diameter_m=0.1,
    )


def test_adapter_promotes_history_without_extending_it():
    release = _build()
    assert release.duration_s == 0.2
    assert release.cumulative_mass_out_kg == 0.015
    assert release.integrated_mass_kg == pytest.approx(0.015)
    assert release.integrated_static_enthalpy_j == pytest.approx(15000.0)
    assert release.termination_provenance == "provider positive-mass threshold"


def test_adapter_rejects_missing_provider_step_fields():
    response = _response()
    del response["data"]["steps"][0]["velocity_m_s"]
    with pytest.raises(EquipmentReleaseExportError, match="missing required fields"):
        _build(response)


def test_adapter_rejects_provider_ledger_mismatch():
    response = _response()
    response["data"]["cumulative_mass_out_kg"] = 0.5
    with pytest.raises(EquipmentReleaseExportError, match="failed strict PRISM validation"):
        _build(response)


def test_adapter_does_not_accept_normal_flow_as_accident():
    response = _response()
    response["data"]["event_kind"] = "normal_vent"
    with pytest.raises(EquipmentReleaseExportError, match="event_kind=accidental_leak"):
        _build(response)


def test_adapter_requires_explicit_event_kind():
    response = _response()
    del response["data"]["event_kind"]
    with pytest.raises(EquipmentReleaseExportError, match="event_kind=accidental_leak"):
        _build(response)
