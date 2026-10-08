import json
from pathlib import Path

import pytest
from lh2_tno.campaign import AnnualCondition
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
from lh2_tno.equipment_boundary import ResolvedLiquidRelease, ResolvedLiquidStep
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.frequency import FrequencyPlan
from lh2_tno.frequency import FrequencyAsset
from lh2_tno.provider_release import ProviderReleaseBranch
from test_provider_release import _defaults, _liquid_release, _release, _release_set


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
    payload["resolved_release"] = None
    payload["resolved_liquid_release"] = ResolvedLiquidRelease(
        component_id="liquid-transfer-line-01",
        port_id="line-out",
        event_id="synthetic-pipe-leak",
        event_kind="accidental_leak",
        upstream_service="LH2",
        upstream_service_provenance="synthetic test",
        phase_basis="two_phase",
        enthalpy_convention="provider_total_outlet_enthalpy",
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
        cumulative_specific_enthalpy_out_j=20.0,
        reference_area_m2=0.001,
        reference_area_provenance="synthetic test",
        steps=(ResolvedLiquidStep(
            time_s=0.0,
            total_mass_flow_kg_s=0.001,
            gas_mass_flow_kg_s=0.001,
            ground_liquid_mass_flow_kg_s=0.0,
            airborne_liquid_mass_flow_kg_s=0.0,
            specific_enthalpy_j_kg=100000.0,
            gas_pressure_pa_abs=101325.0,
            gas_temperature_k=288.15,
            gas_density_kg_m3=1.0,
            gas_effective_area_m2=0.001,
            gas_velocity_m_s=1.0,
            gas_velocity_origin="provider_resolved",
        ),),
        termination_provenance="synthetic test",
        droplet_partition_provenance="synthetic test; no airborne liquid",
        failure_opening_diameter_m=0.025,
    ).model_dump(mode="json")
    payload["source_position_enu_m"] = [5.0, 0.0, 1.0]
    payload["available_mass_kg"] = 1.0
    payload["source_operator"] = "equipment_liquid_release"
    payload["release_termination"] = {
        "basis": "inventory_depletion",
        "time_s": 0.2,
        "provenance": "synthetic test",
    }
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


def test_provider_catalog_compiles_packet_to_exact_frequency_route():
    manifest, plan, _, conditions = _campaign_inputs()
    packet = _release().model_copy(
        update={
            "upstream_service": "LH2",
            "failure_opening_diameter_m": 0.0127,
        }
    )
    campaign = build_equipment_campaign_from_provider_catalog(
        manifest,
        plan,
        (packet,),
        _defaults(),
        conditions,
        scope_provenance="synthetic direct provider campaign",
    )
    branches = [branch for route in campaign.event_routes for branch in route.branches]
    assert sum(branch.request is not None for branch in branches) == 1
    request = next(branch.request for branch in branches if branch.request is not None)
    assert request.resolved_release is not None
    assert request.resolved_release.event_id == packet.event_id


def test_provider_catalog_compiles_liquid_packet_to_exact_frequency_route():
    manifest, plan, _, conditions = _campaign_inputs()
    packet = _liquid_release().model_copy(
        update={
            "failure_opening_diameter_m": 0.0127,
        }
    )
    defaults = _defaults()
    defaults.update(
        source_operator="equipment_liquid_release",
        release_termination={
            "basis": "inventory_depletion",
            "time_s": packet.duration_s,
            "provenance": "synthetic liquid provider inventory boundary",
        },
    )
    campaign = build_equipment_campaign_from_provider_catalog(
        manifest,
        plan,
        (packet,),
        defaults,
        conditions,
        scope_provenance="synthetic direct liquid provider campaign",
    )
    branches = [branch for route in campaign.event_routes for branch in route.branches]
    assert sum(branch.request is not None for branch in branches) == 1
    request = next(branch.request for branch in branches if branch.request is not None)
    assert request.resolved_liquid_release is not None
    assert request.resolved_liquid_release.event_id == packet.event_id
    assert request.source_operator == "equipment_liquid_release"


