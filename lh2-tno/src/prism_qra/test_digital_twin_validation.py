import math

import digital_twin_validation as D


def _analysis(values):
    return {
        "screening_rate": round(
            float(values["TANK_PRESSURE_PA"])
            * float(values["LEAK_DIAMETER_M"]) ** 2,
            9,
        )
    }


def _monitor():
    return D.DigitalTwinMonitor(
        D.default_tag_specs(), _analysis,
        max_frame_age_ms=1000.0,
        constraints=(D.pressure_agreement,),
        model_version="test-version",
    )


def test_virtual_commissioning_detects_every_injected_fault():
    report = D.run_replay(_monitor(), D.build_virtual_commissioning_suite())
    metrics = report.metrics
    assert metrics.n_injected_faults == 11
    assert metrics.detected_faults == 11
    assert metrics.fault_detection_rate == 1.0
    assert metrics.false_accepts == 0
    assert metrics.false_rejects == 0
    assert metrics.valid_frame_acceptance_rate == 1.0
    assert metrics.state_accuracy == 1.0
    assert metrics.state_alignment_ratio == 1.0
    assert metrics.traceability_coverage == 1.0


def test_bad_frame_is_transactional_and_does_not_replace_good_state():
    monitor = _monitor()
    good_values = D.make_values(pressure_pa=40.0e6)
    good = D.TelemetryFrame(1, 0.0, 0.01, good_values)
    assert monitor.process(good).accepted
    prior = dict(monitor.state)

    broken = D.make_values(pressure_pa=60.0e6)
    broken["TANK_TEMPERATURE_K"] = D.TelemetryValue(20.0, "degC")
    result = monitor.process(D.TelemetryFrame(2, 1.0, 1.01, broken))
    assert not result.accepted
    assert any(reason.startswith("BAD_UNIT") for reason in result.reasons)
    assert monitor.state == prior


def test_duplicate_and_unseen_older_sequence_are_distinguished():
    monitor = _monitor()
    assert monitor.process(D.TelemetryFrame(
        10, 0.0, 0.01, D.make_values()
    )).accepted
    duplicate = monitor.process(D.TelemetryFrame(
        10, 1.0, 1.01, D.make_values()
    ))
    older = monitor.process(D.TelemetryFrame(
        9, 2.0, 2.01, D.make_values()
    ))
    assert duplicate.reasons == ("DUPLICATE_SEQUENCE",)
    assert older.reasons == ("OUT_OF_ORDER_SEQUENCE",)


def test_cross_sensor_bias_and_impossible_state_are_rejected():
    monitor = _monitor()
    biased = D.make_values()
    biased["TANK_PRESSURE_REDUNDANT_PA"] = D.TelemetryValue(30.0e6, "Pa")
    bias_result = monitor.process(D.TelemetryFrame(1, 0.0, 0.01, biased))
    assert not bias_result.accepted
    assert bias_result.reasons == (
        "CROSS_FIELD_INCONSISTENCY:redundant pressure sensors disagree",
    )

    conflict = D.make_values(
        unloading_flow_kg_s=0.2, filling_flow_kg_s=0.2
    )
    conflict_result = monitor.process(D.TelemetryFrame(
        2, 1.0, 1.01, conflict
    ))
    assert not conflict_result.accepted
    assert conflict_result.reasons == (
        "CROSS_FIELD_INCONSISTENCY:"
        "filling and unloading flows are active together",
    )


def test_forbidden_transition_is_rejected_without_changing_state():
    monitor = _monitor()
    esd = D.make_values(esd_active=True)
    assert monitor.process(D.TelemetryFrame(1, 0.0, 0.01, esd)).accepted
    assert monitor.plant_state is D.PlantState.ESD

    unloading = D.make_values(unloading_flow_kg_s=0.5)
    result = monitor.process(D.TelemetryFrame(2, 1.0, 1.01, unloading))
    assert not result.accepted
    assert result.reasons[0].startswith("FORBIDDEN_STATE_TRANSITION")
    assert monitor.plant_state is D.PlantState.ESD


def test_output_hashes_are_deterministic_across_independent_replays():
    cases = D.build_virtual_commissioning_suite()
    first = D.run_replay(_monitor(), cases)
    second = D.run_replay(_monitor(), cases)
    assert D.replay_hashes(first) == D.replay_hashes(second)
    assert len(D.replay_hashes(first)) == first.metrics.n_accepted


