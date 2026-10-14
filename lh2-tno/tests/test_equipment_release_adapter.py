import pytest

from lh2_tno.equipment_release_adapter import (
    EquipmentReleaseExportError,
    build_resolved_gas_release_from_provider_response,
    build_resolved_liquid_release_from_provider_response,
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


def test_gas_adapter_preserves_provider_port_and_source_state_per_interval():
    response = _response()
    for step in response["data"]["steps"]:
        step["provider_port_state"] = {
            "component_id": "tank-1",
            "port_id": "tank-1.leak",
            "time_s": step["time_s"],
            "fluid": "ParaHydrogen",
            "phase": "two_phase",
            "pressure_pa_abs": 250000.0,
            "temperature_k": 20.5,
            "density_kg_m3": 0.2,
            "specific_enthalpy_j_kg": 1.0e6,
            "mass_flow_kg_s": step["mass_flow_kg_s"],
            "position_enu_m": [0.0, 0.0, 1.0],
            "direction_enu": [1.0, 0.0, 0.0],
            "provenance": "equipment twin port state",
            "source_digest": "c" * 64,
        }
        step["provider_source_state"] = {
            "source_pressure_pa_abs": 250000.0,
            "source_temperature_k": 20.5,
            "source_density_kg_m3": 0.2,
            "source_specific_enthalpy_j_kg": 1.0e6,
            "source_specific_entropy_j_kgk": 1000.0,
            "throat_pressure_pa_abs": 100000.0,
            "throat_temperature_k": 20.5,
            "throat_density_kg_m3": 0.2,
            "throat_specific_enthalpy_j_kg": 1.0e6,
            "throat_mass_flux_kg_m2_s": 10.0,
            "choked": True,
            "provider_source_state_provenance": "equipment twin throat state",
        }

    release = _build(response)
    assert all(step.provider_port_state is not None for step in release.steps)
    assert all(step.provider_source_state is not None for step in release.steps)
    assert release.steps[1].provider_port_state.time_s == pytest.approx(0.1)
    assert release.steps[0].provider_port_state.source_digest == "c" * 64


def test_gas_adapter_rejects_malformed_provider_port_state():
    response = _response()
    response["data"]["steps"][0]["provider_port_state"] = {
        "component_id": "tank-1",
        "port_id": "tank-1.leak",
        "time_s": 0.0,
        "fluid": "ParaHydrogen",
        "phase": "two_phase",
        "pressure_pa_abs": 250000.0,
        "temperature_k": 20.5,
        "density_kg_m3": 0.2,
        "specific_enthalpy_j_kg": 1.0e6,
        "mass_flow_kg_s": 0.1,
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [2.0, 0.0, 0.0],
        "provenance": "equipment twin port state",
        "source_digest": "c" * 64,
    }
    with pytest.raises(EquipmentReleaseExportError, match="provider_port_state failed strict validation"):
        _build(response)


def test_adapter_preserves_provider_mass_balance_without_calling_residual_depletion():
    response = _response()
    response["data"]["provider_meta"] = {
        "initial_mass_kg": 1.0,
        "final_mass_kg": 0.8,
        "residual_mass_kg": 0.8,
        "isolation_time_s": 0.1,
        "post_isolation_observation_s": 0.02,
        "isolation_success": True,
    }
    release = _build(response)
    balance = release.provider_mass_balance
    assert balance is not None
    assert balance.initial_mass_kg == pytest.approx(1.0)
    assert balance.final_mass_kg == pytest.approx(0.8)
    assert balance.cumulative_mass_out_kg == pytest.approx(0.015)
    assert balance.reported_residual_mass_kg == pytest.approx(0.8)
    assert balance.derived_accounting_residual_kg == pytest.approx(-0.185)
    assert balance.post_isolation_observation_s == pytest.approx(0.02)
    assert balance.isolation_success is True


def test_adapter_accepts_null_optional_isolation_metadata_when_clock_not_requested():
    response = _response()
    response["data"]["provider_meta"] = {
        "initial_mass_kg": 1.0,
        "final_mass_kg": 0.985,
        "residual_mass_kg": 0.985,
        "isolation_time_s": None,
        "post_isolation_observation_s": 0.0,
        "isolation_success": None,
    }
    release = _build(response)
    assert release.provider_mass_balance is not None
    assert release.provider_mass_balance.isolation_time_s is None
    assert release.provider_mass_balance.isolation_success is None


def test_gas_adapter_preserves_explicit_hydrogen_property_basis():
    response = _response()
    response["data"]["fluid"] = "Hydrogen"
    response["data"]["property_basis"] = {
        "fluid": "Hydrogen",
        "backend": "CoolProp-HEOS",
        "energy_reference": "CoolProp-HEOS:Hydrogen:native",
    }
    release = _build(response)
    assert release.property_basis.fluid == "Hydrogen"
    assert release.property_basis.energy_reference == "CoolProp-HEOS:Hydrogen:native"


def test_adapter_preserves_and_normalizes_provider_termination_basis():
    response = _response()
    response["data"]["termination_basis"] = "isolation_success"
    release = _build(response)
    assert release.termination_basis == "reviewed_isolation_success"


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


def _liquid_response():
    return {
        "operation": "liquid_release",
        "data": {
            "event_kind": "accidental_leak",
            "upstream_service": "LH2",
            "fluid": "ParaHydrogen",
            "phase_basis": "two_phase",
            "duration_s": 0.2,
            "available_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.04,
            "cumulative_specific_enthalpy_out_j": 40000.0,
            "reference_area_m2": 0.02,
            "reference_area_provenance": "provider flashed-gas reference area",
            "termination_provenance": "provider positive-mass threshold",
            "droplet_partition_provenance": "provider ballistic ground interception",
            "steps": [
                {
                    "time_s": 0.0,
                    "total_mass_flow_kg_s": 0.2,
                    "gas_mass_flow_kg_s": 0.1,
                    "ground_liquid_mass_flow_kg_s": 0.1,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "specific_enthalpy_j_kg": 1.0e6,
                    "gas_pressure_pa_abs": 100000.0,
                    "gas_temperature_k": 20.5,
                    "gas_density_kg_m3": 0.2,
                    "gas_effective_area_m2": 0.02,
                    "gas_velocity_m_s": 25.0,
                    "gas_velocity_origin": "provider_resolved",
                    "droplet_class_outcomes": [
                        {
                            "ground_liquid_mass_flow_kg_s": 0.1,
                            "airborne_liquid_mass_flow_kg_s": 0.0,
                            "flight_time_s": 0.1,
                            "impact_position_m": [1.0, 0.0, 0.0],
                            "droplet_diameter_m": 0.001,
                        }
                    ],
                }
            ],
        },
    }


def _build_liquid(response=None, provider_result_digest=None):
    return build_resolved_liquid_release_from_provider_response(
        _liquid_response() if response is None else response,
        component_id="tank-1",
        port_id="tank-1.liquid-leak",
        event_id="tank-1/liquid/area-1",
        provider_source_digest="b" * 64,
        upstream_service_provenance="provider liquid tank state",
        provider_boundary_reference="provider liquid flash and ground partition",
        input_origin="model_prediction",
        position_enu_m=[0.0, 0.0, 1.0],
        direction_enu=[1.0, 0.0, 0.0],
        ambient_pressure_pa_abs=100000.0,
        ambient_temperature_k=288.15,
        failure_opening_diameter_m=0.1,
        provider_result_digest=provider_result_digest,
    )


def test_liquid_adapter_promotes_partition_and_mass_ledger():
    release = _build_liquid()
    assert release.phase_basis == "two_phase"
    assert release.integrated_mass_kg == pytest.approx(0.04)
    assert release.integrated_specific_enthalpy_out_j == pytest.approx(40000.0)


def test_liquid_adapter_preserves_explicit_hydrogen_property_basis():
    response = _liquid_response()
    response["data"]["fluid"] = "Hydrogen"
    response["data"]["property_basis"] = {
        "fluid": "Hydrogen",
        "backend": "CoolProp-HEOS",
        "energy_reference": "CoolProp-HEOS:Hydrogen:native",
    }
    release = _build_liquid(response)
    assert release.property_basis.fluid == "Hydrogen"
    assert release.property_basis.energy_reference == "CoolProp-HEOS:Hydrogen:native"


def test_liquid_adapter_rejects_airborne_liquid_without_adapter():
    response = _liquid_response()
    step = response["data"]["steps"][0]
    step["airborne_liquid_mass_flow_kg_s"] = 0.01
    step["total_mass_flow_kg_s"] = 0.21
    step["droplet_class_outcomes"][0]["airborne_liquid_mass_flow_kg_s"] = 0.01
    response["data"]["cumulative_mass_out_kg"] = 0.042
    with pytest.raises(EquipmentReleaseExportError, match="failed strict PRISM validation"):
        _build_liquid(response)


def test_liquid_adapter_carries_no_rainout_evidence_and_suppresses_pool_context():
    response = _liquid_response()
    step = response["data"]["steps"][0]
    step["total_mass_flow_kg_s"] = 0.2
    step["gas_mass_flow_kg_s"] = 0.2
    step["gas_effective_area_m2"] = 0.04
    step["ground_liquid_mass_flow_kg_s"] = 0.0
    step["droplet_class_outcomes"] = []
    response["data"]["cumulative_mass_out_kg"] = 0.04
    response["data"]["no_rainout_evidence"] = {
        "origin": "provider_resolved",
        "basis": "all_liquid_flash",
        "provenance": "provider flash partition has zero ground interception",
        "source_digest": "c" * 64,
    }
    release = _build_liquid(response, provider_result_digest="c" * 64)
    assert release.no_rainout_evidence is not None
