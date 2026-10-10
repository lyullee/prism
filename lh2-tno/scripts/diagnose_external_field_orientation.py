"""Run a declared coordinate-orientation sensitivity for one outdoor field replay.

The sweep changes only the model's ENU release bearing.  It is a diagnostic for
an unresolved field coordinate convention; it is not parameter fitting and it
cannot promote a measured-source replay to physical validation.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend  # noqa: E402
from lh2_tno.consequences import ConsequenceRequest  # noqa: E402
from lh2_tno.contracts import Facility  # noqa: E402
from lh2_tno.equipment_boundary import ResolvedLiquidRelease  # noqa: E402
from lh2_tno.field_model_comparison import build_field_model_comparison_record  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _field_paths(field: dict[str, Any]) -> tuple[Path, Path]:
    channels = field.get("channels")
    if not isinstance(channels, list):
        raise ValueError("field evidence has no channels")
    found: dict[str, Path] = {}
    for row in channels:
        if isinstance(row, dict) and row.get("channel") in {"receptor_observations", "source_boundary"}:
            path = row.get("path")
            if isinstance(path, str):
                found[row["channel"]] = Path(path).resolve()
    if set(found) != {"receptor_observations", "source_boundary"}:
        raise ValueError("field evidence must expose receptor_observations and source_boundary")
    return found["receptor_observations"], found["source_boundary"]


def _receptors(path: Path) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result.setdefault(row["sensor_id"], [
                float(row["x_m"]), float(row["y_m"]), float(row["height_m"]),
            ])
    if not result:
        raise ValueError("field receptor observations are empty")
    return result


def _bearing_vector(bearing_deg: float) -> list[float]:
    angle = math.radians(bearing_deg)
    return [math.sin(angle), math.cos(angle), 0.0]


def _facility(template_path: Path, receptor_positions: dict[str, list[float]]) -> Facility:
    payload = _read_json(template_path)
    payload["components"] = [component for component in payload["components"] if component["id"] == "storage"]
    component = payload["components"][0]
    component["property_basis"] = {
        "fluid": "ParaHydrogen",
        "backend": "CoolProp-HEOS",
        "energy_reference": "CoolProp-HEOS:ParaHydrogen:native",
    }
    component["parameters_si"]["volume_m3"] = 1.0
    payload["ports"] = [{
        "id": "storage.out", "component_id": "storage", "phase": "two_phase", "direction": "out",
    }]
    payload["edges"] = []
    payload["receptors"] = [
        {"id": sensor_id, "position_enu_m": position}
        for sensor_id, position in sorted(receptor_positions.items())
    ]
    return Facility.model_validate_json(json.dumps(payload, allow_nan=False))


def _request(
    release: ResolvedLiquidRelease,
    weather: dict[str, Any],
    receptor_count: int,
    bearing_deg: float,
) -> ConsequenceRequest:
    duration = float(release.duration_s)
    payload = {
        "component_id": "storage",
        "source_input": None,
        "resolved_release": None,
        "resolved_release_set": None,
        "resolved_liquid_release": release.model_dump(mode="json"),
        "available_mass_kg": release.available_mass_kg,
        "source_position_enu_m": list(release.position_enu_m),
        "source_positions_enu_m": None,
        "weather": weather,
        "pool": None,
        "ignition": {
            "direct_probability": 0.1,
            "delayed_probability_given_no_direct": 0.2,
            "explosion_probability_given_delayed": 0.4,
            "delayed_time_s": 1.0,
            "burn_back_duration_s": 2.0,
            "obstructed_energy_fraction": 0.08,
            "provenance": "diagnostic coordinate sensitivity only",
            "deflagration_only": True,
        },
        "domain": {
            "downwind_bounds_m": [-10.0, 100.0],
            "crosswind_bounds_m": [-30.0, 30.0],
            "height_bounds_m": [0.0, 20.0],
            "cell_size_m": 1.0,
        },
        "evaluation_times_s": list(range(int(round(duration)) + 1)),
        "radiative_fraction_range": [0.06, 0.12],
        "radiation_provenance": "diagnostic coordinate sensitivity only",
        "annual_frequency_per_year": None,
        "annual_frequency_provenance": None,
        "frequency_event": None,
        "release_termination": {
            "basis": "synthetic_diagnostic_horizon",
            "time_s": duration,
            "provenance": "measured-source replay sensitivity; no provider termination claim",
        },
        "source_operator": "equipment_liquid_release",
        "source_duration_mode": "declared",
        "occupancy_probability": 1.0,
        "initiation_intensity_per_s": None,
        "frequency_scope": "single_initiating_event_current_weather",
        "dispersion_x_max_m": 100.0,
        "transition_dx_m": 0.1,
        "transition_x_max_m": 100.0,
        "n_puff_steps": 80,
    }
    # The argument is recorded in the release itself; retaining this assertion
    # prevents a future caller from accidentally sweeping a different vector.
    if not math.isclose(math.degrees(math.atan2(release.direction_enu[0], release.direction_enu[1])) % 360.0,
                        bearing_deg, abs_tol=1e-6):
        raise ValueError("release bearing and request bearing disagree")
    if receptor_count <= 0:
        raise ValueError("receptor_count must be positive")
    return ConsequenceRequest.model_validate_json(json.dumps(payload, allow_nan=False))


def _prediction(base: dict[str, Any], data: dict[str, Any], release: ResolvedLiquidRelease, bearing: float) -> dict[str, Any]:
    value = copy.deepcopy(base)
    value["source_boundary_binding"] = copy.deepcopy(base["source_boundary_binding"])
    value["source_boundary_binding"]["mode"] = "measured_source_replay"
    value["coordinate_metadata"] = {
        "field_axis_definition_status": "not_supplied_in_public_workbook",
        "model_axis_assumption": "x=east, y=north, z=up; source-relative metres",
        "wind_direction_convention": "meteorological wind-from bearing, clockwise from north",
        "wind_from_bearing_deg": base.get("coordinate_metadata", {}).get("wind_from_bearing_deg", 315.0),
        "wind_to_bearing_deg": (base.get("coordinate_metadata", {}).get("wind_from_bearing_deg", 315.0) + 180.0) % 360.0,
        "source_release_bearing_deg": bearing,
        "source_direction_enu": list(release.direction_enu),
        "review_note": "Bearing was changed for a declared sensitivity only; no bearing was fitted or promoted.",
    }
    value["receptors"] = [
        {
            "id": row["id"],
            "position_enu_m": row.get("position_enu_m"),
            "concentration_history": row.get("concentration_history", []),
        }
        for row in data["receptors"]
    ]
    value["prediction_provenance"] = {
        "result_status": data.get("status"),
        "raw_result_retained_outside_repository": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "orientation_sweep_bearing_deg": bearing,
        "backend_elapsed_ms": data.get("stage_elapsed_ms", {}).get("near_field_and_dispersion"),
    }
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-evidence", type=Path, required=True)
    parser.add_argument("--base-model-prediction", type=Path, required=True)
    parser.add_argument("--raw-chain-result", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--facility-template", type=Path, default=ROOT / "examples" / "consequence_facility.json")
    parser.add_argument("--bearings", default="286,106,135,45")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    field = _read_json(args.field_evidence)
    base_prediction = _read_json(args.base_model_prediction)
    raw = _read_json(args.raw_chain_result)
    receptor_path, _ = _field_paths(field)
    receptor_positions = _receptors(receptor_path)
    facility = _facility(args.facility_template, receptor_positions)
    provider_payload = copy.deepcopy(raw["data"]["source"]["provider_boundary"])
    provider_payload.update(component_id="storage", port_id="storage.out")
    weather = {
        "wind_speed_m_s": 2.7,
        "wind_from_bearing_deg": 315.0,
        "measurement_height_m": 10.0,
        "roughness_m": 0.03,
        "stability": "D",
        "relative_humidity": 0.73,
    }
    config = BackendConfig.model_validate_json(args.backend_config.read_text(encoding="utf-8"))
    backend = IsolatedBackend(config)
    pipeline = ResearchPipeline(facility, backend)
    reports: list[dict[str, Any]] = []
    for raw_bearing in args.bearings.split(","):
        bearing = float(raw_bearing.strip()) % 360.0
        provider = copy.deepcopy(provider_payload)
        provider["direction_enu"] = _bearing_vector(bearing)
        release = ResolvedLiquidRelease.model_validate_json(json.dumps(provider, allow_nan=False))
        request = _request(release, weather, len(receptor_positions), bearing)
        result = pipeline.consequences(request)
        data = result["data"]
        prediction = _prediction(base_prediction, data, release, bearing)
        comparison = build_field_model_comparison_record(field, prediction)
        reports.append({
            "bearing_deg": bearing,
            "status": comparison["status"],
            "backend_elapsed_ms": result.get("elapsed_ms"),
            "matched_row_count": comparison["matching"]["matched_row_count"],
            "matched_fraction": comparison["matching"]["matched_fraction"],
            "metrics": comparison["metrics"],
            "diagnostics": comparison["diagnostics"],
            "source_boundary_binding": comparison["source_boundary_binding"],
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
        })
    output = {
        "schema_version": "prism.external_field_orientation_sweep.v1",
        "status": "RESTRICTED_EXTERNAL_FIELD_ORIENTATION_DIAGNOSTIC",
        "event_id": field.get("event_id"),
        "field_evidence_status": field.get("status"),
        "coordinate_reference": base_prediction.get("coordinate_reference"),
        "bearing_sweep_deg": [row["bearing_deg"] for row in reports],
        "reports": reports,
        "promotion_policy": {
            "bearing_is_not_fitted": True,
            "measured_source_replay_is_not_independent_validation": True,
            "field_axis_definition_required_before_promotion": True,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "bearings": output["bearing_sweep_deg"],
        "rmse_vol_pct": {str(row["bearing_deg"]): row["metrics"]["rmse_vol_pct"] for row in reports},
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
