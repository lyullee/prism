from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "export_lh2dt_native_valve_prism_packet.py"
_SPEC = importlib.util.spec_from_file_location("native_stroke_valve_packet", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _provider() -> tuple[object, dict[str, object]]:
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {
            "event_id": "valve/event-1",
            "component_id": "valve-A",
            "port_id": "gas-out",
        },
    }
    return _MODULE.NativeStrokeValveProvider(response), response


def test_native_stroke_valve_provider_preserves_response_identity():
    provider, response = _provider()
    assert provider.export_accident_history({
        "event_id": "valve/event-1",
        "component_id": "valve-A",
        "port_id": "gas-out",
    }) == response


def test_native_stroke_valve_provider_preserves_source_throat_and_removes_only_auxiliary_opening():
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {
            "event_id": "valve/event-1",
            "component_id": "valve-A",
            "port_id": "gas-out",
            "steps": [{
                "provider_source_state": {
                    "source_specific_entropy_j_kgk": 46876.8,
                    "throat_pressure_pa_abs": 261197.2,
                    "throat_density_kg_m3": 0.25,
                    "throat_specific_enthalpy_j_kg": 3.2e6,
                    "opening": 1.0,
                }
            }],
        },
    }
    provider = _MODULE.NativeStrokeValveProvider(response)
    strict = provider.export_accident_history({
        "event_id": "valve/event-1",
        "component_id": "valve-A",
        "port_id": "gas-out",
    })
    trace = strict["data"]["steps"][0]["provider_source_state"]
    assert trace["throat_pressure_pa_abs"] == 261197.2
    assert "opening" not in trace


@pytest.mark.parametrize("field,value", [
    ("event_id", "valve/event-2"),
    ("component_id", "valve-B"),
    ("port_id", "other-out"),
])
def test_native_stroke_valve_provider_rejects_identity_mismatch(field: str, value: str):
    provider, _ = _provider()
    request = {
        "event_id": "valve/event-1",
        "component_id": "valve-A",
        "port_id": "gas-out",
    }
    request[field] = value
    with pytest.raises(ValueError, match=field):
        provider.export_accident_history(request)
