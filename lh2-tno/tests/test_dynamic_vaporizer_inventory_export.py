import pytest

from scripts.export_lh2dt_dynamic_vaporizer_prism_packet import (
    _annotate_inventory_depletion_response,
)
from scripts.export_lh2dt_dynamic_vaporizer_inventory_prism_packet import (
    _pressure_equalization_metadata,
)


def test_inventory_depletion_annotation_preserves_native_ledger_and_stop_rule():
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {
            "cumulative_mass_out_kg": 9.99999999,
            "provider_meta": {
                "final_mass_kg": 1.0e-8,
                "model_class": "lh2dt.DynamicVaporizer",
            },
        },
    }

    annotated = _annotate_inventory_depletion_response(
        response, initial_mass_kg=10.0
    )

    metadata = annotated["data"]["provider_meta"]
    assert metadata["available_mass_definition"].startswith("initial finite-volume")
    assert metadata["depletion_threshold_kg"] == pytest.approx(1.0e-8)
    assert metadata["remaining_inventory_kg"] == pytest.approx(1.0e-8)
    assert metadata["max_total_mass_residual_kg"] == pytest.approx(0.0)
    assert "state.mass_kg" in metadata["termination_rule"]
    assert response["data"]["provider_meta"] == {
        "final_mass_kg": 1.0e-8,
        "model_class": "lh2dt.DynamicVaporizer",
    }


@pytest.mark.parametrize(
    "response, initial_mass, message",
    [
        ({}, 1.0, "data field"),
        ({"data": {"provider_meta": {}}}, 1.0, "mass ledger"),
        (
            {"data": {"cumulative_mass_out_kg": 1.0, "provider_meta": {"final_mass_kg": 2.0}}},
            0.0,
            "invalid mass ledger",
        ),
    ],
)
def test_inventory_depletion_annotation_rejects_incomplete_or_invalid_ledger(
    response, initial_mass, message
):
    with pytest.raises(ValueError, match=message):
        _annotate_inventory_depletion_response(
            response, initial_mass_kg=initial_mass
        )


def test_pressure_equalization_metadata_requires_explicit_zero_flow_tail():
    steps = [
        {
            "time_s": 0.0,
            "mass_flow_kg_s": 1.0,
            "provider_source_state": {"source_pressure_pa_abs": 102000.0},
        },
        {
            "time_s": 6.3,
            "mass_flow_kg_s": 0.0,
            "provider_source_state": {"source_pressure_pa_abs": 101000.0},
        },
        {
            "time_s": 12.6,
            "mass_flow_kg_s": 0.0,
            "provider_source_state": {"source_pressure_pa_abs": 100900.0},
        },
    ]

    metadata = _pressure_equalization_metadata(
        steps, duration_s=600.0, ambient_pressure_pa_abs=101325.0
    )

    assert metadata["pressure_equalization_success"] is True
    assert metadata["pressure_equalization_time_s"] == 6.3
    assert metadata["post_pressure_equalization_observation_s"] == 6.3
    assert metadata["terminal_source_pressure_pa_abs"] == 100900.0
