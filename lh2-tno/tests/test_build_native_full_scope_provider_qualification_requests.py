from __future__ import annotations

import json

from scripts.build_native_full_scope_provider_qualification_requests import build_requests


def _dynamic_packet() -> dict:
    return {
        "event_id": "dynamic-event",
        "component_id": "tank-1",
        "port_id": "outlet",
        "event_kind": "accidental_leak",
        "termination_basis": "model_pressure_equalization",
        "termination_provenance": "provider finite-volume state history",
        "duration_s": 0.2,
        "available_mass_kg": 10.0,
        "cumulative_mass_out_kg": 1.0,
        "provider_source_digest": "a" * 64,
        "provider_result_digest": "b" * 64,
        "provider_mass_balance": {
            "initial_mass_kg": 10.0,
            "cumulative_mass_in_kg": 0.0,
            "cumulative_mass_out_kg": 1.0,
            "final_mass_kg": 9.0,
            "derived_accounting_residual_kg": 0.0,
            "dynamic_state_closure": {
                "inventory_feedback_closed": True,
                "pressure_feedback_closed": True,
                "state_history_digest": "c" * 64,
                "max_abs_inventory_residual_kg": 0.0,
                "inventory_tolerance_kg": 1.0e-6,
                "max_abs_pressure_residual_pa": 0.0,
                "pressure_tolerance_pa": 1.0,
            },
        },
    }


def test_native_request_builder_uses_packet_closure_not_campaign_label(tmp_path):
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text(json.dumps(_dynamic_packet()), encoding="utf-8")
    readiness = {
        "status": "PARTIAL_DIAGNOSTIC_EVIDENCE",
        "rows": [
            {
                "event_id": "dynamic-event",
                "component_id": "tank-1",
                "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
                "evidence": {
                    "resolved_packet_paths": [str(packet_path)],
                    "qualification_readiness": {"blockers": ["sidecar_missing"]},
                },
            }
        ],
    }

    result = build_requests(readiness, readiness_path=tmp_path / "readiness.json")

    assert result["qualification_only_request_count"] == 1
    assert result["closure_and_qualification_request_count"] == 0
    request = result["requests"][0]["requests"][0]
    assert request["request_kind"] == "qualification_only"
    assert request["closure_status"] == "CLOSURE_READY_FOR_QUALIFICATION"
    assert request["acceptance"]["facility_qra_allowed"] is False
