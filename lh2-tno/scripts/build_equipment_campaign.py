"""Compile a generic equipment manifest into an explicit RiskCampaign.

The command only compiles declarations.  It does not run the external physics
backend.  Use the normal PRISM campaign command with the emitted JSON to run
the campaign after the provider and backend pins have been reviewed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.campaign import AnnualCondition
from lh2_tno.campaign_template import build_equipment_campaign, build_equipment_campaign_from_catalog
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    requests = parser.add_mutually_exclusive_group(required=True)
    requests.add_argument("--request-template", type=Path)
    requests.add_argument("--request-catalog", type=Path,
                          help="JSON array or {'templates': [...]} of consequence request templates")
    parser.add_argument("--annual-conditions", type=Path, required=True)
    parser.add_argument("--scope-provenance", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = EquipmentManifest.from_json(args.manifest)
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    if args.request_template:
        request_templates = (ConsequenceRequest.model_validate_json(
            args.request_template.read_text(encoding="utf-8")
        ),)
    else:
        catalog = json.loads(args.request_catalog.read_text(encoding="utf-8"))
        if isinstance(catalog, dict):
            catalog = catalog.get("templates")
        if not isinstance(catalog, list):
            raise ValueError("request catalog must be a JSON array or an object with a templates array")
        request_templates = tuple(
            ConsequenceRequest.model_validate_json(json.dumps(item, allow_nan=False))
            for item in catalog
        )
    rows = json.loads(args.annual_conditions.read_text(encoding="utf-8"))
    conditions = tuple(
        AnnualCondition.model_validate_json(json.dumps(row, allow_nan=False))
        for row in rows
    )
    if args.request_template:
        campaign = build_equipment_campaign(
            manifest, plan, request_templates[0], conditions,
            scope_provenance=args.scope_provenance,
        )
    else:
        campaign = build_equipment_campaign_from_catalog(
            manifest, plan, request_templates, conditions,
            scope_provenance=args.scope_provenance,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(campaign.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    matched = sum(
        branch.request is not None
        for route in campaign.event_routes
        for branch in route.branches
    )
    print(json.dumps({
        "status": "COMPILED",
        "output": str(args.output),
        "event_count": len(campaign.event_routes),
        "matched_request_branch_count": matched,
        "uncomputed_branch_count": len(campaign.event_routes) - matched,
        "physics_executed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
