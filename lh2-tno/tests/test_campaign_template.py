import json
from pathlib import Path

from lh2_tno.campaign import AnnualCondition
from lh2_tno.campaign_template import build_equipment_campaign
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan


def _campaign_inputs():
    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(root / "examples/equipment_manifest.json")
    plan = FrequencyPlan.model_validate_json(
        (root / "examples/equipment_frequency_plan.json").read_text(encoding="utf-8")
    )
    request = ConsequenceRequest.model_validate_json(
        (root / "examples/equipment_consequence_template.json").read_text(encoding="utf-8")
    )
    rows = json.loads((root / "examples/equipment_annual_conditions.json").read_text(encoding="utf-8"))
    conditions = tuple(
        AnnualCondition.model_validate_json(json.dumps(row, allow_nan=False))
        for row in rows
    )
    return manifest, plan, request, conditions


def test_campaign_compiler_preserves_one_matching_and_nine_uncomputed_routes():
    manifest, plan, request, conditions = _campaign_inputs()
    campaign = build_equipment_campaign(
        manifest,
        plan,
        request,
        conditions,
        scope_provenance="synthetic test campaign",
    )
    branches = [branch for route in campaign.event_routes for branch in route.branches]
    assert len(campaign.event_routes) == 10
    assert sum(branch.request is not None for branch in branches) == 1
    assert sum(branch.uncomputed_reason is not None for branch in branches) == 9
    matched = next(branch.request for branch in branches if branch.request is not None)
    assert matched.frequency_event is None
    assert matched.annual_frequency_per_year is None
    assert matched.component_id == "storage-tank-01"


def test_campaign_compiler_does_not_substitute_a_different_opening():
    manifest, plan, request, conditions = _campaign_inputs()
    payload = request.model_dump(mode="json")
    payload["source_input"]["nozzle"]["diameter_m"] = 0.02
    wrong_size = ConsequenceRequest.model_validate_json(json.dumps(payload))
    campaign = build_equipment_campaign(
        manifest,
        plan,
        wrong_size,
        conditions,
        scope_provenance="synthetic wrong-opening test",
    )
    assert all(branch.request is None for route in campaign.event_routes for branch in route.branches)
    assert all(branch.uncomputed_reason for route in campaign.event_routes for branch in route.branches)
