import pytest

from lh2_tno.equipment_accident_export import (
    ACCIDENT_EXPORT_REQUEST_SCHEMA,
    EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
    EquipmentAccidentExportError,
    AccidentReleaseExportRequest,
    EmergencyReliefExportRequest,
    InventoryReleaseExportRequest,
    export_equipment_gas_accident_history,
    export_equipment_emergency_relief_history,
    export_equipment_inventory_release_history,
)


def _request(**updates):
    payload = {
        "schema_version": ACCIDENT_EXPORT_REQUEST_SCHEMA,
        "event_kind": "accidental_leak",
        "component_id": "tank-1",
        "port_id": "tank-1.leak",
        "event_id": "tank-1/leak/area-1",
        "failure_mode": "small_hole",
        "failure_opening_diameter_m": 0.1,
        "horizon_s": 0.2,
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 100000.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": "a" * 64,
        "provider_boundary_reference": "tank accident outlet",
        "input_origin": "synthetic",
        "model_package": "lh2dt",
        "model_class": "LayeredTank",
        "model_revision": "test-revision",
        "state_snapshot_digest": "b" * 64,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit provider accident scenario",
        "provider_termination_required": True,
    }
    payload.update(updates)
    return payload


def _response(request):
    return {
        "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
        "data": {
            "event_kind": "accidental_leak",
            "event_id": request["event_id"],
            "component_id": request["component_id"],
            "port_id": request["port_id"],
            "duration_s": 0.2,
            "available_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.015,
            "cumulative_static_enthalpy_out_j": 15000.0,
            "termination_provenance": "provider positive-mass threshold",
            "termination_basis": "inventory_depletion",
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


class _Provider:
    def __init__(self):
        self.requests = []

    def export_accident_history(self, request):
        self.requests.append(request)
        return _response(request)


class _StateOnlyModel:
    def evaluate(self, *_args, **_kwargs):
        return {"pressure_pa_abs": 100000.0}


def test_explicit_provider_export_is_strictly_promoted_but_diagnostic_is_not_qualified():
    provider = _Provider()
    result = export_equipment_gas_accident_history(provider, _request())
    assert result.release.duration_s == pytest.approx(0.2)
    assert result.provider_method == "export_accident_history"
    assert result.promotion_status == "DIAGNOSTIC_PACKET_NOT_PROMOTED"
    assert result.provider_packet_promoted is False
    assert provider.requests[0]["event_kind"] == "accidental_leak"


def test_qualified_actual_requires_explicit_evidence_status():
    result = export_equipment_gas_accident_history(
        _Provider(), _request(evidence_status="qualified_actual")
    )
    assert result.provider_packet_promoted is True
    assert result.promotion_status == "QUALIFIED_PROVIDER_PACKET"


def test_state_only_model_cannot_be_used_as_accident_export():
    with pytest.raises(EquipmentAccidentExportError, match="export_accident_history"):
        export_equipment_gas_accident_history(_StateOnlyModel(), _request())


def test_normal_state_response_is_rejected_even_with_export_method():
    class NormalProvider(_Provider):
        def export_accident_history(self, request):
            response = _response(request)
            response["normal_state_snapshot"] = True
            return response

    with pytest.raises(EquipmentAccidentExportError, match="normal-state snapshot"):
        export_equipment_gas_accident_history(NormalProvider(), _request())


def test_request_requires_provider_owned_termination():
    with pytest.raises(EquipmentAccidentExportError, match="provider_termination_required"):
        AccidentReleaseExportRequest.from_mapping(
            _request(provider_termination_required=False)
        )


def test_provider_schema_and_identity_are_checked():
    class BadProvider(_Provider):
        def export_accident_history(self, request):
            response = _response(request)
            response["provider_export_schema"] = "normal-flow"
            return response

    with pytest.raises(EquipmentAccidentExportError, match="external_accident_history"):
        export_equipment_gas_accident_history(BadProvider(), _request())


def test_emergency_relief_export_uses_separate_no_random_opening_contract():
    payload = {
        "schema_version": "prism.equipment_emergency_relief_export_request.v1",
        "event_kind": "emergency_relief",
        "component_id": "vent-1",
        "port_id": "vent-1.out",
        "event_id": "vent-1/maximum-relief-discharge",
        "horizon_s": 0.2,
        "position_enu_m": [0.0, 0.0, 2.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 100000.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": "a" * 64,
        "provider_boundary_reference": "vent relief outlet",
        "input_origin": "synthetic",
        "model_package": "lh2dt",
        "model_class": "VentStack",
        "model_revision": "test-revision",
        "state_snapshot_digest": "b" * 64,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit provider relief scenario",
        "provider_termination_required": True,
    }

    class ReliefProvider:
        def export_accident_history(self, request):
            response = _response({"event_id": request["event_id"], "component_id": request["component_id"], "port_id": request["port_id"]})
            response["data"]["event_kind"] = "emergency_relief"
            response["data"]["termination_basis"] = "emergency_relief_discharge"
            return response

    request = EmergencyReliefExportRequest.from_mapping(payload)
    result = export_equipment_emergency_relief_history(ReliefProvider(), request)
    assert result.release.event_kind == "emergency_relief"
    assert result.release.failure_opening_diameter_m is None
    assert result.release.termination_basis == "emergency_relief_discharge"
    assert result.provider_packet_promoted is False


def test_inventory_export_requires_provider_owned_inventory_termination():
    payload = {
        "schema_version": "prism.equipment_inventory_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": "vaporizer-1",
        "port_id": "vaporizer-1.out",
        "event_id": "vaporizer-1/inventory",
        "release_mode": "instantaneous_inventory",
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 100000.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": "a" * 64,
        "provider_boundary_reference": "inventory outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt",
        "model_class": "DynamicVaporizer",
        "model_revision": "test-revision",
        "state_snapshot_digest": "b" * 64,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit inventory diagnostic",
        "provider_termination_required": True,
    }
    request = InventoryReleaseExportRequest.from_mapping(payload)
    result = export_equipment_inventory_release_history(_Provider(), request)
    assert result.release.failure_opening_diameter_m is None
    assert result.release.termination_basis == "inventory_depletion"
    assert result.release.event_kind == "accidental_leak"


def test_inventory_export_rejects_hole_like_termination():
    class HoleTerminatingProvider(_Provider):
        def export_accident_history(self, request):
            response = _response(request)
            response["data"]["termination_basis"] = "provider_positive_mass_threshold"
            return response

    payload = {
        "schema_version": "prism.equipment_inventory_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": "vaporizer-1",
        "port_id": "vaporizer-1.out",
        "event_id": "vaporizer-1/inventory",
        "release_mode": "instantaneous_inventory",
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 100000.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": "a" * 64,
        "provider_boundary_reference": "inventory outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt",
        "model_class": "DynamicVaporizer",
        "model_revision": "test-revision",
        "state_snapshot_digest": "b" * 64,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit inventory diagnostic",
        "provider_termination_required": True,
    }
    with pytest.raises(EquipmentAccidentExportError, match="inventory_depletion"):
        export_equipment_inventory_release_history(
            HoleTerminatingProvider(), InventoryReleaseExportRequest.from_mapping(payload)
        )
