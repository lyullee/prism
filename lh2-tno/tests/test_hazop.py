from types import SimpleNamespace

import pytest

from lh2_tno.hazop import (
    HAZOP_SCHEMA,
    HAZOP_STATE_SCHEMA,
    HazopSelectionError,
    HazopStateFrame,
    HazopTable,
    evaluate_hazop,
    evaluate_hazop_runtime_frame,
    hazop_state_from_runtime_frame,
    run_hazop_runtime_consequence,
    run_hazop_runtime_consequence_branches,
    run_hazop_facility_runtime,
)
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames


def table_payload():
    return {
        "schema_version": HAZOP_SCHEMA,
        "id": "generic-intake-hazop-v1",
        "facility_id": "generic-outdoor-lh2",
        "operating_modes": ["receiving", "supply", "standby"],
        "configuration_origin": "synthetic",
        "source_provenance": "generic test HAZOP table; replace with reviewed P&ID HAZOP",
        "rows": [
            {
                "id": "TK01-high-pressure-receiving",
                "component_id": "TK-01",
                "component_kind": "storage_tank",
                "operating_modes": ["receiving"],
                "variable_tag": "PT-01",
                "quantity": "pressure",
                "trigger": "at_or_above",
                "threshold_high_si": 600000.0,
                "scenario_family": "vessel_hole",
                "release_mode": "hole",
                "priority": "high",
                "deviation_label": "high pressure",
                "cause_summary": "receiving pressure rises above design criterion",
                "consequence_summary": "tank wall release scenario requires provider packet",
                "safeguards": ["PSV-01", "ESD-01"],
                "provenance": "synthetic HAZOP row",
            },
            {
                "id": "TK01-low-temperature-supply",
                "component_id": "TK-01",
                "component_kind": "storage_tank",
                "operating_modes": ["supply"],
                "variable_tag": "TT-01",
                "quantity": "temperature",
                "trigger": "below",
                "threshold_low_si": 18.0,
                "scenario_family": "liquid_two_phase",
                "release_mode": "hole",
                "priority": "medium",
                "deviation_label": "low temperature",
                "cause_summary": "supply temperature falls",
                "consequence_summary": "two phase release candidate",
                "provenance": "synthetic HAZOP row",
            },
        ],
    }


def state(mode="receiving", pressure=650000.0, temperature=20.0):
    return {
        "schema_version": HAZOP_STATE_SCHEMA,
        "facility_id": "generic-outdoor-lh2",
        "component_id": "TK-01",
        "operating_mode": mode,
        "captured_at_s": 10.0,
        "source_provenance": "historian://intake/TK-01",
        "values": {
            "PT-01": {
                "quantity": "pressure", "value_si": pressure,
                "quality": "valid", "sensor_location": "tank-vapour",
            },
            "TT-01": {
                "quantity": "temperature", "value_si": temperature,
                "quality": "valid", "sensor_location": "tank-vapour",
            },
        },
    }


def test_mode_and_field_value_select_scenario_without_creating_release_or_frequency():
    result = evaluate_hazop(table_payload(), state())
    assert result["status"] == "SCENARIOS_SELECTED"
    assert result["operating_mode"] == "receiving"
    assert result["selected_scenario_count"] == 1
    selected = result["selected_scenarios"][0]
    assert selected["scenario_family"] == "vessel_hole"
    assert selected["provider_release_required"] is True
    assert selected["provider_release_status"] == "REQUIRED_NOT_CREATED"
    assert result["policy"]["frequency_inference_performed"] is False
    assert result["policy"]["release_packet_created"] is False


def test_nonmatching_operating_mode_does_not_reuse_receiving_row():
    result = evaluate_hazop(table_payload(), state(mode="standby"))
    assert result["status"] == "NO_APPLICABLE_MODE_ROW"
    assert result["selected_scenarios"] == []


def test_normal_value_produces_no_deviation():
    result = evaluate_hazop(table_payload(), state(pressure=500000.0))
    assert result["status"] == "NO_DEVIATION"
    assert result["active_deviation_count"] == 0


