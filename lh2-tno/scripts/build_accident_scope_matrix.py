"""Build a fail-closed major-accident coverage matrix for one campaign."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.accident_scope import (  # noqa: E402
    MAJOR_ACCIDENT_FAMILIES,
    build_accident_scope_matrix,
)
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit major LH2 accident-family coverage without inferring missing cases."
    )
    parser.add_argument("--equipment-manifest", type=Path, required=True)
    parser.add_argument("--risk-campaign", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument(
        "--provider-worklist",
        type=Path,
        help="optional provider worklist for event/family alignment auditing",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--required-family",
        action="append",
        dest="required_families",
        choices=MAJOR_ACCIDENT_FAMILIES,
        help="Limit the audit to one or more declared families; repeat the option.",
    )
    args = parser.parse_args()

    try:
        manifest = EquipmentManifest.from_json(args.equipment_manifest)
        campaign = RiskCampaign.model_validate_json(
            args.risk_campaign.read_text(encoding="utf-8")
        )
        result = json.loads(args.result.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("campaign result must be a JSON object")
        families = tuple(args.required_families or MAJOR_ACCIDENT_FAMILIES)
        worklist = (
            json.loads(args.provider_worklist.read_text(encoding="utf-8"))
            if args.provider_worklist
            else None
        )
        if worklist is not None and not isinstance(worklist, dict):
            raise ValueError("provider worklist must be a JSON object")
        matrix = build_accident_scope_matrix(
            campaign,
            result,
            manifest,
            required_families=families,
            provider_worklist=worklist,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise SystemExit(f"accident scope matrix input error: {error}") from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE" if matrix["matrix_complete"] else "INCOMPLETE_DECLARED_SCOPE",
                "output": str(args.output),
                "family_count": len(matrix["rows"]),
                "blocking_reason_count": len(matrix["blocking_reasons"]),
                "facility_total_risk_available": matrix["facility_total_risk_available"],
                "provider_worklist_alignment": (
                    matrix["provider_worklist_alignment"]["status"]
                    if matrix["provider_worklist_alignment"] is not None
                    else None
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0 if matrix["matrix_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
