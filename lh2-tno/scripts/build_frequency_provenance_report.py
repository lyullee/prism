"""Build a source-to-event literature frequency provenance report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan  # noqa: E402
from lh2_tno.frequency_provenance import build_frequency_provenance_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trace reviewed frequency sources and uncertainty from a plan to generated LH2 events."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = EquipmentManifest.from_json(args.manifest)
        plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
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
        "field_frequency_collection_used": report["policy"]["field_frequency_collection_used"],
        "sensor_frequency_learning_used": report["policy"]["sensor_frequency_learning_used"],
    }, ensure_ascii=False))
    return 0 if report["status"] != "FAILED_PROVENANCE_INTEGRITY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

