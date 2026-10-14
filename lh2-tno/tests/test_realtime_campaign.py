from pathlib import Path
import copy

import pytest

from lh2_tno.facility_ledger import merge_facility_campaign_results
from lh2_tno.provider_release import build_consequence_request_from_provider_release
from lh2_tno.realtime_campaign import (
    RealtimeCampaignBindingError,
    build_realtime_facility_campaign_result,
)
from lh2_tno.service import (
    ConsequenceService,
    FacilityRealtimeBinding,
    FacilityRealtimeConsequenceMonitor,
    RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
)
from test_consequence_service import RiskPipeline, _facility_binding
from test_provider_release import _defaults, _release


def _monitor(tmp_path: Path, *, with_provider_path: bool = True):
    base, frame = _facility_binding(tmp_path, "storage-tank-01")
    provider_request = build_consequence_request_from_provider_release(
        _release(), _defaults()
    )
    frequency = RealtimeFrequencyBinding(
        event_id="storage-tank-hole-01",
        asset_id="storage-tank-01",
        initiating_frequency_per_year=1.0e-3,
        annual_condition_probability=1.0,
        release_branch_probability=1.0,
        occupancy_probability=1.0,
        provenance="reviewed synthetic literature binding for adapter test",
        source_digest="a" * 64,
    )
    binding = FacilityRealtimeBinding(
        component_id=base.component_id,
        template=base.template,
        monitor=RealtimeConsequenceMonitor(
            ConsequenceService(RiskPipeline(tmp_path)), period_s=1.0, deadline_s=1.0
        ),
        normalizer=base.normalizer,
        pressure_tag=base.pressure_tag,
        temperature_tag=base.temperature_tag,
        release_resolver=(
            (lambda _template, _state: provider_request)
            if with_provider_path
            else None
        ),
        frequency_binding=frequency,
    )
    return (
        FacilityRealtimeConsequenceMonitor(
            {"storage-tank-01": binding}, facility_id="generic-outdoor-lh2"
        ),
        frame,
    )


def _snapshot(tmp_path: Path, *, with_provider_path: bool = True):
    monitor, frame = _monitor(tmp_path, with_provider_path=with_provider_path)
    return monitor.update_from_frames({"storage-tank-01": frame}, now_s=100.2)


def _annual_conditions():
    return [
        {
            "id": "weather-1",
            "annual_probability": 1.0,
            "weather": {"wind_speed_m_s": 3.0, "stability_class": "D"},
            "population": [
                {
                    "receptor_id": "worker-01",
                    "persons": 10.0,
                    "presence_probability": 1.0,
                    "provenance": "reviewed outdoor population test input",
                }
            ],
            "provenance": "reviewed annual weather test input",
        }
    ]


def _scenario_binding(*, low: float = 2.0 / 7.0):
    probabilities = {
        "direct_fire": 0.25,
        "delayed_flash_fire": 0.35,
        "delayed_explosion": 0.10,
        "no_ignition": 0.30,
    }
    branch_harm = {
        branch: ([low, 2.0 * low] if branch != "no_ignition" else [0.0, 0.0])
        for branch in probabilities
    }
    return {
        "component_id": "storage-tank-01",
        "event_id": "storage-tank-hole-01",
        "asset_id": "storage-tank-01",
        "annual_condition_id": "weather-1",
        "release_branch_id": "reviewed-isolation",
        "release_branch_probability": 1.0,
        "ignition_branch_probabilities": probabilities,
        "branch_harm_low_high": {"worker-01": branch_harm},
        "scenario_families": ["vessel_hole"],
    }


def test_realtime_snapshot_becomes_conditional_facility_ledger_input(tmp_path):
    snapshot = _snapshot(tmp_path)
    result = build_realtime_facility_campaign_result(
        snapshot,
        annual_conditions=_annual_conditions(),
        scenario_bindings=[_scenario_binding()],
        expected_component_ids=("storage-tank-01",),
    )

    assert result["schema_version"] == "prism.realtime_facility_campaign_result.v1"
    assert result["status"] == "PARTIAL_DECLARED_SCOPE"
    assert len(result["risk_atoms"]) == 4
    assert result["cases"][0]["status"] == "EXECUTED_OPERATOR_LIMITED"
    assert result["provider_packet_case_count"] == 1
    assert result["qualified_provider_packet_case_count"] == 0
    assert result["physical_validation_claim"] is False
    assert result["complete_facility_qra_claim"] is False
    assert all(
        atom["expected_deaths_basis"] == "population_weighted"
        for atom in result["risk_atoms"]
    )

    ledger = merge_facility_campaign_results(
        [result], expected_component_ids=("storage-tank-01",)
    )
    assert ledger["conditional_diagnostic_facility_risk_available"] is True
    assert ledger["facility_total_risk_available"] is False
    assert ledger["qualified_facility_qra_available"] is False
    assert ledger["conditional_diagnostic_facility_annual_ir_low_high"]["worker-01"] == pytest.approx(
        [2.0e-4, 4.0e-4]
    )
    assert ledger["population_accounting"]["status"] == "EXPLICIT_CONDITION_POPULATION"
    assert ledger["component_statuses"]["storage-tank-01"] == "PARTIAL"


