"""Run a public-install LH2 campaign without developer-specific model paths.

The example is diagnostic and keeps G1/G2 explicitly uncomputed. It does not
supply a real facility's provider evidence or revalidate the SLABx component.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import IsolatedBackend
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import Facility
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.public_backend import installed_backend_config


def verify_risk_arithmetic(result):
    """Recompute both risk routes directly from the preserved event atoms."""
    atoms = result["risk_atoms"]
    max_ir_error = 0.
    max_fn_error = 0.
    for receptor_id, reported in result["known_contribution_annual_ir_low_high"].items():
        for index in (0, 1):
            expected = sum(a["initiating_frequency_per_year"] * a["conditional_weight"] * a["receptor_harm_low_high"][receptor_id][index] for a in atoms)
            max_ir_error = max(max_ir_error, abs(reported[index] - expected))
    for index, curve in enumerate(result["known_contribution_expected_death_fn_low_high"]):
        ns = sorted({a["expected_deaths_low_high"][index] for a in atoms if a["expected_deaths_low_high"][index] >= 1.})
        assert curve["expected_deaths"] == ns, "F/N death-count axis differs from the atoms"
        expected = [sum(a["initiating_frequency_per_year"] * a["conditional_weight"] for a in atoms if a["expected_deaths_low_high"][index] >= n) for n in ns]
        assert len(curve["cumulative_frequency_per_year"]) == len(expected)
        max_fn_error = max([max_fn_error] + [abs(a-b) for a,b in zip(curve["cumulative_frequency_per_year"], expected)])
    assert max_ir_error < 1e-14 and max_fn_error < 1e-14
    return {"independent_ir_max_absolute_error": max_ir_error, "independent_fn_max_absolute_error": max_fn_error}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/public_lh2_backend")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    def save(name, data):
        (args.output_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    config = installed_backend_config(require_operations=("integrated_source", "consequence_chain", "facility_risk_aggregate"))
    facility = Facility.model_validate_json((ROOT / "examples/consequence_facility.json").read_text(encoding="utf-8"))
    request = json.loads((ROOT / "examples/consequence_request.json").read_text(encoding="utf-8"))
    request.update(annual_frequency_per_year=None, annual_frequency_provenance=None, initiation_intensity_per_s=None)
    request["source_input"]["nozzle"]["diameter_m"] = .01
    request["release_termination"] = {"basis": "synthetic_diagnostic_horizon", "time_s": .2, "provenance": "public installation diagnostic; not a reviewed physical termination"}
    population = [{"receptor_id": r.id, "persons": 10., "presence_probability": .5,
                   "provenance": "synthetic disjoint outdoor population"} for r in facility.receptors]
    weather = copy.deepcopy(request["weather"])
    campaign = {
        "id": "public-install-lh2", "frequency_plan": {
            "id": "public-install", "assets": [{"id": "tank-shell", "model_component_id": "storage", "profile": "TNO_PRESSURE_VESSEL",
                "classification_basis": "synthetic pressure vessel; applicability is not certified",
                "physical_scope_ids": ["example-tank"], "vessel_external_impact_or_operating_error": False}],
            "excluded_model_components": {c.id: "outside this public-install diagnostic" for c in facility.components if c.id != "storage"},
        },
        "annual_conditions": [
            {"id": "west", "annual_probability": .5, "weather": weather, "population": population, "provenance": "synthetic joint annual condition"},
            {"id": "south-west", "annual_probability": .5, "weather": {**weather, "wind_from_bearing_deg": 225.}, "population": population, "provenance": "synthetic joint annual condition"},
        ],
        "event_routes": [
            {"event_id": "public-install/tank-shell/" + loc, "branches": [{"id": "uncomputed", "probability_given_event": 1.,
                "provenance": "unsupported scope remains visible", "uncomputed_reason": "no qualified full-inventory provider history in this installation diagnostic"}]}
            for loc in ("G1", "G2")
        ] + [{"event_id": "public-install/tank-shell/G3", "branches": [{"id": "declared-release", "probability_given_event": 1.,
            "provenance": "synthetic finite release; no field isolation claim", "request": request}]}],
        "scope_provenance": "public installation and numerical coupling diagnostic; not a complete facility QRA",
    }
    save("backend.json", config.model_dump(mode="json"))
    save("facility.json", facility.model_dump(mode="json"))
    save("campaign.json", campaign)
    started = time.perf_counter()
    result = ResearchPipeline(facility, IsolatedBackend(config)).facility_risk(RiskCampaign.model_validate_json(json.dumps(campaign)))
    elapsed = (time.perf_counter() - started) * 1000.
    save("campaign_result.json", result)
    atoms = result["risk_atoms"]
    arithmetic = verify_risk_arithmetic(result)
    assert atoms, "no quantitative cases executed"
    assert result["total_facility_annual_ir_low_high"] is None
    assert result["uncomputed_cases"], "missing full-inventory histories must remain uncomputed"
    verification = {
        "schema_version": "prism.public_backend_chain_verification.v1",
        "input_origin": "synthetic", "backend_config_digest": config.digest(),
        "package_versions": {n: importlib.metadata.version(n) for n in ("prism-risk", "slabx", "slabx-lh2", "numpy", "CoolProp")},
        "risk_atom_count": len(atoms), "uncomputed_case_count": len(result["uncomputed_cases"]),
        **arithmetic, "fresh_campaign_elapsed_ms": elapsed,
        "physical_validation_claim": False, "complete_facility_qra_claim": False,
        "slabx_component_validation_reopened": False,
        "known_contribution_annual_ir_low_high": result["known_contribution_annual_ir_low_high"],
        "known_contribution_expected_death_fn_low_high": result["known_contribution_expected_death_fn_low_high"],
        "uncomputed_cases": [{k: row.get(k) for k in ("event_id", "annual_condition_id", "status", "reason", "elapsed_ms")} for row in result["uncomputed_cases"]],
        "public_dependency_chain_executed": True,
    }
    save("verification.json", verification)
    print(json.dumps(verification, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
