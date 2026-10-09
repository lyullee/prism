from __future__ import annotations

import importlib.util
from pathlib import Path

from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot


_SCRIPT = Path(__file__).parents[1] / "scripts" / "export_lh2dt_dynamic_pipe_prism_packet.py"
_SPEC = importlib.util.spec_from_file_location("dynamic_pipe_packet", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_dynamic_pipe_export_request_contains_canonical_state_payload():
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": "pipe-1",
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": 250000.0,
        "temperature_k": 20.5,
    })
    request = _MODULE._request(
        provider_source_digest="a" * 64,
        component_id="pipe-1",
        port_id="pipe-1.out",
        event_id="pipe-1/event-1",
        opening_diameter_m=0.002,
        position_enu_m=[0.0, 0.0, 1.0],
        model_revision="test",
        state_snapshot=snapshot,
    )
    assert request.state_snapshot is not None
    assert request.state_snapshot.digest() == snapshot.digest()
    assert request.state_snapshot_digest == snapshot.digest()
