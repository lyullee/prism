"""Run the explicit equipment -> HAZOP -> quantitative campaign boundary.

The input JSON contains the equipment manifest, observed/predicted runtime
frames, HAZOP tables, the provider-bound HAZOP runtime result, annual weather
and population conditions, reviewed frequency/release bindings, branch
partitions, and an explicit qualitative-to-quantitative scenario crosswalk.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_hazop_campaign import (  # noqa: E402
    build_equipment_hazop_quantitative_campaign,
)


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read manifest {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise ValueError("integration manifest JSON root must be an object")
    return value


def run(*, manifest_path: Path, output_path: Path, now_s: float) -> dict[str, Any]:
    manifest = _load(manifest_path)
    required = (
        "equipment_manifest",
        "runtime_frames",
        "hazop_table_set",
        "runtime_result",
        "annual_conditions",
        "scenario_bindings",
        "branch_probabilities",
        "branch_partition_groups",
        "scenario_identity_crosswalk",
    )
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError("integration manifest is missing: " + ", ".join(missing))
    result = build_equipment_hazop_quantitative_campaign(
        equipment_manifest=manifest["equipment_manifest"],
        runtime_frames=manifest["runtime_frames"],
        hazop_table_set=manifest["hazop_table_set"],
        runtime_result=manifest["runtime_result"],
        annual_conditions=manifest["annual_conditions"],
        scenario_bindings=manifest["scenario_bindings"],
        branch_probabilities=manifest["branch_probabilities"],
        branch_partition_groups=manifest["branch_partition_groups"],
        scenario_identity_crosswalk=manifest["scenario_identity_crosswalk"],
        now_s=now_s,
        expected_component_ids=manifest.get("expected_component_ids", ()),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--now-s", type=float, required=True)
    args = parser.parse_args()
    try:
        result = run(manifest_path=args.manifest, output_path=args.output, now_s=args.now_s)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"equipment HAZOP quantitative campaign failed: {error}") from error
    campaign = result.get("campaign")
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "facility_id": result.get("facility_id"),
                "identity_crosswalk_status": (
                    result.get("scenario_identity_crosswalk", {}).get("status")
                    if isinstance(result.get("scenario_identity_crosswalk"), Mapping)
                    else None
                ),
                "risk_atom_count": (
                    len(campaign.get("risk_atoms", []))
                    if isinstance(campaign, Mapping)
                    else 0
                ),
                "facility_qra_claim": (
                    campaign.get("complete_facility_qra_claim")
                    if isinstance(campaign, Mapping)
                    else False
                ),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.get("status") == "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BUILT_OPERATOR_LIMITED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