def test_missing_signal_is_open_and_not_treated_as_safe():
    payload = state()
    payload["values"].pop("PT-01")
    result = evaluate_hazop(table_payload(), payload)
    assert result["status"] == "BLOCKED_OPEN_INPUTS"
    assert result["selected_scenarios"] == []
    assert result["checks"][0]["status"] == "MISSING_SIGNAL"


def test_wrong_quantity_is_open():
    payload = state()
    payload["values"]["PT-01"]["quantity"] = "temperature"
    result = evaluate_hazop(table_payload(), payload)
    assert result["status"] == "BLOCKED_OPEN_INPUTS"
    assert "quantity mismatch" in result["blocking_reasons"][0]


def test_table_rejects_family_release_mode_mismatch():
    payload = table_payload()
    payload["rows"][0]["release_mode"] = "maximum_relief_discharge"
    with pytest.raises(Exception, match="does not support"):
        evaluate_hazop(payload, state())


def test_state_facility_mismatch_fails_closed():
    payload = state()
    payload["facility_id"] = "other-facility"
    with pytest.raises(HazopSelectionError, match="facility_id"):
        evaluate_hazop(table_payload(), payload)


def test_outside_range_uses_both_bounds():
    payload = table_payload()
    payload["rows"][0].update({
        "trigger": "outside_range", "threshold_low_si": 400000.0,
        "threshold_high_si": 600000.0,
    })
    assert evaluate_hazop(payload, state(pressure=450000.0))["status"] == "NO_DEVIATION"
    assert evaluate_hazop(payload, state(pressure=650000.0))["selected_scenario_count"] == 1


def test_state_frame_rejects_missing_mode_and_bad_digest():
    payload = state()
    payload.pop("operating_mode")
    with pytest.raises(Exception):
        HazopStateFrame.model_validate(payload)


def test_verified_runtime_frame_carries_mode_into_hazop_selection():
    source = {
        "source_id": "historian-tank-01",
        "source_sha256": "a" * 64,
        "component_id": "TK-01",
        "origin": "historian_measured",
        "operating_mode": "receiving",
        "samples": [{
            "captured_at_s": 3.0,
            "values": {"pressure": {"value_si": 650000.0, "sensor_location": "vapour"}},
        }],
    }
    frame = build_observed_state_runtime_frames([source])["frames"][0]
    table = table_payload()
    table["rows"][0]["component_id"] = "TK-01"
    table["rows"][0]["variable_tag"] = "pressure"
    result = evaluate_hazop_runtime_frame(table, frame, now_s=3.2)
    assert result["status"] == "SCENARIOS_SELECTED"
    assert result["operating_mode"] == "receiving"
    assert result["state_digest"] == hazop_state_from_runtime_frame(
        frame, facility_id="generic-outdoor-lh2", now_s=3.2
    ).digest()


def test_runtime_frame_without_mode_is_withheld_from_hazop():
    source = {
        "source_id": "historian-tank-01",
        "source_sha256": "a" * 64,
        "component_id": "TK-01",
        "origin": "historian_measured",
        "samples": [{"captured_at_s": 3.0, "values": {"pressure": 650000.0}}],
    }
    frame = build_observed_state_runtime_frames([source])["frames"][0]
    with pytest.raises(HazopSelectionError, match="operating_mode"):
        evaluate_hazop_runtime_frame(table_payload(), frame, now_s=3.2)
    payload = state()
    payload["state_snapshot_digest"] = "z" * 64
    with pytest.raises(Exception):
        HazopStateFrame.model_validate(payload)


def _runtime_frame_for_gate():
    source = {
        "source_id": "historian-tank-01",
        "source_sha256": "a" * 64,
        "component_id": "TK-01",
        "origin": "historian_measured",
        "operating_mode": "receiving",
        "samples": [{
            "captured_at_s": 3.0,
            "values": {"pressure": {"value_si": 650000.0, "sensor_location": "vapour"}},
        }],
    }
    return build_observed_state_runtime_frames([source])["frames"][0]


