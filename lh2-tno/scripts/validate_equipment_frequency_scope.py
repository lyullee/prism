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
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Keep the source checkout directly runnable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan
from lh2_tno.frequency_scope import audit_frequency_scope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = EquipmentManifest.from_json(args.manifest)
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    result = audit_frequency_scope(manifest, plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "facility_id": result["facility_id"],
        "generated_event_count": result["generated_event_count"],
        "output": str(args.output),
        "blocking_reasons": result["blocking_reasons"],
    }, ensure_ascii=False))
    return 0 if result["status"] == "EXECUTABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
