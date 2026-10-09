"""Export the declared LH2 outdoor major-accident scenario catalogue."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.accident_scenario_catalog import (  # noqa: E402
    ACCIDENT_SCENARIO_CATALOG_SCHEMA,
    accident_scenario_catalog,
    audit_catalog_manifest,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the fail-closed PRISM LH2 major-accident scenario catalogue."
    )
    parser.add_argument("--equipment-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = {
        "schema": ACCIDENT_SCENARIO_CATALOG_SCHEMA,
        "scope": "outdoor_major_accidents",
        "scenarios": list(accident_scenario_catalog()),
        "physical_validation_claim": False,
        "promotion_policy": (
            "definitions identify required provider evidence; they do not create "
            "accident packets or promote synthetic diagnostics"
        ),
    }
    if args.equipment_manifest is not None:
        manifest = EquipmentManifest.from_json(args.equipment_manifest)
        payload["manifest_audit"] = audit_catalog_manifest(
            {"id": component.id, "kind": component.kind}
            for component in manifest.components
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "CATALOG_EXPORTED",
        "schema": payload["schema"],
        "scenario_count": len(payload["scenarios"]),
        "output": str(args.output),
        "manifest_audit": "manifest_audit" in payload,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

