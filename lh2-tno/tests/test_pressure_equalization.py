from lh2_tno.pressure_equalization import audit_provider_pressure_equalization


def _closure():
    return {
        "inventory_feedback_closed": True,
        "pressure_feedback_closed": True,
        "state_history_digest": "a" * 64,
        "max_abs_inventory_residual_kg": 0.0,
        "inventory_tolerance_kg": 1.0e-10,
        "max_abs_pressure_residual_pa": 0.0,
        "pressure_tolerance_pa": 1.0e-5,
    }


def _packet(*, zero_tail=True):
    rows = [
        {
            "time_s": 0.0,
            "mass_flow_kg_s": 1.0,
            "provider_source_state": {"source_pressure_pa_abs": 102000.0},
        },
        {
            "time_s": 1.0,
            "mass_flow_kg_s": 0.0,
            "provider_source_state": {"source_pressure_pa_abs": 101325.0},
        },
    ]
    if zero_tail:
        rows.append({
            "time_s": 2.0,
            "mass_flow_kg_s": 0.0,
            "provider_source_state": {"source_pressure_pa_abs": 101200.0},
        })
    return {
        "event_id": "vaporizer/G2",
        "component_id": "vaporizer-01",
        "port_id": "out",
        "ambient_pressure_pa_abs": 101325.0,
        "termination_basis": "inventory_over_600s",
        "steps": rows,
        "provider_mass_balance": {
            "initial_mass_kg": 2.0,
            "cumulative_mass_in_kg": 0.0,
            "cumulative_mass_out_kg": 1.0,
            "final_mass_kg": 1.0,
            "derived_accounting_residual_kg": 0.0,
            "dynamic_state_closure": _closure(),
        },
    }


def test_pressure_equalization_candidate_requires_no_packet_mutation():
    report = audit_provider_pressure_equalization(_packet())

    assert report["status"] == "PRESSURE_EQUALIZATION_CANDIDATE"
    assert report["candidate_termination"]["basis"] == "model_pressure_equalization"
    assert report["candidate_termination"]["time_s"] == 1.0
    assert report["candidate_termination"]["observation_s"] == 1.0
    assert report["promotion_gates"]["packet_mutation_allowed"] is False
    assert report["current_termination_basis"] == "inventory_over_600s"


def test_pressure_equalization_candidate_stays_open_without_observation_tail():
    report = audit_provider_pressure_equalization(_packet(zero_tail=False))

    assert report["status"] == "PRESSURE_EQUALIZATION_EVIDENCE_OPEN"
    assert "provider zero-flow observation tail is shorter than required" in report["blocking_reasons"]


def test_pressure_equalization_candidate_requires_dynamic_closure():
    packet = _packet()
    packet["provider_mass_balance"].pop("dynamic_state_closure")
    report = audit_provider_pressure_equalization(packet)

    assert report["status"] == "PRESSURE_EQUALIZATION_EVIDENCE_OPEN"
    assert "provider dynamic pressure/inventory closure is missing or not closed" in report["blocking_reasons"]
