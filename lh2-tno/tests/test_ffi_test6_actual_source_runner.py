"""Contract tests for the external FFI Test 6 numerical runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_ffi_test6_actual_source_numerical_gate.py"
SPEC = importlib.util.spec_from_file_location("ffi_test6_actual_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_levels_are_strict_and_reproducible():
    assert MODULE._levels("40, 80, 160") == (40, 80, 160)


@pytest.mark.parametrize("value", ["40", "80,40", "40,40", "0,80", ""])
def test_levels_require_two_increasing_positive_values(value: str):
    with pytest.raises(ValueError):
        MODULE._levels(value)


def test_actual_source_identity_is_fixed_and_unfitted():
    assert MODULE.SOURCE == {
        "rate_kg_s": 0.8317,
        "nozzle_diameter_m": 0.0254,
        "liquid_mass_fraction": 0.559,
        "height_m": 0.5,
        "duration_s": 120.0,
        "temperature_K": 20.37,
    }
    assert "MAE_vol_pct" in MODULE.MONITORED
    assert "RMSE_vol_pct" in MODULE.MONITORED
