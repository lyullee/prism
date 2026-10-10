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


def test_invalid_packet_is_rejected():
    with pytest.raises(ProviderReleaseClosureError):
        audit_provider_release_closure({"provider_export_schema": "wrong"})
