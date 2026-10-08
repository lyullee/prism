"""Probe pressure-equalisation stops in the pinned integrated LH2 source."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from lh2_tno.backend import BackendConfig, IsolatedBackend
from lh2_tno.source_termination import effective_source_duration


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "results" / "20261008" / "full_chain" / "backend_config.json"
REQUEST = ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json"


def main() -> None:
    config = BackendConfig.model_validate_json(CONFIG.read_text(encoding="utf-8"))
    backend = IsolatedBackend(config)
    base = json.loads(REQUEST.read_text(encoding="utf-8"))["source_input"]
    for pressure in (105000.0, 120000.0, 200000.0):
        source = copy.deepcopy(base)
        source["tank"].update(pressure_pa=pressure)
        source.update(duration_s=5.0, time_step_s=0.2)
        result = backend.run("integrated_source", source)
        steps = result["data"]["steps"]
        effective = (effective_source_duration(5.0, 0.2, [x["time_s"] for x in steps], "model_natural")
                     if steps else 0.0)
        print(json.dumps({"pressure_pa": pressure, "step_count": len(steps),
                          "last_time_s": steps[-1]["time_s"] if steps else None,
                          "effective_duration_s": effective}, ensure_ascii=False))


if __name__ == "__main__":
    main()