def test_nonfinite_numbers_and_boolean_as_number_are_rejected():
    monitor = _monitor()
    values = D.make_values()
    values["TANK_PRESSURE_PA"] = D.TelemetryValue(math.inf, "Pa")
    values["UNLOADING_FLOW_KG_S"] = D.TelemetryValue(True, "kg/s")
    result = monitor.process(D.TelemetryFrame(1, 0.0, 0.01, values))
    assert not result.accepted
    assert "NONFINITE:TANK_PRESSURE_PA" in result.reasons
    assert "BAD_TYPE:UNLOADING_FLOW_KG_S" in result.reasons


def test_actual_hydrogen_source_model_can_be_called_through_the_boundary():
    import source_term

    def actual_analysis(values):
        discharge = source_term.discharge(
            float(values["TANK_PRESSURE_PA"]),
            float(values["TANK_TEMPERATURE_K"]),
            "Hydrogen",
            float(values["LEAK_DIAMETER_M"]),
            n_scan=80,
        )
        return {
            "rate_kg_s": discharge.rate_kg_s,
            "choked": discharge.choked,
            "flow_model": discharge.flow_model,
        }

    monitor = D.DigitalTwinMonitor(
        D.default_tag_specs(), actual_analysis,
        constraints=(D.pressure_agreement,),
    )
    result = monitor.process(D.TelemetryFrame(
        1, 0.0, 0.025, D.make_values()
    ))
    assert result.accepted
    assert result.output_hash is not None
    assert result.processing_latency_ms > 0.0


def test_rejected_large_sequence_does_not_poison_future_frames():
    monitor = _monitor()
    invalid = D.make_values()
    del invalid["TANK_TEMPERATURE_K"]
    assert not monitor.process(D.TelemetryFrame(
        1_000_000, 0.0, 0.01, invalid
    )).accepted
    result = monitor.process(D.TelemetryFrame(
        1, 1.0, 1.01, D.make_values()
    ))
    assert result.accepted


def test_sequence_tracking_is_per_stream_and_bounded():
    monitor = D.DigitalTwinMonitor(
        D.default_tag_specs(), _analysis, max_frame_age_ms=1000.0,
        constraints=(D.pressure_agreement,), sequence_history_limit=2,
    )
    for stream in ("a", "b"):
        assert monitor.process(D.TelemetryFrame(
            1, 0.0, 0.01, D.make_values(), stream
        )).accepted
    assert monitor.process(D.TelemetryFrame(
        2, 1.0, 1.01, D.make_values(), "a"
    )).accepted
    assert monitor.process(D.TelemetryFrame(
        3, 2.0, 2.01, D.make_values(), "a"
    )).accepted
    assert len(monitor._seen_sequences["a"]) == 2
    old = monitor.process(D.TelemetryFrame(
        1, 3.0, 3.01, D.make_values(), "a"
    ))
    assert old.reasons == ("OUT_OF_ORDER_SEQUENCE",)


def test_cross_frame_clock_reversal_and_nonfinite_time_are_rejected():
    monitor = _monitor()
    assert monitor.process(D.TelemetryFrame(
        1, 10.0, 10.01, D.make_values()
    )).accepted
    reversed_result = monitor.process(D.TelemetryFrame(
        2, 9.0, 9.01, D.make_values()
    ))
    assert "CLOCK_REVERSED" in reversed_result.reasons
    nonfinite = monitor.process(D.TelemetryFrame(
        2, math.nan, 11.0, D.make_values()
    ))
    assert "NONFINITE:source_time_s" in nonfinite.reasons
    assert math.isfinite(nonfinite.end_to_end_latency_ms)


def test_replay_fault_must_be_rejected_for_the_expected_reason():
    monitor = _monitor()
    values = D.make_values()
    del values["TANK_TEMPERATURE_K"]
    case = D.FrameExpectation(
        D.TelemetryFrame(1, 0.0, 0.01, values), False,
        injected_fault="wrong-reason-regression",
        expected_reason_prefix=D.RejectReason.BAD_UNIT.value,
    )
    report = D.run_replay(monitor, (case,))
    assert report.metrics.n_rejected == 1
    assert report.metrics.detected_faults == 0
    assert report.metrics.fault_detection_rate == 0.0


def test_empty_replay_does_not_claim_perfect_performance():
    metrics = D.run_replay(_monitor(), ()).metrics
    assert metrics.fault_detection_rate == 0.0
    assert metrics.valid_frame_acceptance_rate == 0.0
    assert metrics.state_accuracy == 0.0
    assert metrics.state_alignment_ratio == 0.0
    assert metrics.traceability_coverage == 0.0
