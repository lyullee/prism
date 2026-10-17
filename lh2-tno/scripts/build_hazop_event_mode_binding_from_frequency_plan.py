"""Build an explicit HAZOP event-mode binding from a reviewed frequency plan.

The frequency plan is the source of the operating-mode and HAZOP scenario
labels for a generic diagnostic campaign.  This utility deliberately performs
no inference: every event must already contain ``operating_mode`` and
``hazop_scenario_id`` and the release mode must be explicit.  The output is
accepted by ``run_native_provider_facility_campaign.py`` and can therefore be
checked against the exact event/component/release identity at runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def build_binding(frequency_plan: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    events = frequency_plan.get("precomputed_events")
    if not isinstance(events, list) or not events:
        raise ValueError("frequency plan must contain a non-empty precomputed_events array")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"precomputed_events[{index}] must be an object")
        event_id = event.get("id")
        component_id = event.get("model_component_id")
        release = event.get("release")
        release_mode = release.get("mode") if isinstance(release, dict) else None
        operating_mode = event.get("operating_mode")
        scenario_id = event.get("hazop_scenario_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"precomputed_events[{index}] is missing id")
        if event_id in seen:
            raise ValueError(f"duplicate frequency event id: {event_id}")
        seen.add(event_id)
        for field, value in (
            ("model_component_id", component_id),
            ("release.mode", release_mode),
            ("operating_mode", operating_mode),
            ("hazop_scenario_id", scenario_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"event {event_id} is missing explicit {field}")
        rows.append(
            {
                "event_id": event_id,
                "component_id": component_id,
                "profile": event.get("profile"),
                "release_mode": release_mode,
                "annual_frequency_per_year": event.get("annual_frequency_per_year"),
                "status": "MODE_PRESENT",
                "operating_mode": operating_mode,
                "hazop_scenario_id": scenario_id,
                "binding_source": "reviewed frequency plan; no mode inference",
                "binding_errors": [],
                "mode_inference_performed": False,
                "scenario_inference_performed": False,
                "physical_validation_claim": False,
            }
        )

    return {
        "schema_version": "prism.hazop_event_mode_binding.v1",
        "status": "HAZOP_EVENT_MODE_BINDING_COMPLETE",
        "event_count": len(rows),
        "mode_bound_event_count": len(rows),
        "mode_required_event_count": 0,
        "scenario_id_required_event_count": 0,
        "mode_conflict_event_count": 0,
        "provider_event_count": len(rows),
        "orphan_mode_binding_count": 0,
        "event_rows": rows,
        "errors": [],
        "policy": {
            "matching": "exact event_id/component_id/release_mode",
            "mode_source": "frequency_plan.operating_mode",
            "scenario_source": "frequency_plan.hazop_scenario_id",
            "mode_inference_performed": False,
            "scenario_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
        "source_frequency_plan": str(source_path).replace("\\", "/"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binding = build_binding(_load(args.frequency_plan), source_path=args.frequency_plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(binding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": binding["status"], "event_count": binding["event_count"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
