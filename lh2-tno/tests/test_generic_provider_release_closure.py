from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.generic_provider_release_closure import (
    audit_generic_provider_release_closure,
)


def _release() -> dict:
    root = Path(__file__).parents[1]
    return json.loads(
        (root / "examples" / "provider_release_catalog_synthetic.json").read_text(
            encoding="utf-8"
        )
    )["releases"][0]


def test_campaign_audit_counts_ready_and_open_events(tmp_path):
    closed_value = _release()
    closed_value.update({
        "input_origin": "reviewed_measurement",
        "termination_basis": "reviewed_isolation_success",
        "provider_mass_balance": {
            "schema_version": "prism.provider_mass_balance.v1",
            "initial_mass_kg": closed_value["available_mass_kg"],
            "cumulative_mass_out_kg": closed_value["cumulative_mass_out_kg"],
            "final_mass_kg": closed_value["available_mass_kg"] - closed_value["cumulative_mass_out_kg"],
            "reported_residual_mass_kg": 0.0,
            "derived_accounting_residual_kg": 0.0,
            "isolation_time_s": closed_value["duration_s"] / 2.0,
            "isolation_success": True,
        },
    })
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps(closed_value), encoding="utf-8")
    open_packet = _release()
    open_packet["input_origin"] = "synthetic"
    open_packet["termination_basis"] = "synthetic_diagnostic_horizon"
    open_packet.pop("provider_mass_balance", None)
    opened = tmp_path / "open.json"
    opened.write_text(json.dumps(open_packet), encoding="utf-8")
    evidence = {
        "schema_version": "prism.native_scope_packet_evidence.v1",
        "rows": [
            {"event_id": "event-closed", "evidence": {"resolved_packet_paths": ["closed.json"]}},
            {"event_id": "event-open", "evidence": {"resolved_packet_paths": ["open.json"]}},
        ],
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report = audit_generic_provider_release_closure(evidence_path)

    assert report["event_count"] == 2
    assert report["closure_ready_event_count"] == 1
    assert report["closure_open_event_count"] == 1
    assert report["closure_ready_provider_packet_count"] == 1
    assert report["qualified_provider_packet_count"] == 0
    assert report["diagnostic_only"] is True
    assert report["promotion_gates"]["facility_qra_allowed"] is False
    request = report["event_rows"][1]["packet_rows"][0]["closure_request"]
    assert request["request_schema"] == "prism.provider_release_closure_request.v1"
    assert request["status"] == "OPEN"
    assert request["acceptance"]["frequency_inference_allowed"] is False
    assert any(
        row["field"] == "termination_basis"
        for row in request["required_evidence"]
    )


def test_campaign_audit_keeps_packet_audit_errors_open(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"provider_export_schema": "wrong"}), encoding="utf-8")
    evidence = {
        "rows": [
            {"event_id": "event-invalid", "evidence": {"resolved_packet_paths": ["invalid.json"]}},
        ]
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    report = audit_generic_provider_release_closure(path)

    assert report["closure_open_event_count"] == 1
    assert "audit failed" in report["event_rows"][0]["blocking_reasons"][0]


def test_campaign_audit_uses_bound_provider_threshold_verification(tmp_path):
    packet = _release()
    packet["termination_basis"] = "inventory_depletion"
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    verification = {
        "provider_result_digest": packet["provider_result_digest"],
        "provider_run_meta": {
            "termination_basis": "inventory_depletion_positive_threshold",
            "available_mass_kg": packet["available_mass_kg"],
            "cumulative_mass_out_kg": packet["cumulative_mass_out_kg"],
            "threshold_mass_kg": 0.9,
            "remaining_mass_kg": 0.8,
            "max_abs_mass_residual_kg": 0.0,
        },
    }
    (tmp_path / "verification.json").write_text(
        json.dumps(verification), encoding="utf-8"
    )
    evidence = {
        "rows": [
            {
                "event_id": "event-threshold",
                "evidence": {"resolved_packet_paths": ["resolved_release.json"]},
            }
        ]
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report = audit_generic_provider_release_closure(evidence_path)

    assert report["closure_ready_event_count"] == 1
    assert report["event_rows"][0]["packet_rows"][0]["termination_evidence_used"] is True


def test_campaign_audit_uses_packet_releasable_inventory_ledger(tmp_path):
    packet = _release()
    packet["termination_basis"] = "inventory_depletion"
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    (tmp_path / "verification.json").write_text(
        json.dumps({"provider_result_digest": packet["provider_result_digest"]}),
        encoding="utf-8",
    )
    (tmp_path / "provider_response.json").write_text(
        json.dumps({
            "data": {
                "provider_meta": {
                    "release_mode": "instantaneous_inventory",
                    "available_mass_definition": "cumulative releasable mass until atmospheric-pressure equilibrium",
                    "remaining_releasable_mass_kg": 0.0,
                    "residual_mass_kg": 0.0,
                }
            }
        }),
        encoding="utf-8",
    )
    evidence = {
        "rows": [
            {
                "event_id": "event-releasable",
                "evidence": {"resolved_packet_paths": ["resolved_release.json"]},
            }
        ]
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report = audit_generic_provider_release_closure(evidence_path)

    assert report["closure_ready_event_count"] == 1
    row = report["event_rows"][0]["packet_rows"][0]
    assert row["termination_evidence_used"] is True
