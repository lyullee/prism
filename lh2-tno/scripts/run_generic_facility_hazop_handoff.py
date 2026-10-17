"""Run the generic outdoor-LH2 forecast HAZOP-to-quantitative handoff.

This is a facility-neutral digital-twin seam.  Each forecast frame carries an
explicit component and operating mode; the reviewed HAZOP table selects a
scenario when a declared deviation is reached.  The resulting worklist names
the provider-release, literature-frequency, SLABx-LH2, and facility-condition
inputs required for quantitative evaluation.  It deliberately does not
invent a release, learn a frequency, run consequence physics, or promote a
facility IR/F-N result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.forecast_handoff import build_forecast_quantitative_handoff  # noqa: E402
from lh2_tno.hazop_forecast import run_hazop_forecast_risk_scan  # noqa: E402


SCHEMA = "prism.generic_outdoor_facility_hazop_handoff.v1"


def _load(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def _frames(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get("frames")
    if not isinstance(value, list) or not value or not all(isinstance(row, Mapping) for row in value):
        raise ValueError("forecast input must be a non-empty array of frame objects")
    return list(value)


def build_handoff(frames: Any, tables: Mapping[str, Any]) -> dict[str, Any]:
    """Build a generic multi-component HAZOP scan and quantitative worklist."""
    rows = _frames(frames)
    if not isinstance(tables, Mapping) or not tables:
        raise ValueError("tables must be a non-empty component-keyed object")
    component_ids = sorted(str(row.get("component_id") or "") for row in rows)
    component_ids = sorted(set(component_ids))
    if not component_ids or any(not value for value in component_ids):
        raise ValueError("every forecast frame requires component_id")
    if set(tables) != set(component_ids):
        raise ValueError(
            "tables must cover exactly the forecast components; "
            f"expected={component_ids}, actual={sorted(tables)}"
        )
    facility_ids = {str(row.get("facility_id") or "") for row in rows}
    if len(facility_ids) != 1 or not next(iter(facility_ids)):
        raise ValueError("all forecast frames must use one non-empty facility_id")
    facility_id = next(iter(facility_ids))
    scan = run_hazop_forecast_risk_scan(
        facility_id=facility_id,
        tables_by_component={component_id: tables[component_id] for component_id in component_ids},
        forecast_frames=rows,
        expected_component_ids=component_ids,
    )
    handoff = build_forecast_quantitative_handoff(scan)
    return {
        "schema_version": SCHEMA,
        "facility_id": facility_id,
        "component_ids": component_ids,
        "operating_modes": sorted({str(row.get("operating_mode")) for row in rows}),
        "forecast_time_grid_s": sorted({float(row["forecast_time_s"]) for row in rows}),
        "scan": scan,
        "quantitative_handoff": handoff,
        "policy": {
            "operating_mode_taken_from_forecast_input": True,
            "operating_mode_inferred": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "This record proves the generic facility state -> operating-mode -> "
            "HAZOP scenario -> quantitative request connection. Each request "
            "remains withheld until reviewed provider, frequency, SLABx-LH2 and "
            "facility-condition evidence is supplied."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_handoff(_load(args.frames), _load(args.tables))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scan = result["scan"]
    handoff = result["quantitative_handoff"]
    print(json.dumps({
        "status": result["schema_version"],
        "facility_id": result["facility_id"],
        "component_count": len(result["component_ids"]),
        "trigger_count": scan["trigger_count"],
        "withheld_count": scan["withheld_count"],
        "quantitative_request_count": handoff["summary"]["request_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
