import pytest

from scripts.export_lh2dt_dynamic_vaporizer_prism_packet import (
    _annotate_inventory_depletion_response,
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
