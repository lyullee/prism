"""Fresh end-to-end check of model-natural source termination."""
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

OUT = ROOT / "results" / "20261009" / "natural_termination"


def main() -> None:
    facility = Facility.model_validate_json((ROOT / "examples" / "consequence_facility.json").read_text(encoding="utf-8"))
    request = json.loads((ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json").read_text(encoding="utf-8"))
    request["source_input"]["tank"]["pressure_pa"] = 200000.0
    request["source_input"].update(duration_s=5.0, time_step_s=0.2)
    request["evaluation_times_s"] = sorted(set(request["evaluation_times_s"] + [5.0]))
    request["source_duration_mode"] = "model_natural"
    request["release_termination"] = {
        "basis": "model_pressure_equalization", "time_s": 5.0,
        "provenance": "pinned integrated LH2 source pressure-equalisation stop"
    }
    request["annual_frequency_per_year"] = None
    request["annual_frequency_provenance"] = None
    request["initiation_intensity_per_s"] = None
    request_model = ConsequenceRequest.model_validate_json(json.dumps(request, allow_nan=False))
    result = ResearchPipeline(
        facility,
        IsolatedBackend(BackendConfig.model_validate_json(
            (ROOT / "results" / "20261008" / "full_chain" / "backend_config.json").read_text(encoding="utf-8")))
    ).consequences(request_model)
    data = result["data"]
    source = data["source"]
    assert data["full_chain_executed"] is True
    assert source["source_duration_mode"] == "model_natural"
    assert source["natural_termination_detected"] is True
    assert source["effective_duration_s"] == 0.2
    assert data["mass_ledger"]["end_to_end_residual_kg"] < 1e-8
    summary = {"status": data["status"], "requested_duration_s": source["requested_duration_s"],
               "effective_duration_s": source["effective_duration_s"],
               "step_count": len(source["steps"]),
               "mass_residual_kg": data["mass_ledger"]["end_to_end_residual_kg"],
               "physical_validation_claim": data["physical_validation_claim"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