def test_provider_catalog_rejects_duplicate_provider_event_ids():
    manifest, plan, _, conditions = _campaign_inputs()
    packet = _release()
    with pytest.raises(ValueError, match="event_id values must be unique"):
        build_equipment_campaign_from_provider_catalog(
            manifest,
            plan,
            (packet, packet),
            _defaults(),
            conditions,
            scope_provenance="synthetic duplicate provider campaign",
        )


def test_provider_branch_catalog_compiles_success_and_failure_packets_once_per_event():
    manifest, plan, _, conditions = _campaign_inputs()
    packet = _release().model_copy(
        update={
            "upstream_service": "LH2",
            "failure_opening_diameter_m": 0.0127,
        }
    )
    branches = (
        ProviderReleaseBranch(
            id="isolation-success",
            probability_given_event=0.7,
            provenance="synthetic provider success",
            release=packet,
        ),
        ProviderReleaseBranch(
            id="isolation-failure",
            probability_given_event=0.3,
            provenance="synthetic provider failure",
            release=packet,
        ),
    )

    campaign = build_equipment_campaign_from_provider_branch_catalog(
        manifest,
        plan,
        branches,
        _defaults(),
        conditions,
        scope_provenance="synthetic provider branch campaign",
    )

    matched_route = next(
        route for route in campaign.event_routes
        if route.event_id.endswith("storage-shell/AREA_0.01%")
    )
    assert [branch.id for branch in matched_route.branches] == [
        "isolation-success", "isolation-failure"
    ]
    assert sum(branch.probability_given_event for branch in matched_route.branches) == pytest.approx(1.0)
    assert all(branch.request is not None for branch in matched_route.branches)


def test_provider_two_sided_branch_catalog_uses_set_adapter_once_per_event():
    manifest, _, _, conditions = _campaign_inputs()
    pipe_asset = FrequencyAsset(
        id="transfer-line",
        model_component_id="liquid-transfer-line-01",
        profile="TNO_PIPE",
        physical_scope_ids=("liquid-transfer-line-01-segment",),
        classification_basis="synthetic two-sided branch test",
        nominal_diameter_m=0.025,
        length_per_item_m=10.0,
        pipe_conditions="default_conditions",
        pipe_correction_factor=1.0,
        location_weight=0.1,
        location_weight_provenance="synthetic reviewed rupture location allocation",
    )
    plan = FrequencyPlan(
        id="synthetic-two-sided-branch-plan",
        assets=(pipe_asset,),
        excluded_model_components={
            "storage-tank-01": "not selected in this branch test",
            "liquid-demand-boundary": "not selected in this branch test",
        },
    )
    release_set = _release_set()
    endpoints = tuple(
        release.model_copy(update={
            "component_id": "liquid-transfer-line-01",
            "failure_opening_diameter_m": 0.025,
        })
        for release in release_set.releases
    )
    release_set = release_set.model_copy(
        update={"component_id": "liquid-transfer-line-01", "releases": endpoints}
    )
    defaults = _defaults()
    defaults.update(
        component_id="liquid-transfer-line-01",
        source_position_enu_m=None,
        source_positions_enu_m=None,
        available_mass_kg=1.0,
        source_operator="equipment_two_sided_rupture",
        release_termination={
            "basis": "two_sided_rupture",
            "time_s": 0.2,
            "provenance": "synthetic two-sided branch clock",
        },
    )
    branches = (
        ProviderReleaseBranch(
            id="isolation-success",
            probability_given_event=0.7,
            provenance="synthetic two-sided success",
            release=release_set,
        ),
        ProviderReleaseBranch(
            id="isolation-failure",
            probability_given_event=0.3,
            provenance="synthetic two-sided failure",
            release=release_set,
        ),
    )

    campaign = build_equipment_campaign_from_provider_branch_catalog(
        manifest, plan, branches, defaults, conditions,
        scope_provenance="synthetic two-sided provider branch campaign",
    )

    matched_route = next(
        route for route in campaign.event_routes if route.event_id.endswith("transfer-line/G1")
    )
    assert [branch.id for branch in matched_route.branches] == [
        "isolation-success", "isolation-failure"
    ]
    assert all(branch.request is not None for branch in matched_route.branches)
    assert all(branch.request.resolved_release_set is not None for branch in matched_route.branches)
    assert sum(branch.probability_given_event for branch in matched_route.branches) == pytest.approx(1.0)