class _FakeMonitor:
    def __init__(self, request):
        self.request = request
        self.called = False

    def update_from_runtime_frame(self, template, frame, *, now_s, release_resolver, mapping_digest=None):
        self.called = True
        request = release_resolver(template, {"operating_mode": "receiving"})
        return {"request": request, "now_s": now_s, "mapping_digest": mapping_digest}


def _provider_request(*, source_operator="equipment_liquid_release", basis="model_pressure_equalization"):
    return SimpleNamespace(
        component_id="TK-01",
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=SimpleNamespace(event_kind="accidental_leak"),
        source_operator=source_operator,
        release_termination=SimpleNamespace(basis=basis),
    )


class _ModeAwareProviderRequest(SimpleNamespace):
    def model_copy(self, *, update):
        values = dict(self.__dict__)
        values.update(update)
        return type(self)(**values)


def _mode_aware_provider_request(*, operating_mode=None):
    request = _ModeAwareProviderRequest(
        component_id="TK-01",
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=SimpleNamespace(event_kind="accidental_leak"),
        source_operator="equipment_liquid_release",
        release_termination=SimpleNamespace(basis="model_pressure_equalization"),
    )
    if operating_mode is not None:
        request.operating_mode = operating_mode
    return request


def _gate_table():
    table = table_payload()
    table["rows"][0]["variable_tag"] = "pressure"
    return table


def test_runtime_gate_withholds_before_provider_when_hazop_is_normal():
    monitor = _FakeMonitor(_provider_request())
    result = run_hazop_runtime_consequence(
        _gate_table(),
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=monitor,
        release_resolver=lambda template, normalized: _provider_request(),
    )
    assert result["status"] == "CONSEQUENCE_EVALUATED"
    assert monitor.called is True
    assert result["policy"]["consequence_calculated"] is True


def test_runtime_gate_binds_selected_mode_to_provider_consequence_identity():
    class ModeMonitor:
        def __init__(self):
            self.request = None

        def update_from_runtime_frame(self, template, frame, *, now_s, release_resolver, mapping_digest=None):
            self.request = release_resolver(template, {"operating_mode": "receiving"})
            return {"request": self.request}

    monitor = ModeMonitor()
    result = run_hazop_runtime_consequence(
        _gate_table(),
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=monitor,
        release_resolver=lambda template, normalized: _mode_aware_provider_request(),
    )
    assert result["status"] == "CONSEQUENCE_EVALUATED"
    assert monitor.request.operating_mode == "receiving"


def test_runtime_gate_rejects_conflicting_provider_consequence_mode():
    monitor = _FakeMonitor(_mode_aware_provider_request(operating_mode="supply"))
    result = run_hazop_runtime_consequence(
        _gate_table(),
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=monitor,
        release_resolver=lambda template, normalized: _mode_aware_provider_request(
            operating_mode="supply"
        ),
    )
    assert result["status"] == "CONSEQUENCE_REJECTED"
    assert result["error_type"] == "HazopSelectionError"


def test_runtime_gate_requires_explicit_provider_release():
    result = run_hazop_runtime_consequence(
        _gate_table(),
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=_FakeMonitor(_provider_request()),
        release_resolver=None,
    )
    assert result["status"] == "WITHHELD_PROVIDER_RELEASE_REQUIRED"
    assert result["consequence"] is None


def test_runtime_gate_rejects_provider_scenario_contract_mismatch():
    monitor = _FakeMonitor(_provider_request(source_operator="equipment_two_sided_rupture", basis="two_sided_rupture"))
    result = run_hazop_runtime_consequence(
        _gate_table(),
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=monitor,
        release_resolver=lambda template, normalized: _provider_request(
            source_operator="equipment_two_sided_rupture", basis="two_sided_rupture"
        ),
    )
    assert result["status"] == "CONSEQUENCE_REJECTED"
    assert result["error_type"] == "HazopSelectionError"


def test_runtime_gate_requires_explicit_branch_dispatch_for_multiple_rows():
    table = _gate_table()
    extra = dict(table["rows"][0])
    extra["id"] = "TK01-liquid-branch-receiving"
    extra["scenario_family"] = "liquid_two_phase"
    table["rows"].append(extra)
    monitor = _FakeMonitor(_provider_request())
    result = run_hazop_runtime_consequence(
        table,
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=monitor,
        release_resolver=lambda template, normalized: _provider_request(),
    )
    assert result["status"] == "WITHHELD_SCENARIO_BRANCH_DISPATCH_REQUIRED"
    assert monitor.called is False


