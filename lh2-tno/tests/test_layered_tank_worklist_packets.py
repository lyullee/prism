import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "build_layered_tank_worklist_packets.py"
_SPEC = importlib.util.spec_from_file_location("build_layered_tank_worklist_packets", _SCRIPT)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_diagnostic_time_step_scales_with_opening_area():
    reference = _MODULE.diagnostic_time_step(0.0127)
    twice_diameter = _MODULE.diagnostic_time_step(0.0254)

    assert reference == pytest.approx(0.001)
    assert twice_diameter == pytest.approx(reference / 4.0)


@pytest.mark.parametrize("value", [0.0, -0.1, float("nan"), float("inf")])
def test_diagnostic_time_step_rejects_nonpositive_or_nonfinite_values(value):
    with pytest.raises(ValueError, match="opening_diameter_m"):
        _MODULE.diagnostic_time_step(value)


def test_empty_supported_case_set_still_writes_zero_packet_coverage(tmp_path):
    report = _MODULE.build_packets(
        {
            "work_items": [
                {
                    "event_id": "pipe/event",
                    "component_id": "pipe-01",
                    "release_mode": "hole",
                    "provider_event_kind": "accidental_leak",
                    "required_opening_diameter_m": 0.01,
                    "accident_port_ids": ["pipe-out"],
                }
            ]
        },
        lh2dt_root=tmp_path / "lh2dt",
        slabx_root=tmp_path / "slabx",
        output_dir=tmp_path / "diagnostic",
        component_id="storage-tank-01",
        target_release_kg=1.0e-4,
        max_intervals=1,
        reference_time_step_s=0.001,
    )

    assert report["packet_count"] == 0
    assert report["uncomputed_case_count"] == 0
    assert report["coverage_status"] == "NO_EXACT_MATCH"
    assert report["coverage_unmatched_event_count"] == 1
