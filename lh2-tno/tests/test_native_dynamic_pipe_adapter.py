from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "export_lh2dt_native_dynamic_pipe_prism_packet.py"
_SPEC = importlib.util.spec_from_file_location("native_dynamic_pipe_packet", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_native_dynamic_pipe_provider_preserves_response_identity():
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {"event_id": "pipe/event-1"},
    }
    provider = _MODULE.NativeDynamicPipeProvider(response)
    assert provider.export_accident_history({"event_id": "pipe/event-1"}) == response


def test_native_dynamic_pipe_provider_rejects_event_identity_mismatch():
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {"event_id": "pipe/event-1"},
    }
    provider = _MODULE.NativeDynamicPipeProvider(response)
    with pytest.raises(ValueError, match="event_id"):
        provider.export_accident_history({"event_id": "pipe/event-2"})