def test_monitor_owns_snapshot_to_annual_campaign_handoff(tmp_path):
    monitor, frame = _monitor(tmp_path)
    snapshot = monitor.update_from_frames(
        {"storage-tank-01": frame}, now_s=100.2
    )

    result = monitor.build_annual_campaign_result(
        snapshot,
        annual_conditions=_annual_conditions(),
        scenario_bindings=[_scenario_binding()],
    )

    assert result["status"] == "PARTIAL_DECLARED_SCOPE"
    assert result["realtime_handoff"]["facility_id"] == "generic-outdoor-lh2"
    assert result["complete_facility_qra_claim"] is False

    foreign_snapshot = dict(snapshot)
    foreign_snapshot["facility_id"] = "another-facility"
    with pytest.raises(ValueError, match="facility_id"):
        monitor.build_annual_campaign_result(
            foreign_snapshot,
            annual_conditions=_annual_conditions(),
            scenario_bindings=[_scenario_binding()],
        )


def test_realtime_campaign_rejects_branch_harm_that_does_not_close(tmp_path):
    snapshot = _snapshot(tmp_path)
    binding = _scenario_binding(low=0.30)
    with pytest.raises(RealtimeCampaignBindingError, match="does not close"):
        build_realtime_facility_campaign_result(
            snapshot,
            annual_conditions=_annual_conditions(),
            scenario_bindings=[binding],
            expected_component_ids=("storage-tank-01",),
        )


def test_realtime_campaign_does_not_turn_missing_release_path_into_zero_risk(tmp_path):
    snapshot = _snapshot(tmp_path, with_provider_path=False)
    with pytest.raises(
        RealtimeCampaignBindingError, match="no realtime component produced"
    ):
        build_realtime_facility_campaign_result(
            snapshot,
            annual_conditions=_annual_conditions(),
            scenario_bindings=[_scenario_binding()],
            expected_component_ids=("storage-tank-01",),
        )


def test_realtime_campaign_supports_multiple_annual_conditions_with_explicit_reviewed_harm(
    tmp_path,
):
    snapshot = _snapshot(tmp_path)
    conditions = _annual_conditions()
    second = copy.deepcopy(conditions[0])
    second.update(
        id="weather-2",
        annual_probability=0.4,
        weather={"wind_speed_m_s": 7.0, "stability_class": "D"},
    )
    conditions[0]["annual_probability"] = 0.6
    conditions.append(second)

    current_binding = _scenario_binding()
    current_binding["annual_condition_id"] = "weather-1"
    current_binding["consequence_basis"] = "realtime_snapshot"
    reviewed_binding = _scenario_binding(low=0.1)
    reviewed_binding.update(
        annual_condition_id="weather-2",
        consequence_basis="reviewed_annual_condition",
        consequence_provenance="reviewed SLABx-LH2 weather-2 consequence table",
        observed_harm_low_high={"worker-01": [0.07, 0.14]},
    )

    result = build_realtime_facility_campaign_result(
        snapshot,
        annual_conditions=conditions,
        scenario_bindings=[current_binding, reviewed_binding],
        expected_component_ids=("storage-tank-01",),
    )

    assert len(result["events"]) == 1
    assert len(result["cases"]) == 2
    assert len(result["risk_atoms"]) == 8
    assert result["events"][0]["id"] == "storage-tank-hole-01"
    assert result["events"][0]["scenario_families"] == ["vessel_hole"]
    ledger = merge_facility_campaign_results(
        [result], expected_component_ids=("storage-tank-01",)
    )
    assert ledger["conditional_diagnostic_facility_annual_ir_low_high"]["worker-01"] == pytest.approx(
        [1.48e-4, 2.96e-4]
    )
    assert ledger["population_accounting"]["referenced_condition_count"] == 2
    assert ledger["facility_total_risk_available"] is False


def test_realtime_campaign_rejects_hazop_scenario_identity_drift(tmp_path):
    snapshot = _snapshot(tmp_path)
    conditions = _annual_conditions()
    second = copy.deepcopy(conditions[0])
    second.update(id="weather-2", annual_probability=0.4)
    conditions[0]["annual_probability"] = 0.6
    conditions.append(second)

    current = _scenario_binding()
    current.update(
        consequence_basis="realtime_snapshot",
        hazop_scenario_id="TK01-receiving",
    )
    reviewed = _scenario_binding(low=0.1)
    reviewed.update(
        annual_condition_id="weather-2",
        consequence_basis="reviewed_annual_condition",
        consequence_provenance="reviewed consequence fixture",
        observed_harm_low_high={"worker-01": [0.07, 0.14]},
        hazop_scenario_id="TK01-supply",
    )
    with pytest.raises(RealtimeCampaignBindingError, match="metadata conflicts"):
        build_realtime_facility_campaign_result(
            snapshot,
            annual_conditions=conditions,
            scenario_bindings=[current, reviewed],
            expected_component_ids=("storage-tank-01",),
        )
