from __future__ import annotations

import importlib.util
from pathlib import Path

from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot


_SCRIPT = Path(__file__).parents[1] / "scripts" / "run_lh2dt_native_frequency_case.py"
_SPEC = importlib.util.spec_from_file_location("native_frequency_case", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_native_frequency_request_carries_provider_initialized_snapshot():
    snapshot = EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id="storage-tank-01",
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=110000.0,
        temperature_k=20.0,
        mass_kg=71.7644005715206,
        phase="liquid",
        position_enu_m=(0.0, 0.0, 1.0),
    )
    request = _MODULE._native_request(
        "a" * 64,
        snapshot.digest(),
        state_snapshot=snapshot,
    )

    assert request.state_snapshot is not None
    assert request.state_snapshot.mass_kg == snapshot.mass_kg
    assert request.state_snapshot_digest == snapshot.digest()