def test_runtime_gate_executes_existing_consequence_monitor_after_provider_match(tmp_path):
    from lh2_tno.provider_release import build_consequence_request_from_provider_release
    from lh2_tno.service import ConsequenceService, RealtimeConsequenceMonitor
    from test_consequence_service import Pipeline, request
    from test_provider_release import _defaults, _liquid_release

    release = _liquid_release().model_copy(update={"component_id": "TK-01"})
    defaults = _defaults()
    defaults.update({
        "component_id": "TK-01",
        "source_operator": "equipment_liquid_release",
        "release_termination": {
            "basis": "model_pressure_equalization",
            "time_s": 0.2,
            "provenance": "runtime gate integration test",
        },
        "source_duration_mode": "model_natural",
    })
    provider_request = build_consequence_request_from_provider_release(release, defaults)
    monitor = RealtimeConsequenceMonitor(ConsequenceService(Pipeline(tmp_path)))
    result = run_hazop_runtime_consequence(
        _gate_table(),
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=request().model_copy(update={"component_id": "TK-01"}),
        monitor=monitor,
        release_resolver=lambda template, normalized: provider_request,
    )
    assert result["status"] == "CONSEQUENCE_EVALUATED"
    assert result["consequence"]["telemetry_boundary"]["equipment_release_resolved"] is True
    assert result["consequence"]["telemetry_boundary"]["operating_mode"] == "receiving"
    assert result["consequence"]["equipment_release_path"]["status"] == "AVAILABLE_PROVIDER_RELEASE_PATH"
    assert result["consequence"]["equipment_release_path"]["operating_mode"] == "receiving"


def test_runtime_gate_dispatches_multiple_active_rows_as_separate_branches():
    table = _gate_table()
    extra = dict(table["rows"][0])
    extra["id"] = "TK01-liquid-branch-receiving"
    extra["scenario_family"] = "liquid_two_phase"
    table["rows"].append(extra)
    selection = evaluate_hazop_runtime_frame(
        table, _runtime_frame_for_gate(), now_s=3.2
    )
    resolvers = {}
    for row in selection["selected_scenarios"]:
        if row["scenario_family"] == "liquid_two_phase":
            resolvers[("TK-01", row["scenario_id"])] = (
                lambda template, normalized: _provider_request(
                    source_operator="equipment_inventory_depletion",
                    basis="inventory_depletion",
                )
            )
        else:
            resolvers[("TK-01", row["scenario_id"])] = (
                lambda template, normalized: _provider_request()
            )
    monitor = _FakeMonitor(_provider_request())
    result = run_hazop_runtime_consequence_branches(
        table,
        _runtime_frame_for_gate(),
        now_s=3.2,
        template=object(),
        monitor=monitor,
        release_resolvers=resolvers,
    )
    assert result["status"] == "CONSEQUENCE_BRANCHES_EVALUATED"
    assert len(result["branches"]) == 2
    assert all(
        branch["result"]["status"] == "CONSEQUENCE_EVALUATED"
        for branch in result["branches"]
    )
    assert result["policy"]["branches_auto_merged"] is False
    assert monitor.called is True


def test_facility_runtime_collects_component_branch_and_withholds_annual_qra():
    table = _gate_table()
    frame = _runtime_frame_for_gate()
    selection = evaluate_hazop_runtime_frame(table, frame, now_s=3.2)
    scenario_id = selection["selected_scenarios"][0]["scenario_id"]
    monitor = _FakeMonitor(_provider_request())
    binding = SimpleNamespace(template=object(), monitor=monitor, frequency_binding=None)
    result = run_hazop_facility_runtime(
        table,
        {"TK-01": frame},
        now_s=3.2,
        component_bindings={"TK-01": binding},
        release_resolvers={scenario_id: lambda template, normalized: _provider_request()},
    )
    assert result["status"] == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    assert result["components"]["TK-01"]["status"] == "CONSEQUENCE_BRANCHES_EVALUATED"
    assert result["conditional_current_weather_risk"]["status"] == "WITHHELD_NO_ACCEPTED_HAZOP_RISK_ATOM"
    assert result["facility_annual_ir_available"] is False
    assert result["facility_fn_available"] is False
    assert result["policy"]["facility_annual_qra_promotion"] is False


