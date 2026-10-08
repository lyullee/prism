import json
from pathlib import Path

from lh2_tno.accident_scope import build_accident_scope_matrix
from lh2_tno.campaign import AnnualCondition
from lh2_tno.campaign import EventRoute, ReleaseBranch
from lh2_tno.campaign_template import build_equipment_campaign
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.consequences import ConsequenceRequest


def _campaign_inputs():
    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(root / "examples/equipment_manifest.json")
    plan = FrequencyPlan.model_validate_json(
        (root / "examples/equipment_frequency_plan.json").read_text(encoding="utf-8")
    )
    request = ConsequenceRequest.model_validate_json(
        (root / "examples/equipment_consequence_template.json").read_text(encoding="utf-8")
    )
    rows = json.loads(
        (root / "examples/equipment_annual_conditions.json").read_text(encoding="utf-8")
    )
    conditions = tuple(
        AnnualCondition.model_validate_json(json.dumps(row, allow_nan=False)) for row in rows
    )
    return manifest, plan, request, conditions


def test_scope_matrix_marks_generated_and_missing_accident_families_explicitly():
    manifest, plan, request, conditions = _campaign_inputs()
    campaign = build_equipment_campaign(
        manifest, plan, request, conditions, scope_provenance="synthetic scope test"
    )
    events = [event.model_dump(mode="json") for event in generate_events(manifest.to_facility(), plan)]
    cases = []
    for event, route in zip(events, campaign.event_routes):
        branch = route.branches[0]
        cases.append(
            {
                "event_id": event["id"],
                "status": "EXECUTED_OPERATOR_LIMITED" if branch.request is not None else "UNCOMPUTED",
                "reason": "synthetic operator-limited case" if branch.request is not None else "no provider request",
            }
        )
    result = {
        "status": "PARTIAL_DECLARED_SCOPE",
        "events": events,
        "cases": cases,
        "total_facility_annual_ir_low_high": None,
    }

    matrix = build_accident_scope_matrix(campaign, result, manifest)

    rows = {row["family"]: row for row in matrix["rows"]}
    assert rows["vessel_hole"]["status"] == "PARTIAL"
    assert rows["vessel_hole"]["generated_event_count"] == 5
    assert rows["vessel_hole"]["operator_limited_case_count"] == 1
    assert rows["pipe_hole"]["status"] == "PARTIAL"
    assert rows["pipe_hole"]["generated_event_count"] == 5
    assert rows["pipe_hole"]["uncomputed_branch_count"] == 5
    assert rows["two_sided_rupture"]["status"] == "NO_EVENT_GENERATED"
    assert matrix["matrix_complete"] is False
    assert matrix["facility_total_risk_available"] is False
    assert any("two_sided_rupture: NO_EVENT_GENERATED" in reason for reason in matrix["blocking_reasons"])
    assert all(row["frequency_rows_are_not_additive_across_families"] for row in matrix["rows"])


def test_scope_matrix_rejects_unknown_required_family():
    manifest, plan, request, conditions = _campaign_inputs()
    campaign = build_equipment_campaign(
        manifest, plan, request, conditions, scope_provenance="synthetic scope test"
    )
    try:
        build_accident_scope_matrix(campaign, {"events": [], "cases": []}, manifest, required_families=("unknown",))
    except ValueError as error:
        assert "unknown accident families" in str(error)
    else:
        raise AssertionError("unknown family must fail closed")


def test_scope_matrix_preserves_a_physics_failure_status():
    manifest, plan, request, conditions = _campaign_inputs()
    partial_campaign = build_equipment_campaign(
        manifest, plan, request, conditions, scope_provenance="synthetic failure scope test"
    )
    matched_request = next(
        branch.request
        for route in partial_campaign.event_routes
        for branch in route.branches
        if branch.request is not None
    )
    campaign = partial_campaign.model_copy(update={
        "event_routes": tuple(
            EventRoute(
                event_id=route.event_id,
                branches=(ReleaseBranch(
                    id="synthetic-failure-branch",
                    probability_given_event=1.0,
                    provenance="synthetic failure accounting",
                    request=matched_request.model_copy(deep=True),
                ),),
            )
            for route in partial_campaign.event_routes
        )
    })
    events = [event.model_dump(mode="json") for event in generate_events(manifest.to_facility(), plan)]
    result = {
        "events": events,
        "cases": [
            {
                "event_id": event["id"],
                "status": "FAILED",
                "reason": "synthetic backend failure",
            }
            for event in events
            if event["profile"] == "LH2_VESSEL"
        ],
        "total_facility_annual_ir_low_high": None,
    }
    matrix = build_accident_scope_matrix(
        campaign, result, manifest, required_families=("vessel_hole",)
    )
    assert matrix["rows"][0]["status"] == "FAILED"


def test_scope_matrix_blocks_a_generated_event_without_a_case_row():
    manifest, plan, request, conditions = _campaign_inputs()
    campaign = build_equipment_campaign(
        manifest, plan, request, conditions, scope_provenance="synthetic missing-case test"
    )
    events = [event.model_dump(mode="json") for event in generate_events(manifest.to_facility(), plan)]
    result = {
        "events": events,
        "cases": [{"event_id": events[0]["id"], "status": "EXECUTED"}],
        "total_facility_annual_ir_low_high": {"receptor-01": [1.0, 1.0]},
    }
    matrix = build_accident_scope_matrix(
        campaign, result, manifest, required_families=("vessel_hole",)
    )
    row = matrix["rows"][0]
    assert row["status"] == "PARTIAL"
    assert row["event_without_case_count"] == 4
    assert matrix["matrix_complete"] is False


def test_scope_matrix_can_promote_a_fully_executed_declared_subset():
    manifest, plan, request, conditions = _campaign_inputs()
    partial_campaign = build_equipment_campaign(
        manifest, plan, request, conditions, scope_provenance="synthetic complete subset"
    )
    matched_request = next(
        branch.request
        for route in partial_campaign.event_routes
        for branch in route.branches
        if branch.request is not None
    )
    complete_routes = tuple(
        EventRoute(
            event_id=route.event_id,
            branches=(ReleaseBranch(
                id="synthetic-declared-release",
                probability_given_event=1.0,
                provenance="synthetic accounting-only request; physical binding still required",
                request=matched_request.model_copy(deep=True),
            ),),
        )
        for route in partial_campaign.event_routes
    )
    campaign = partial_campaign.model_copy(update={"event_routes": complete_routes})
    events = [event.model_dump(mode="json") for event in generate_events(manifest.to_facility(), plan)]
    result = {
        "events": events,
        "cases": [{"event_id": event["id"], "status": "EXECUTED"} for event in events],
        "total_facility_annual_ir_low_high": {"receptor-01": [1.0, 1.0]},
    }
    matrix = build_accident_scope_matrix(
        campaign, result, manifest, required_families=("vessel_hole",)
    )
    assert matrix["rows"][0]["status"] == "EXECUTED"
    assert matrix["matrix_complete"] is True
    assert matrix["facility_total_risk_available"] is True
