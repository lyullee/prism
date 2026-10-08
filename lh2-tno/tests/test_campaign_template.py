import json
from pathlib import Path

import pytest
from lh2_tno.campaign import AnnualCondition
from lh2_tno.campaign_template import build_equipment_campaign, build_equipment_campaign_from_catalog
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_boundary import ResolvedGasRelease, ResolvedGasStep
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


def test_campaign_catalog_matches_each_explicit_component_opening_without_substitution():
    manifest, plan, storage_request, conditions = _campaign_inputs()
    plan_payload = plan.model_dump(mode="json")
    plan_payload["assets"][1]["location_weight"] = 0.1
    plan_payload["assets"][1]["location_weight_provenance"] = "synthetic single reviewed pipe location"
    plan = FrequencyPlan.model_validate_json(json.dumps(plan_payload))
    payload = storage_request.model_dump(mode="json")
    payload["component_id"] = "liquid-transfer-line-01"
    payload["source_input"] = None
    payload["resolved_release"] = ResolvedGasRelease(
        component_id="liquid-transfer-line-01",
        port_id="line-out",
        event_id="synthetic-pipe-leak",
        event_kind="accidental_leak",
        upstream_service="LH2",
        upstream_service_provenance="synthetic test",
        enthalpy_convention="static_exit_enthalpy",
        property_basis={"fluid": "Hydrogen", "energy_reference": "CoolProp-HEOS:Hydrogen:native"},
        provider_source_digest="0" * 64,
        provider_result_digest="1" * 64,
        provider_boundary_reference="synthetic pipe exit",
        input_origin="synthetic",
        position_enu_m=(5.0, 0.0, 1.0),
        direction_enu=(1.0, 0.0, 0.0),
        ambient_pressure_pa_abs=101325.0,
        ambient_temperature_k=288.15,
        duration_s=0.2,
        available_mass_kg=1.0,
        cumulative_mass_out_kg=0.0002,
        cumulative_static_enthalpy_out_j=20.0,
        steps=(ResolvedGasStep(
            time_s=0.0,
            mass_flow_kg_s=0.001,
            pressure_pa_abs=101325.0,
            specific_enthalpy_j_kg=100000.0,
            temperature_k=288.15,
            density_kg_m3=1.0,
            effective_area_m2=0.001,
            velocity_m_s=1.0,
            area_provenance="synthetic test",
            velocity_origin="provider_resolved",
        ),),
        termination_provenance="synthetic test",
        failure_opening_diameter_m=0.025,
    ).model_dump(mode="json")
    payload["source_position_enu_m"] = [5.0, 0.0, 1.0]
    payload["available_mass_kg"] = 1.0
    pipe_request = ConsequenceRequest.model_validate_json(json.dumps(payload))

    campaign = build_equipment_campaign_from_catalog(
        manifest, plan, (storage_request, pipe_request), conditions,
        scope_provenance="synthetic catalog test",
    )
    branches = [branch for route in campaign.event_routes for branch in route.branches]
    assert sum(branch.request is not None for branch in branches) == 2
    assert sum(branch.uncomputed_reason is not None for branch in branches) == 8
    matched_ids = {branch.request.component_id for branch in branches if branch.request is not None}
    assert matched_ids == {"storage-tank-01", "liquid-transfer-line-01"}


def test_campaign_catalog_rejects_ambiguous_exact_matches():
    manifest, plan, request, conditions = _campaign_inputs()
    with pytest.raises(ValueError, match="multiple request templates match"):
        build_equipment_campaign_from_catalog(
            manifest, plan, (request, request), conditions,
            scope_provenance="synthetic ambiguous catalog test",
        )