def test_realtime_facility_monitor_hazop_bridge_preserves_mode_and_fail_closed_qra(tmp_path):
    from lh2_tno.provider_release import build_consequence_request_from_provider_release
    from lh2_tno.service import (
        ConsequenceService,
        FacilityRealtimeBinding,
        FacilityRealtimeConsequenceMonitor,
        RealtimeConsequenceMonitor,
    )
    from test_consequence_service import Pipeline, request
    from test_provider_release import _defaults, _liquid_release

    release = _liquid_release().model_copy(update={"component_id": "TK-01"})
    defaults = _defaults()
    defaults.update({
        "component_id": "TK-01",
        "source_operator": "equipment_liquid_release",
        "release_termination": {
            "basis": "model_pressure_equalization",
            "time_s": 0.2,
            "provenance": "realtime HAZOP bridge test",
        },
        "source_duration_mode": "model_natural",
    })
    provider_request = build_consequence_request_from_provider_release(release, defaults)
    class _RuntimeNormalizer:
        def normalize(self, *_args, **_kwargs):
            raise AssertionError("runtime HAZOP bridge must bypass historian normalization")

    binding = FacilityRealtimeBinding(
        component_id="TK-01",
        template=request().model_copy(update={"component_id": "TK-01"}),
        monitor=RealtimeConsequenceMonitor(ConsequenceService(Pipeline(tmp_path))),
        normalizer=_RuntimeNormalizer(),
        pressure_tag="pressure",
        temperature_tag="temperature",
    )
    facility = FacilityRealtimeConsequenceMonitor(
        {"TK-01": binding}, facility_id="generic-outdoor-lh2"
    )
    frame = _runtime_frame_for_gate()
    selection = evaluate_hazop_runtime_frame(_gate_table(), frame, now_s=3.2)
    scenario_id = selection["selected_scenarios"][0]["scenario_id"]
    result = facility.update_from_runtime_frames_with_hazop(
        _gate_table(),
        {"TK-01": frame},
        now_s=3.2,
        release_resolvers={
            scenario_id: lambda _template, _normalized: provider_request
        },
    )
    assert result["status"] == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    assert result["components"]["TK-01"]["status"] == "CONSEQUENCE_BRANCHES_EVALUATED"
    assert result["components"]["TK-01"]["selection"]["operating_mode"] == "receiving"
    assert result["realtime_hazop_bridge"]["status"] == "EXECUTED_DIAGNOSTIC"
    assert result["realtime_hazop_bridge"]["selected_scenario_count"] == 1
    assert result["facility_annual_ir_available"] is False
    assert result["facility_fn_available"] is False

    partial = facility.update_from_runtime_frames_with_hazop(
        _gate_table(),
        {},
        now_s=3.2,
        release_resolvers={},
    )
    assert partial["status"] == "REJECTED_RUNTIME_HAZOP_FRAME_SET"
    assert partial["missing_component_ids"] == ["TK-01"]
    assert partial["facility_annual_ir_available"] is False