def test_branch_catalog_preserves_isolation_partition_and_matches_exact_event():
    manifest, plan, request, conditions = _campaign_inputs()
    branches = (
        RequestBranchTemplate(
            id="isolation-success",
            probability_given_event=0.7,
            provenance="synthetic reviewed success branch",
            request=request,
        ),
        RequestBranchTemplate(
            id="isolation-failure",
            probability_given_event=0.3,
            provenance="synthetic reviewed failure branch",
            request=request,
        ),
    )
    campaign = build_equipment_campaign_from_branch_catalog(
        manifest, plan, branches, conditions,
        scope_provenance="synthetic branch catalog test",
    )
    matched_route = next(
        route for route in campaign.event_routes
        if route.event_id.endswith("storage-shell/AREA_0.01%")
    )
    assert [branch.id for branch in matched_route.branches] == [
        "isolation-success", "isolation-failure"
    ]
    assert sum(branch.probability_given_event for branch in matched_route.branches) == pytest.approx(1.0)
    assert all(branch.request is not None for branch in matched_route.branches)


def test_branch_catalog_retains_missing_probability_as_uncomputed_remainder():
    manifest, plan, request, conditions = _campaign_inputs()
    branch = RequestBranchTemplate(
        id="isolation-success",
        probability_given_event=0.7,
        provenance="synthetic partial branch catalog",
        request=request,
    )
    campaign = build_equipment_campaign_from_branch_catalog(
        manifest, plan, (branch,), conditions,
        scope_provenance="synthetic partial branch catalog test",
    )
    matched_route = next(
        route for route in campaign.event_routes
        if route.event_id.endswith("storage-shell/AREA_0.01%")
    )
    assert matched_route.branches[-1].id == "uncomputed-provider-branch-remainder"
    assert matched_route.branches[-1].probability_given_event == pytest.approx(0.3)
    assert matched_route.branches[-1].request is None


def test_branch_catalog_rejects_probability_above_one():
    manifest, plan, request, conditions = _campaign_inputs()
    branches = tuple(
        RequestBranchTemplate(
            id=branch_id,
            probability_given_event=0.6,
            provenance="synthetic over-partition",
            request=request,
        )
        for branch_id in ("a", "b")
    )
    with pytest.raises(ValueError, match="probabilities exceed one"):
        build_equipment_campaign_from_branch_catalog(
            manifest, plan, branches, conditions,
            scope_provenance="synthetic over-partition test",
        )


def test_provider_worklist_campaign_keeps_all_generic_events_uncomputed_without_packets():
    root = Path(__file__).parents[1]
    manifest = EquipmentManifest.from_json(
        root / "examples" / "generic_lh2_full_scope_manifest.json"
    )
    plan = FrequencyPlan.model_validate_json(
        (root / "examples" / "generic_lh2_full_scope_frequency_plan.json").read_text(
            encoding="utf-8"
        )
    )
    conditions = tuple(
        AnnualCondition.model_validate_json(json.dumps(row, allow_nan=False))
        for row in json.loads(
            (root / "examples" / "equipment_annual_conditions.json").read_text(
                encoding="utf-8"
            )
        )
    )
    campaign = build_equipment_campaign_from_provider_worklist(
        manifest,
        plan,
        conditions,
        scope_provenance="synthetic provider worklist test",
    )

    assert len(campaign.event_routes) == 24
    branches = [branch for route in campaign.event_routes for branch in route.branches]
    assert len(branches) == 24
    assert all(branch.id == "uncomputed-provider-packet" for branch in branches)
    assert all(branch.request is None for branch in branches)
    assert all("provider accident packet required" in branch.uncomputed_reason for branch in branches)
