from __future__ import annotations

import json

from lh2_tno.slabx_validation_audit import audit_slabx_lh2_validation_evidence


def _write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _results():
    return {
        "generated_utc": "2026-08-25T23:53:16Z",
        "slabx_lh2_version": "0.1.2",
        "slabx_version": "1.0.6",
        "measurements_installed": True,
        "lfl_in_bracket": 5,
        "ffi": {str(i): {} for i in range(1, 7)},
        "flacs_comparison": {"rows": [{} for _ in range(6)]},
        "pool_radius": {"case": {}, "median_ratio": 1.03},
        "negative_control_lng_pool": {"max_change_pct": 0.0},
    }


def _audit():
    return {
        "passed": True,
        "checks": {
            "all_nine_scenarios_present": True,
            "dynamic_tests_passed": 51,
            "quasi_steady_tests_passed": 7,
            "mass_and_domain": True,
            "hse_endpoint_gates": True,
            "juel_holdout_rmse": True,
            "previous_numerical_matrix": True,
            "rate_integrals": True,
            "runtime_three_repeats": True,
            "original_model_snapshot_unchanged": True,
        },
        "metrics": {
            "max_scenario_mass_residual_kg": 1.0e-12,
            "runtime_repeat_inventory_difference_kg": 0.0,
        },
    }


def test_slabx_validation_evidence_is_restricted_and_digest_bound(tmp_path):
    results = _write(tmp_path, "results.json", _results())
    audit = _write(tmp_path, "audit.json", _audit())
    report = audit_slabx_lh2_validation_evidence(results, audit)
    assert report["status"] == "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
    assert report["metrics"]["ffi_case_count"] == 6
    assert report["physical_validation_claim"] is False
    assert report["facility_qra_claim"] is False
    assert report["source_results"]["sha256"]


def test_slabx_validation_failure_never_promotes_claims(tmp_path):
    results = _results()
    results["negative_control_lng_pool"]["max_change_pct"] = 1.0
    results_path = _write(tmp_path, "results.json", results)
    audit_path = _write(tmp_path, "audit.json", _audit())
    report = audit_slabx_lh2_validation_evidence(results_path, audit_path)
    assert report["status"] == "BLOCKED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
    assert "pool_and_negative_control" in [row["name"] for row in report["checks"] if row["status"] == "BLOCKED"]
    assert report["physical_validation_claim"] is False
    assert report["facility_qra_claim"] is False
