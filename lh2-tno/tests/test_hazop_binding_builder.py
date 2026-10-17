import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "build_hazop_event_mode_binding_from_frequency_plan.py"
_SPEC = importlib.util.spec_from_file_location("hazop_binding_builder", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _plan(**event_overrides):
    event = {
        "id": "facility/pipe/G1",
        "model_component_id": "pipe-01",
        "profile": "LH2_PIPE",
        "release": {"mode": "hole"},
        "annual_frequency_per_year": 1.0e-4,
        "operating_mode": "supply",
        "hazop_scenario_id": "pipe-01-supply-hole",
    }
    event.update(event_overrides)
    return {"precomputed_events": [event]}


def test_builder_copies_explicit_identity_without_inference(tmp_path):
    output = _MODULE.build_binding(_plan(), source_path=tmp_path / "frequency.json")

    assert output["status"] == "HAZOP_EVENT_MODE_BINDING_COMPLETE"
    assert output["event_count"] == 1
    row = output["event_rows"][0]
    assert row["component_id"] == "pipe-01"
    assert row["release_mode"] == "hole"
    assert row["operating_mode"] == "supply"
    assert row["mode_inference_performed"] is False
    assert row["scenario_inference_performed"] is False


@pytest.mark.parametrize("missing", ["model_component_id", "operating_mode", "hazop_scenario_id"])
def test_builder_fails_closed_when_explicit_identity_is_missing(missing):
    event = _plan()["precomputed_events"][0]
    event.pop(missing)

    with pytest.raises(ValueError, match=missing):
        _MODULE.build_binding({"precomputed_events": [event]}, source_path=Path("bad.json"))
