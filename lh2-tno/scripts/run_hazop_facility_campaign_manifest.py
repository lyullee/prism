"""Run a multi-branch HAZOP-to-facility campaign from a JSON manifest.

The manifest is the integration boundary for a digital-twin orchestrator.  It
contains the already evaluated HAZOP runtime result and the reviewed annual
condition, frequency, release-branch, and partition inputs.  This runner does
not infer missing frequencies, release sizes, branch probabilities, weather,
or population data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.hazop_campaign import (  # noqa: E402
    HazopFacilityCampaignError,
    build_hazop_facility_campaign_branches_from_manifest,
)


def _load_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HazopFacilityCampaignError(f"cannot read manifest {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise HazopFacilityCampaignError("manifest JSON root must be an object")
    return value


def run(*, manifest_path: Path, output_path: Path) -> dict[str, Any]:
    """Execute and persist one manifest-driven facility campaign."""
    manifest = _load_object(manifest_path)
    result = build_hazop_facility_campaign_branches_from_manifest(manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="JSON manifest containing runtime, annual, binding, and partition inputs",
    )
    parser.add_argument("--output", type=Path, required=True, help="JSON result path")
    args = parser.parse_args()
    try:
        result = run(manifest_path=args.manifest, output_path=args.output)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"HAZOP facility campaign failed: {error}") from error
    campaign = result.get("campaign")
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "facility_id": result.get("facility_id"),
                "branch_count": len(result.get("branch_campaigns", [])),
                "risk_atom_count": (
                    len(campaign.get("risk_atoms", []))
                    if isinstance(campaign, Mapping)
                    else None
                ),
                "facility_qra_claim": (
                    campaign.get("complete_facility_qra_claim")
                    if isinstance(campaign, Mapping)
                    else None
                ),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
