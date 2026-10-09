from __future__ import annotations

import pytest

from lh2_tno.native_source_state import (
    NativeSourceStateCompletionError,
    complete_isentropic_throat_source_states,
)


class _State:
    phase = "gas"
    density_kg_m3 = 0.8
    temperature_K = 250.0
    specific_enthalpy_J_kg = 3.2e6
    specific_entropy_J_kgK = 44000.0


class _Properties:
    def from_pT(self, pressure_pa: float, temperature_k: float) -> _State:
        assert pressure_pa > 0.0 and temperature_k > 0.0
        return _State()

    def from_ps(self, pressure_pa: float, entropy_j_kgk: float) -> _State:
        assert pressure_pa > 0.0 and entropy_j_kgk > 0.0
        return _State()


def _response() -> dict:
    return {
        "provider_export_schema": "prism.external_accident_history.v1",
        "data": {
            "steps": [{
                "time_s": 0.0,
                "provider_source_state": {
                    "source_pressure_pa_abs": 500000.0,
                    "source_temperature_k": 300.0,
                    "throat_pressure_pa_abs": 250000.0,
                },
            }],
        },
    }


def test_completion_fills_only_property_derived_fields():
    enriched, audit = complete_isentropic_throat_source_states(
        _response(), properties=_Properties()
    )
    trace = enriched["data"]["steps"][0]["provider_source_state"]
    assert trace["source_specific_entropy_j_kgk"] == 44000.0
    assert trace["throat_density_kg_m3"] == 0.8
    assert audit["status"] == "COMPLETED_ISENTROPIC_THROAT_FIELDS"
    assert audit["source_pressure_inferred"] is False
    assert _response()["data"]["steps"][0]["provider_source_state"].get("source_specific_entropy_j_kgk") is None


def test_completion_rejects_missing_pressure_anchors():
    response = _response()
    response["data"]["steps"][0]["provider_source_state"].pop("throat_pressure_pa_abs")
    with pytest.raises(NativeSourceStateCompletionError, match="throat_pressure"):
        complete_isentropic_throat_source_states(response, properties=_Properties())
