"""Audit native provider source/throat fields needed by the compressible handoff.

This is an evidence audit, not a source-state synthesizer.  Gas providers are
checked against the exact fields consumed by ``build_compressible_plane_handoff``.
Liquid/two-phase providers are reported separately because their current
accident contracts do not promise a gas compressible-plane handoff.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_CASES = (
    ("LayeredTank", "results/20261025/native_layered_tank_isolation/provider_response.json", "liquid_or_two_phase"),
    ("DynamicHEMPipe", "results/20261025/native_dynamic_pipe_isolation/provider_response.json", "liquid_or_two_phase"),
    # The same native class also has an explicit gas branch.  Keep it as a
    # separate scenario row so the liquid/two-phase contract is never recast
    # as gas while the optional compressible adapter can be audited against
    # the provider's actual gas export.
    ("DynamicHEMPipe", "results/20261026/native_dynamic_pipe_gas_horizon/provider_response.json", "gas"),
    ("StrokeLimitedCommandedValve", "results/20261025/native_stroke_valve/provider_response.json", "gas"),
    ("MappedPump", "results/20261025/native_mapped_pump/provider_response.json", "liquid"),
    ("DynamicVaporizer", "results/20261025/native_dynamic_vaporizer/provider_response.json", "gas"),
    ("DynamicReliquefier", "results/20261025/native_dynamic_reliquefier/provider_response.json", "gas"),
    ("VentStack", "results/20261025/native_vent_stack/provider_response.json", "gas"),
)

# These are the fields read by src/lh2_tno/compressible_source_adapter.py.
_REQUIRED_FOR_ADAPTER = (
    "source_specific_entropy_j_kgk",
    "throat_pressure_pa_abs",
    "throat_density_kg_m3",
    "throat_specific_enthalpy_j_kg",
)
_USEFUL_TRACE_FIELDS = (
    "source_pressure_pa_abs",
    "source_temperature_k",
    "source_density_kg_m3",
    "source_specific_enthalpy_j_kg",
    "source_specific_entropy_j_kgk",
    "throat_pressure_pa_abs",
    "throat_temperature_k",
    "throat_density_kg_m3",
    "throat_specific_enthalpy_j_kg",
    "throat_mass_flux_kg_m2_s",
    "choked",
    "provider_source_state_provenance",
)


def _read(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return value


def _step_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValueError("provider response data.steps must be a list")
    return [step for step in data["steps"] if isinstance(step, dict)]


def build() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for model, response_path, phase_family in _CASES:
        response = _read(response_path)
        steps = _step_rows(response)
        source_states = [step.get("provider_source_state") for step in steps]
        present_counts = {
            field: sum(isinstance(state, dict) and state.get(field) is not None for state in source_states)
            for field in _USEFUL_TRACE_FIELDS
        }
        missing_required_by_interval = []
        for index, state in enumerate(source_states):
            missing = [field for field in _REQUIRED_FOR_ADAPTER if not isinstance(state, dict) or state.get(field) is None]
            if missing:
                missing_required_by_interval.append({"interval": index, "missing_fields": missing})
        if phase_family == "gas":
            adapter_status = "COMPLETE" if not missing_required_by_interval else "INCOMPLETE"
            interpretation = (
                "All required source/throat fields are present for the optional adapter"
                if adapter_status == "COMPLETE"
                else "Provider source state exists but cannot be consumed by the optional compressible adapter"
            )
        else:
            adapter_status = "NOT_APPLICABLE_CURRENT_GAS_ADAPTER"
            interpretation = "Liquid/two-phase native contract requires its own validated near-field handoff"
        entries.append({
            "model_class": model,
            "provider_response": response_path,
            "phase_family": phase_family,
            "provider_model": response.get("provider_model"),
            "interval_count": len(steps),
            "provider_source_state_interval_count": sum(isinstance(state, dict) for state in source_states),
            "field_presence_counts": present_counts,
            "required_fields_for_compressible_adapter": list(_REQUIRED_FOR_ADAPTER),
            "missing_required_by_interval": missing_required_by_interval,
            "compressible_adapter_status": adapter_status,
            "interpretation": interpretation,
        })
    gas_entries = [entry for entry in entries if entry["phase_family"] == "gas"]
    model_classes = sorted({entry["model_class"] for entry in entries})
    complete_gas = sum(entry["compressible_adapter_status"] == "COMPLETE" for entry in gas_entries)
    return {
        "schema_version": "prism.native_source_state_completeness.v1",
        "status": "SOURCE_STATE_AUDITED_WITH_GAS_HANDOFF_BLOCKERS",
        "native_model_count": len(model_classes),
        "native_scenario_count": len(entries),
        "gas_model_count": len(gas_entries),
        "gas_models_complete_for_compressible_adapter": complete_gas,
        "gas_models_blocked_for_compressible_adapter": len(gas_entries) - complete_gas,
        "required_fields_for_compressible_adapter": list(_REQUIRED_FOR_ADAPTER),
        "entries": entries,
        "limitations": [
            "This audit reports provider evidence; it does not infer missing entropy or throat states",
            "Gas source-state completeness does not qualify a provider or validate a near-field correlation",
            "Liquid/two-phase cases need a separate validated handoff and are not silently recast as gas",
            "No frequency inference, physical validation claim, or facility IR/F-N promotion is made",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "gas_models_complete_for_compressible_adapter": result["gas_models_complete_for_compressible_adapter"],
        "gas_models_blocked_for_compressible_adapter": result["gas_models_blocked_for_compressible_adapter"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
