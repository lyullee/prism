from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot


_SCRIPT = Path(__file__).parents[1] / "scripts" / "run_lh2dt_native_frequency_case.py"
_SPEC = importlib.util.spec_from_file_location("native_frequency_case", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

_BIND_SCRIPT = Path(__file__).parents[1] / "scripts" / "bind_native_campaign_state_snapshots.py"
_BIND_SPEC = importlib.util.spec_from_file_location("bind_native_snapshots", _BIND_SCRIPT)
assert _BIND_SPEC is not None and _BIND_SPEC.loader is not None
_BIND_MODULE = importlib.util.module_from_spec(_BIND_SPEC)
_BIND_SPEC.loader.exec_module(_BIND_MODULE)


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


def test_campaign_state_binding_rejects_provider_inventory_mismatch(tmp_path):
    snapshot = EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id="storage-tank-01",
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=110000.0,
        temperature_k=20.0,
        mass_kg=1.0,
        phase="liquid",
    )
    digest = snapshot.digest()
    event_id = "facility/storage-shell/AREA_0.01%"
    result_digest = "b" * 64
    packet_dir = tmp_path / "events" / "000_storage"
    packet_dir.mkdir(parents=True)
    (packet_dir / "verification.json").write_text(
        json.dumps({
            "provider_result_digest": result_digest,
            "state_snapshot": snapshot.to_mapping(),
            "state_snapshot_handoff": {
                "digest": digest,
                "digest_match": True,
                "provider_echo_digest": digest,
            },
        }),
        encoding="utf-8",
    )
    (packet_dir / "resolved_release.json").write_text(
        json.dumps({"provider_result_digest": result_digest}),
        encoding="utf-8",
    )
    campaign = {
        "event_routes": [{
            "event_id": event_id,
            "branches": [{
                "request": {
                    "component_id": "storage-tank-01",
                    "resolved_release": {
                        "provider_result_digest": result_digest,
                        "available_mass_kg": 2.0,
                    },
                },
            }],
        }],
    }

    with pytest.raises(ValueError, match="state snapshot mass and provider initial inventory"):
        _BIND_MODULE.bind(campaign, tmp_path)
