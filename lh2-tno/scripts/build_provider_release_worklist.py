"""Build a fail-closed provider packet worklist from a frequency plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan
from lh2_tno.provider_worklist import build_provider_release_worklist


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--frequency-plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest = EquipmentManifest.from_json(args.manifest)
    plan = FrequencyPlan.model_validate_json(
        args.frequency_plan.read_text(encoding="utf-8")
    )
    result = build_provider_release_worklist(manifest, plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "generated_event_count": result["generated_event_count"],
        "provider_packet_count": result["provider_packet_count"],
        "status_counts": result.get("status_counts", {}),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
