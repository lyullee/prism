import json
from pathlib import Path

from lh2_tno.external_sweep_audit import audit_root, public_summary


def test_external_sweep_audit_records_closure_and_keeps_qra_closed(tmp_path: Path):
    for name, rows in {
        "sweep_results.json": [{
            "status": "COMPLETED_HORIZON",
            "runtime_s": 2.0,
            "max_mass_residual_kg": 1e-9,
            "max_energy_residual_J": 2e-8,
        }],
        "secondary_results.json": [],
        "cd_results.json": [],
        "tno_policy_results.json": [{
            "status": "COMPLETED",
            "runtime_s": 0.4,
            "qra_grade": "ENGINEERING_JUDGEMENT",
            "overall_max_ir_proxy_per_y": 1e-7,
            "hyram_single_opportunity_area_m2": 1.0,
        }],
        "risk_model_matrix.json": [],
        "vent_fire_risk_results.json": [],
    }.items():
        (tmp_path / name).write_text(json.dumps(rows), encoding="utf-8")
    (tmp_path / "all_case_summary.csv").write_text("case,status\na,COMPLETED_HORIZON\n", encoding="utf-8")

    report = audit_root(tmp_path)
    assert report["status"] == "SCREENING_ONLY_EXTERNAL_SWEEP"
    assert report["aggregate"]["tank_sweep_record_count"] == 1
    assert report["aggregate"]["all_declared_tank_cases_present"] is True
    assert report["aggregate"]["maximum_tank_mass_residual_kg"] == 1e-9
    assert report["promotion_gates"]["independent_physical_validation_claim"] is False
    assert report["promotion_gates"]["facility_ir_fn_claim"] is False
    summary = public_summary(report)
    assert summary["source_root"] == "<external-lh2-sweep-root>"
    assert str(tmp_path) not in str(summary)
