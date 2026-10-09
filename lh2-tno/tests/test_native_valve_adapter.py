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
