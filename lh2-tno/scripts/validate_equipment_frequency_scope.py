"""Audit the explicit literature-frequency scope of a generic equipment manifest.

This is deliberately a separate step from consequence evaluation.  A provider
manifest may be structurally executable while its initiating-event frequency
scope is still missing.  The audit therefore requires a reviewed
``FrequencyPlan`` and checks that every facility component is selected exactly
once or is explicitly excluded with a reason.  It never infers a profile from
component kind, pressure, diameter or name.

Examples
--------
  python scripts/validate_equipment_frequency_scope.py \
      --manifest examples/equipment_manifest.json \
      --frequency-plan examples/equipment_frequency_plan.json \
      --output frequency_scope_audit.json

  # Optional external event rows (rate arithmetic remains external):
  python scripts/validate_equipment_frequency_scope.py \
      --manifest examples/generic_lh2_full_scope_manifest.json \
      --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json \
      --precomputed-events examples/external_frequency_event_catalogue.json \
      --precomputed-events-provenance "external bridge; source digest pinned" \
      --output frequency_scope_external_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Keep the source checkout directly runnable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyEvent, FrequencyPlan
from lh2_tno.frequency_scope import audit_frequency_scope
from lh2_tno.legacy_frequency_bridge import attach_precomputed_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--precomputed-events", type=Path)
    parser.add_argument("--precomputed-events-provenance")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = EquipmentManifest.from_json(args.manifest)
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    if args.precomputed_events is not None:
        if not args.precomputed_events_provenance or not args.precomputed_events_provenance.strip():
            raise SystemExit("--precomputed-events-provenance is required with --precomputed-events")
        raw_events = json.loads(args.precomputed_events.read_text(encoding="utf-8"))
        if isinstance(raw_events, dict):
            raw_events = raw_events.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raise SystemExit("precomputed event JSON must contain a nonempty events array")
        events = tuple(
            FrequencyEvent.model_validate_json(json.dumps(row, allow_nan=False))
            for row in raw_events
        )
        plan = attach_precomputed_events(
            plan, events, provenance=args.precomputed_events_provenance
        )
    result = audit_frequency_scope(manifest, plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "generated_event_count": result["generated_event_count"],
        "event_generation_mode": result["event_generation_mode"],
        "frequency_arithmetic_owner": result["frequency_arithmetic_owner"],
        "output": str(args.output),
        "blocking_reasons": result["blocking_reasons"],
    }, ensure_ascii=False))
    return 0 if result["status"] == "EXECUTABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
