"""Run the explicit finite-inventory LH2 liquid-jet operator end to end."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.contracts import Facility
from lh2_tno.pipeline import ResearchPipeline


def main() -> None:
    facility = Facility.model_validate_json((ROOT / "examples" / "consequence_facility.json").read_text(encoding="utf-8"))
    config = BackendConfig.model_validate_json((ROOT / "results" / "20261009" / "backend_config_current.json").read_text(encoding="utf-8"))
    backend = IsolatedBackend(config)
    base = json.loads((ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json").read_text(encoding="utf-8"))
    source = copy.deepcopy(base["source_input"])
    source["nozzle"]["direction_enu"] = [1.0, 0.0, -1.0]
    source["liquid_jet"] = {
        "discharge_coefficient": .62,
        "droplet_diameter_m": 5e-4,
        "d2_evaporation_constant_m2_s": 1e-7,
        "spray_half_angle_deg": 12.0,
        "liquid_velocity_fraction": 1.0,
    }
    source.update(duration_s=2.0, time_step_s=2.0)
    pool = {
        "footprint_origin": "declared_sensitivity", "radius_m": .1,
        "conductivity_w_mk": .6, "diffusivity_m2_s": 1e-7,
        "initial_temperature_k": 288.15, "domain_radius_m": 1.0,
        "radial_step_m": .05, "maximum_time_step_s": .01,
    }
    probe = backend.run("liquid_jet_source", source)
    rate = probe["data"]["steps"][0]["conservation"]["mass_in_kg_s"]
    available = rate * source["duration_s"]
    request = copy.deepcopy(base)
    request["source_input"] = source
    request["pool"] = pool
    request["available_mass_kg"] = available
    request["evaluation_times_s"] = sorted(set(request["evaluation_times_s"] + [2.0]))
    request["source_operator"] = "inventory_liquid_jet"
    request["release_termination"] = {
        "basis": "inventory_depletion", "time_s": 2.0,
        "provenance": "explicit finite-inventory liquid-jet operator; constant upstream diagnostic"
    }
    request["annual_frequency_per_year"] = None
    request["annual_frequency_provenance"] = None
    request["initiation_intensity_per_s"] = None
    result = ResearchPipeline(facility, backend).consequences(
        ConsequenceRequest.model_validate_json(json.dumps(request, allow_nan=False)))
    data = result["data"]
    assert data["full_chain_executed"] is True
    assert data["source_operator"] == "inventory_liquid_jet"
    assert data["operator_limited"] is True
    assert abs(data["mass_ledger"]["released_kg"] - available) < 1e-8
    summary = {
        "status": data["status"], "source_operator": data["source_operator"],
        "operator_limited": data["operator_limited"], "duration_s": source["duration_s"],
        "available_mass_kg": available, "released_mass_kg": data["mass_ledger"]["released_kg"],
        "mass_residual_kg": data["mass_ledger"]["end_to_end_residual_kg"],
        "physical_validation_claim": data["physical_validation_claim"],
    }
    out = ROOT / "results" / "20261009" / "inventory_liquid_jet"
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
