from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "export_lh2dt_native_vent_stack_prism_packet.py"
_SPEC = importlib.util.spec_from_file_location("native_vent_stack_packet", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _provider() -> tuple[object, dict[str, object]]:
    response = {"provider_export_schema": "prism.external_accident_history.v1", "data": {"event_id": "vent/event-1", "component_id": "vent-A", "port_id": "gas-out", "steps": [{"provider_source_state": {"opening": 1.0}}]}}
    return _MODULE.NativeVentStackProvider(response), response


def test_native_vent_stack_provider_preserves_identity_and_strips_incomplete_trace():
    provider, response = _provider()
    result = provider.export_accident_history({"event_id": "vent/event-1", "component_id": "vent-A", "port_id": "gas-out"})
    assert result["data"]["event_id"] == response["data"]["event_id"]
    assert "provider_source_state" not in result["data"]["steps"][0]


@pytest.mark.parametrize("field,value", [("event_id", "vent/event-2"), ("component_id", "vent-B"), ("port_id", "other-out")])
def test_native_vent_stack_provider_rejects_identity_mismatch(field: str, value: str):
    provider, _ = _provider()
    request = {"event_id": "vent/event-1", "component_id": "vent-A", "port_id": "gas-out"}
    request[field] = value
    with pytest.raises(ValueError, match=field):
        provider.export_accident_history(request)
