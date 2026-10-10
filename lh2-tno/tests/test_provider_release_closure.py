from __future__ import annotations

import json
from pathlib import Path

import pytest

from lh2_tno.provider_release_closure import (
    ProviderReleaseClosureError,
    audit_provider_release_closure,
)


ROOT = Path(__file__).parents[1]


def _release() -> dict:
    return json.loads(
        (ROOT / "examples" / "provider_release_catalog_synthetic.json").read_text(
            encoding="utf-8"
        )
    )["releases"][0]


def _closed_release() -> dict:
    value = _release()
    value.update({
        "input_origin": "reviewed_measurement",
        "termination_basis": "reviewed_isolation_success",
        "provider_mass_balance": {
            "schema_version": "prism.provider_mass_balance.v1",
            "initial_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.2,
            "final_mass_kg": 0.8,
            "reported_residual_mass_kg": 0.0,
            "derived_accounting_residual_kg": 0.0,
            "isolation_time_s": 0.1,
            "isolation_success": True,
        },
    })
    return value


def test_missing_termination_and_isolation_evidence_stays_open():
    report = audit_provider_release_closure(_release())
    assert report["status"] == "CLOSURE_EVIDENCE_OPEN"
    assert report["promotion_gates"]["qualified_provider_packet_allowed"] is False
    reasons = " ".join(report["blocking_reasons"])
    assert "termination basis" in reasons
    assert "termination provenance" not in reasons  # the synthetic example has provenance


def test_reviewed_isolation_packet_closes_physical_boundary_but_not_qualification():
    report = audit_provider_release_closure(_closed_release())
    assert report["status"] == "CLOSURE_READY_FOR_QUALIFICATION"
    assert report["packet_rows"][0]["checks"]["isolation_success_declared"] is True
    assert report["promotion_gates"]["closure_ready"] is True
    assert report["promotion_gates"]["qualified_provider_packet_allowed"] is False


def test_inventory_depletion_requires_zero_provider_final_mass():
    value = _closed_release()
    value["termination_basis"] = "inventory_depletion"
    value["provider_mass_balance"]["final_mass_kg"] = 0.5
    value["provider_mass_balance"]["isolation_success"] = None
    value["provider_mass_balance"]["isolation_time_s"] = None
    report = audit_provider_release_closure(value)
    assert report["status"] == "CLOSURE_EVIDENCE_OPEN"
    assert any("inventory_final_depleted" in reason for reason in report["blocking_reasons"])


def test_inventory_depletion_accepts_bound_positive_threshold_sidecar():
    value = _release()
    value["termination_basis"] = "inventory_depletion"
    evidence = {
        "termination_basis": "inventory_depletion_positive_threshold",
        "provider_result_digest": value["provider_result_digest"],
        "available_mass_kg": value["available_mass_kg"],
        "cumulative_mass_out_kg": value["cumulative_mass_out_kg"],
        "threshold_mass_kg": 0.9,
        "remaining_mass_kg": 0.8,
        "max_abs_mass_residual_kg": 0.0,
    }
    report = audit_provider_release_closure(value, termination_evidence=evidence)
    assert report["status"] == "CLOSURE_READY_FOR_QUALIFICATION"
    row = report["packet_rows"][0]
    assert row["checks"]["inventory_final_depleted"] is True
    assert row["termination_evidence_checks"]["termination_evidence_digest_matches"] is True
    assert report["promotion_gates"]["qualified_provider_packet_allowed"] is False


def test_inventory_depletion_accepts_exhausted_releasable_inventory_sidecar():
    value = _release()
    value["termination_basis"] = "inventory_depletion"
    evidence = {
        "termination_basis": "inventory_depletion_releasable_mass",
        "provider_result_digest": value["provider_result_digest"],
        "available_mass_kg": value["available_mass_kg"],
        "cumulative_mass_out_kg": value["cumulative_mass_out_kg"],
        "available_mass_definition": "cumulative releasable mass until atmospheric-pressure equilibrium",
        "remaining_releasable_mass_kg": 0.0,
        "provider_residual_mass_kg": 0.0,
    }
    report = audit_provider_release_closure(value, termination_evidence=evidence)
    assert report["status"] == "CLOSURE_READY_FOR_QUALIFICATION"
    row = report["packet_rows"][0]
    assert row["termination_evidence_mode"] == "releasable_inventory"
    assert row["checks"]["inventory_final_depleted"] is True


def test_invalid_packet_is_rejected():
    with pytest.raises(ProviderReleaseClosureError):
        audit_provider_release_closure({"provider_export_schema": "wrong"})


def test_emergency_relief_packet_uses_dedicated_provider_loader():
    packet = ROOT / "results" / "20261031" / "native_generic_scope_packets_pipefix" / "events" / "015_pressure-relief-vent-01_G1" / "resolved_release.json"
    report = audit_provider_release_closure(packet)
    assert report["status"] == "CLOSURE_READY_FOR_QUALIFICATION"
    assert report["packet_rows"][0]["event_kind"] == "emergency_relief"
