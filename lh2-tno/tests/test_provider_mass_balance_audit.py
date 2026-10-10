import pytest

from lh2_tno.provider_mass_balance_audit import audit_provider_mass_balance_records


def test_audit_distinguishes_closed_partial_and_unbalanced_provider_ledgers():
    records = [
        {
            "provider_model": "closed",
            "data": {
                "event_id": "closed",
                "component_id": "pipe-1",
                "cumulative_mass_out_kg": 1.0,
                "provider_meta": {
                    "initial_mass_kg": 2.0,
                    "final_mass_kg": 1.0,
                    "residual_mass_kg": 0.0,
                },
            },
        },
        {
            "provider_model": "partial",
            "data": {
                "event_id": "partial",
                "component_id": "valve-1",
                "cumulative_mass_out_kg": 0.1,
                "provider_meta": {"residual_mass_kg": 9.9},
            },
        },
        {
            "provider_model": "unbalanced",
            "data": {
                "event_id": "unbalanced",
                "component_id": "pipe-2",
                "cumulative_mass_out_kg": 1.0,
                "provider_meta": {
                    "initial_mass_kg": 2.0,
                    "final_mass_kg": 1.2,
                    "residual_mass_kg": 1.2,
                },
            },
        },
    ]
    report = audit_provider_mass_balance_records(records)
    assert report["status_counts"] == {
        "CLOSED": 1,
        "PARTIAL": 1,
        "UNBALANCED": 1,
    }
    assert report["promotion_allowed"] is False
    assert report["rows"][2]["provider_mass_balance"]["derived_accounting_residual_kg"] == pytest.approx(0.2)
