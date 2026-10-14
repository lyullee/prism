"""Build a source-to-event literature frequency provenance report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyEvent, FrequencyPlan  # noqa: E402
from lh2_tno.frequency_provenance import build_frequency_provenance_report  # noqa: E402
from lh2_tno.legacy_frequency_bridge import attach_precomputed_events  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trace reviewed frequency sources and uncertainty from a plan to generated LH2 events."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument(
        "--precomputed-events",
        type=Path,
        help="optional JSON event catalogue produced by an external generator; rows are attached exactly",
    )
    parser.add_argument(
        "--precomputed-events-provenance",
        help="explicit source/handoff provenance required with --precomputed-events",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = EquipmentManifest.from_json(args.manifest)
        plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
        if args.precomputed_events is not None:
            if not args.precomputed_events_provenance or not args.precomputed_events_provenance.strip():
                raise ValueError(
                    "--precomputed-events-provenance is required with --precomputed-events"
                )
            raw_events = json.loads(args.precomputed_events.read_text(encoding="utf-8"))
            if isinstance(raw_events, dict):
                raw_events = raw_events.get("events")
            if not isinstance(raw_events, list) or not raw_events:
                raise ValueError("precomputed event JSON must contain a nonempty events array")
            # JSON arrays are converted to the contract's tuple fields by the
            # JSON validator; ``model_validate(dict)`` intentionally remains
            # strict for in-process callers.
            events = tuple(
                FrequencyEvent.model_validate_json(json.dumps(row, allow_nan=False))
                for row in raw_events
            )
            plan = attach_precomputed_events(
                plan,
                events,
                provenance=args.precomputed_events_provenance,
            )
        report = build_frequency_provenance_report(manifest, plan)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"frequency provenance input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "profile_count": len(report["profile_provenance"]),
        "event_count": len(report["generated_events"]),
        "catalogue_digest": report["catalogue"]["digest"],
        "event_generation_mode": report["frequency_plan"]["event_generation_mode"],
        "external_frequency_override_used": report["policy"]["external_frequency_override_used"],
        "field_frequency_collection_used": report["policy"]["field_frequency_collection_used"],
        "sensor_frequency_learning_used": report["policy"]["sensor_frequency_learning_used"],
    }, ensure_ascii=False))
    return 0 if report["status"] != "FAILED_PROVENANCE_INTEGRITY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

