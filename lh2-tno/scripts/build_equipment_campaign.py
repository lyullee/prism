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

from lh2_tno.campaign import AnnualCondition, PhysicalValidationEvidence, RiskCampaign
from lh2_tno.campaign_template import (
    RequestBranchTemplate,
    build_equipment_campaign,
    build_equipment_campaign_from_branch_catalog,
    build_equipment_campaign_from_catalog,
    build_equipment_campaign_from_provider_branch_catalog,
    build_equipment_campaign_from_provider_catalog,
    build_equipment_campaign_from_provider_worklist,
)
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan
from lh2_tno.provider_release import (
    ProviderReleaseContractError,
    load_provider_emergency_relief_catalog,
    load_provider_release_branch_catalog,
    load_provider_release_catalog,
    load_provider_release_set_branch_catalog,
    load_provider_release_set_catalog,
)
from lh2_tno.provider_packet_promotion import (
    ProviderPacketPromotionError,
    load_provider_packet_evidence_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    requests = parser.add_mutually_exclusive_group(required=True)
    requests.add_argument("--request-template", type=Path)
    requests.add_argument("--request-catalog", type=Path,
                          help="JSON array or {'templates': [...]} of consequence request templates")
    requests.add_argument(
        "--request-branch-catalog", type=Path,
        help="JSON array or {'branches': [...]} of explicit conditional provider/barrier branches",
    )
    requests.add_argument(
        "--provider-release-catalog", type=Path,
        help="explicit prism.resolved_release.v1 packet catalog from the equipment model",
    )
    requests.add_argument(
        "--provider-release-branch-catalog", type=Path,
        help="explicit provider packets wrapped with conditional isolation/barrier branches",
    )
    requests.add_argument(
        "--provider-worklist-only", action="store_true",
        help="compile every frequency event as an explicit missing-provider-packet branch",
    )
    parser.add_argument(
        "--release-kind", choices=("accidental_leak", "emergency_relief", "two_sided_rupture"),
        default="accidental_leak",
        help="provider packet family; two_sided_rupture uses a dedicated release-set catalog",
    )
    parser.add_argument(
        "--request-defaults", type=Path,
        help="reviewed consequence context JSON; required with --provider-release-catalog",
    )
    parser.add_argument(
        "--provider-evidence-catalog",
        type=Path,
        help=(
            "optional prism.provider_packet_evidence.v1 object/array to attach to the compiled campaign; "
            "missing events remain unqualified"
        ),
    )
    parser.add_argument(
        "--allow-distinct-event-evidence",
        action="store_true",
        help=(
            "allow multiple qualification rows for one event when their exact "
            "component/port/source/result packet identities differ (conditional branches)"
        ),
    )
    parser.add_argument(
        "--physical-validation-evidence",
        type=Path,
        help=(
            "optional prism physical-validation evidence JSON; independent validation requires an evidence ID and SHA-256"
        ),
    )
    parser.add_argument("--annual-conditions", type=Path, required=True)
    parser.add_argument("--scope-provenance", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = EquipmentManifest.from_json(args.manifest)
    plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding="utf-8"))
    if (args.provider_release_catalog or args.provider_release_branch_catalog) and not args.request_defaults:
        parser.error("provider release catalogs require --request-defaults")
    if args.request_defaults and not (args.provider_release_catalog or args.provider_release_branch_catalog):
        parser.error("--request-defaults is valid only with a provider release catalog")

    if args.request_template:
        request_templates = (ConsequenceRequest.model_validate_json(
            args.request_template.read_text(encoding="utf-8")
        ),)
    elif args.request_catalog:
        catalog = json.loads(args.request_catalog.read_text(encoding="utf-8"))
        if isinstance(catalog, dict):
            catalog = catalog.get("templates")
        if not isinstance(catalog, list):
            raise ValueError("request catalog must be a JSON array or an object with a templates array")
        request_templates = tuple(
            ConsequenceRequest.model_validate_json(json.dumps(item, allow_nan=False))
            for item in catalog
        )
    elif args.request_branch_catalog:
        catalog = json.loads(args.request_branch_catalog.read_text(encoding="utf-8"))
        if isinstance(catalog, dict):
            catalog = catalog.get("branches")
        if not isinstance(catalog, list):
            raise ValueError("branch request catalog must be a JSON array or an object with a branches array")
        request_branches = tuple(
            RequestBranchTemplate.model_validate_json(json.dumps(item, allow_nan=False))
            for item in catalog
        )
    elif args.provider_release_branch_catalog:
        try:
            provider_release_branches = (
                load_provider_release_set_branch_catalog(args.provider_release_branch_catalog)
                if args.release_kind == "two_sided_rupture"
                else load_provider_release_branch_catalog(args.provider_release_branch_catalog)
            )
            defaults = json.loads(args.request_defaults.read_text(encoding="utf-8"))
            if not isinstance(defaults, dict):
                raise ProviderReleaseContractError("request defaults must be a JSON object")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderReleaseContractError) as error:
            raise SystemExit(f"provider branch campaign input error: {error}") from error
    elif not args.provider_worklist_only:
        try:
            loader = {
                "accidental_leak": load_provider_release_catalog,
                "emergency_relief": load_provider_emergency_relief_catalog,
                "two_sided_rupture": load_provider_release_set_catalog,
            }[args.release_kind]
            provider_releases = loader(args.provider_release_catalog)
            defaults = json.loads(args.request_defaults.read_text(encoding="utf-8"))
            if not isinstance(defaults, dict):
                raise ProviderReleaseContractError("request defaults must be a JSON object")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderReleaseContractError) as error:
            raise SystemExit(f"provider campaign input error: {error}") from error
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
    elif args.request_catalog:
        campaign = build_equipment_campaign_from_catalog(
            manifest, plan, request_templates, conditions,
            scope_provenance=args.scope_provenance,
        )
    elif args.request_branch_catalog:
        campaign = build_equipment_campaign_from_branch_catalog(
            manifest, plan, request_branches, conditions,
            scope_provenance=args.scope_provenance,
        )
    elif args.provider_release_branch_catalog:
        campaign = build_equipment_campaign_from_provider_branch_catalog(
            manifest,
            plan,
            provider_release_branches,
            defaults,
            conditions,
            scope_provenance=args.scope_provenance,
        )
    elif args.provider_release_catalog or args.provider_release_branch_catalog:
        campaign = build_equipment_campaign_from_provider_catalog(
            manifest,
            plan,
            provider_releases,
            defaults,
            conditions,
            scope_provenance=args.scope_provenance,
        )
    else:
        campaign = build_equipment_campaign_from_provider_worklist(
            manifest,
            plan,
            conditions,
            scope_provenance=args.scope_provenance,
        )
    provider_evidence = ()
    if args.provider_evidence_catalog:
        try:
            evidence = load_provider_packet_evidence_catalog(
                args.provider_evidence_catalog,
                allow_distinct_event_id_packets=args.allow_distinct_event_evidence,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderPacketPromotionError) as error:
            raise SystemExit(f"provider packet evidence input error: {error}") from error
        generated_event_ids = {route.event_id for route in campaign.event_routes}
        unknown = sorted({row.event_id for row in evidence} - generated_event_ids)
        if unknown:
            raise SystemExit(
                "provider packet evidence references unknown generated events: "
                + ", ".join(unknown)
            )
        provider_evidence = evidence
    physical_validation = PhysicalValidationEvidence()
    if args.physical_validation_evidence:
        try:
            physical_validation = PhysicalValidationEvidence.model_validate_json(
                args.physical_validation_evidence.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise SystemExit(f"physical validation evidence input error: {error}") from error
    if provider_evidence or args.physical_validation_evidence:
        campaign = RiskCampaign.model_validate({
            **campaign.model_dump(),
            "provider_packet_evidence": provider_evidence,
            "physical_validation_evidence": physical_validation,
        })
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
    uncomputed = sum(
        branch.request is None
        for route in campaign.event_routes
        for branch in route.branches
    )
    print(json.dumps({
        "status": "COMPILED",
        "output": str(args.output),
        "event_count": len(campaign.event_routes),
        "matched_request_branch_count": matched,
        "uncomputed_branch_count": uncomputed,
        "physics_executed": False,
        "input_mode": (
            "request_template" if args.request_template else
            "request_catalog" if args.request_catalog else
            "request_branch_catalog" if args.request_branch_catalog else
            "provider_worklist_only" if args.provider_worklist_only else
            "provider_release_branch_catalog" if args.provider_release_branch_catalog else
            "provider_release_catalog"
        ),
        "provider_release_kind": (
            args.release_kind
            if args.provider_release_catalog or args.provider_release_branch_catalog
            else None
        ),
        "provider_packet_evidence_count": len(campaign.provider_packet_evidence),
        "provider_packet_evidence_attached": bool(campaign.provider_packet_evidence),
        "physical_validation_evidence_status": campaign.physical_validation_evidence.status,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