def test_hazop_facility_runtime_handoff_reaches_campaign_with_explicit_annual_rows(tmp_path):
    from lh2_tno.hazop_campaign import build_hazop_facility_campaign_result
    from lh2_tno.provider_release import build_consequence_request_from_provider_release
    from lh2_tno.service import (
        ConsequenceService,
        RealtimeConsequenceMonitor,
        RealtimeFrequencyBinding,
    )
    from test_consequence_service import RiskPipeline, request
    from test_provider_release import _defaults, _liquid_release

    release = _liquid_release().model_copy(update={"component_id": "TK-01"})
    defaults = _defaults()
    defaults.update({
        "component_id": "TK-01",
        "source_operator": "equipment_liquid_release",
        "release_termination": {
            "basis": "model_pressure_equalization",
            "time_s": 0.2,
            "provenance": "HAZOP facility campaign handoff test",
        },
        "source_duration_mode": "model_natural",
    })
    provider_request = build_consequence_request_from_provider_release(release, defaults)
    monitor = RealtimeConsequenceMonitor(ConsequenceService(RiskPipeline(tmp_path)))
    frequency = RealtimeFrequencyBinding(
        event_id="hazop-tk01-hole",
        asset_id="TK-01",
        initiating_frequency_per_year=1.0e-3,
        annual_condition_probability=1.0,
        release_branch_probability=1.0,
        occupancy_probability=1.0,
        provenance="reviewed HAZOP handoff literature fixture",
        source_digest="a" * 64,
        frequency_p05_per_year=5.0e-4,
        frequency_p95_per_year=2.0e-3,
    )
    selection = evaluate_hazop_runtime_frame(
        _gate_table(), _runtime_frame_for_gate(), now_s=3.2
    )
    scenario_id = selection["selected_scenarios"][0]["scenario_id"]
    runtime = run_hazop_facility_runtime(
        _gate_table(),
        {"TK-01": _runtime_frame_for_gate()},
        now_s=3.2,
        component_bindings={
            "TK-01": SimpleNamespace(
                template=request().model_copy(update={"component_id": "TK-01"}),
                monitor=monitor,
                frequency_binding=frequency,
            )
        },
        release_resolvers={scenario_id: lambda template, normalized: provider_request},
    )
    assert runtime["status"] == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    assert runtime["facility_id"] == "generic-outdoor-lh2"
    branch = runtime["components"]["TK-01"]["branches"][0]
    assert branch["risk"]["status"] == "AVAILABLE_CURRENT_WEATHER_IR"
    assert runtime["risk_atoms"][0]["operating_mode"] == "receiving"
    consequence = branch["result"]["consequence"]
    probabilities = consequence["data"]["ignition_branch_probabilities"]
    observed = branch["risk"]["risk_atom"]["receptor_harm_low_high"]
    active_probability = sum(
        float(value)
        for name, value in probabilities.items()
        if name != "no_ignition"
    )
    assert active_probability > 0.0
    branch_harm = {
        receptor_id: {
            name: (
                [0.0, 0.0]
                if name == "no_ignition"
                else [float(value) / active_probability for value in endpoints]
            )
            for name in probabilities
        }
        for receptor_id, endpoints in observed.items()
    }
    campaign_handoff = build_hazop_facility_campaign_result(
        runtime,
        annual_conditions=[{
            "id": "weather-d-03",
            "annual_probability": 1.0,
            "weather": {"wind_speed_m_s": 3.0, "stability_class": "D"},
            "population": [
                {
                    "receptor_id": receptor_id,
                    "persons": 10.0,
                    "presence_probability": 1.0,
                    "provenance": "reviewed outdoor population fixture",
                }
                for receptor_id in observed
            ],
            "provenance": "reviewed annual weather fixture",
        }],
        scenario_bindings=[{
            "component_id": "TK-01",
            "operating_mode": "receiving",
            "hazop_scenario_id": scenario_id,
            "event_id": frequency.event_id,
            "asset_id": frequency.asset_id,
            "annual_condition_id": "weather-d-03",
            "release_branch_id": "reviewed-isolation",
            "release_branch_probability": 1.0,
            "ignition_branch_probabilities": probabilities,
            "branch_harm_low_high": branch_harm,
            "scenario_families": [branch["scenario_family"]],
        }],
        expected_component_ids=("TK-01",),
    )
    assert campaign_handoff["status"] == "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert campaign_handoff["campaign"]["status"] == "PARTIAL_DECLARED_SCOPE"
    assert campaign_handoff["campaign"]["complete_facility_qra_claim"] is False
    assert campaign_handoff["facility_ledger"]["conditional_diagnostic_facility_risk_available"] is True
    assert campaign_handoff["facility_ledger"]["facility_total_risk_available"] is False
