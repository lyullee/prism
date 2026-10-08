"""Run one explicit 600 s inventory-release chain.

This is a reproducible provider-integration diagnostic, not a site QRA.  The
synthetic tank and wall heat input are deliberately recorded in the output.
If the saved backend pin is stale, refreshing it requires an explicit flag and
the old/new tree digests are written to the verification record.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.contracts import Facility
from lh2_tno.frequency import FrequencyAsset, FrequencyPlan, bind_event, generate_events
from lh2_tno.pipeline import ResearchPipeline


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _backend_config(path: Path, allow_pin_refresh: bool) -> tuple[BackendConfig, list[dict]]:
    raw = _read(path)
    refreshed = []
    for package in raw["packages"]:
        current = tree_digest(Path(package["root"]))
        if current != package["sha256"]:
            if not allow_pin_refresh:
                raise ValueError(
                    f"backend pin mismatch for {package['name']}; pass --allow-pin-refresh "
                    "to record the explicit old/new digest"
                )
            refreshed.append({"name": package["name"], "declared": package["sha256"], "observed": current})
            package["sha256"] = current
    return BackendConfig.model_validate_json(json.dumps(raw, allow_nan=False)), refreshed


def build_request() -> tuple[Facility, object, ConsequenceRequest, dict]:
    facility_data = _read(ROOT / "examples" / "consequence_facility.json")
    # The facility is a synthetic long-horizon diagnostic only.  Its volume
    # must match the provider input; it is not a reviewed plant inventory.
    facility_data["components"][0]["parameters_si"]["volume_m3"] = 10.0
    facility = Facility.model_validate_json(json.dumps(facility_data, allow_nan=False))
    asset = FrequencyAsset(
        id="storage",
        model_component_id="storage",
        profile="TNO_PRESSURE_VESSEL",
        classification_basis="synthetic long-horizon provider diagnostic",
        physical_scope_ids=("storage-shell-long-horizon",),
        vessel_external_impact_or_operating_error=False,
    )
    plan = FrequencyPlan(
        id="long-horizon-probe",
        assets=(asset,),
        excluded_model_components={
            component.id: "diagnostic excludes unrelated component"
            for component in facility.components
            if component.id != "storage"
        },
    )
    event = generate_events(facility, plan)[1]  # TNO vessel G2 inventory over 600 s.

    request_data = _read(ROOT / "examples" / "consequence_request.json")
    source = request_data["source_input"]
    source["tank"]["volume_m3"] = 10.0
    source["tank"]["wall_heat_input_w"] = 100000.0
    source["duration_s"] = 600.0
    source["time_step_s"] = 60.0
    request_data["available_mass_kg"] = 1000.0
    request_data["evaluation_times_s"] = [0.0, 1.0, 2.0, 20.0, 600.0]
    request_data["source_operator"] = "inventory_over_600s"
    request_data["release_termination"] = {
        "basis": "inventory_over_600s",
        "time_s": 600.0,
        "provenance": "provider returned the complete declared 600 s history",
    }
    request_data.update(
        annual_frequency_per_year=None,
        annual_frequency_provenance=None,
        initiation_intensity_per_s=None,
    )
    request = bind_event(ConsequenceRequest.model_validate_json(json.dumps(request_data, allow_nan=False)), event)
    return facility, plan, request, {"event": event.model_dump(mode="json"), "source_input": source}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend-config",
        type=Path,
        default=ROOT / "results" / "20261009" / "backend_config_current.json",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "20261009" / "long_horizon_inventory")
    parser.add_argument("--allow-pin-refresh", action="store_true")
    args = parser.parse_args(argv)

    config, refreshed_pins = _backend_config(args.backend_config, args.allow_pin_refresh)
    facility, plan, request, inputs = build_request()
    result = ResearchPipeline(facility, IsolatedBackend(config)).consequences(request)
    data = result["data"]
    source = data["source"]
    if data["status"] != "END_TO_END_DIAGNOSTIC_EXECUTED" or data["full_chain_executed"] is not True:
        raise ValueError("long-horizon source did not complete the end-to-end diagnostic chain")
    if source.get("effective_duration_s") != 600.0:
        raise ValueError("provider history did not cover the declared 600 s duration")
    residual = data["mass_ledger"]["end_to_end_residual_kg"]
    if abs(residual) > 1e-8:
        raise ValueError("long-horizon mass ledger did not close")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "request.json").write_text(
        json.dumps({"facility": facility.model_dump(mode="json"), "plan": plan.model_dump(mode="json"), **inputs, "request": request.model_dump(mode="json")},
                   ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (args.output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    verification = {
        "status": "EXECUTED_DIAGNOSTIC_ONLY",
        "event_id": inputs["event"]["id"],
        "provider_history_duration_s": source["effective_duration_s"],
        "provider_interval_count": len(source["steps"]),
        "elapsed_ms": result["elapsed_ms"],
        "end_to_end_mass_residual_kg": residual,
        "operator_limited": data["operator_limited"],
        "facility_validation": data["facility_validation"],
        "physical_validation_claim": data["physical_validation_claim"],
        "synthetic_inputs": {
            "tank_volume_m3": 10.0,
            "wall_heat_input_w": 100000.0,
            "available_mass_kg": 1000.0,
            "meaning": "provider integration diagnostic; not a reviewed site inventory or measured heat load",
        },
        "backend_config_digest": config.digest(),
        "refreshed_backend_pins": refreshed_pins,
    }
    (args.output / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
