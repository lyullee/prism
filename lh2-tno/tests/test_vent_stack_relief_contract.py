from pathlib import Path

import pytest

from scripts.export_lh2dt_vent_stack_prism_packet import VentStackAccidentProvider


def _provider(**updates):
    values = {
        "root": Path("."),
        "duration_s": 0.2,
        "time_step_s": 0.1,
        "stack": {"inner_diameter_m": 0.01},
        "upstream": {"pressure_pa": 102000.0, "temperature_k": 40.0},
        "ambient_temperature_k": 288.15,
    }
    values.update(updates)
    return VentStackAccidentProvider(**values)


def test_relief_metadata_requires_setpoint_and_capacity_as_a_pair():
    provider = _provider(relief_setpoint_pa=102000.0)
    with pytest.raises(ValueError, match="supplied together"):
        provider.export_accident_history({})


def test_relief_metadata_is_not_invented_when_omitted():
    provider = _provider()
    # The pair check is intentionally reached before any external model import.
    # An omitted pair is valid as a diagnostic input and leaves the provider
    # response without qualification metadata rather than inventing defaults.
    assert provider.relief_setpoint_pa is None
    assert provider.relief_capacity_kg_s is None
    assert provider.discharge_complete is False
