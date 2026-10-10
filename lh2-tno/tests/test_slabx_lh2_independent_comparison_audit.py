import json

from lh2_tno.slabx_lh2_independent_comparison_audit import (
    audit_slabx_lh2_independent_comparison,
)


def _write_fixture(tmp_path, *, gate_accepted=False):
    prediction = tmp_path / "predictions.csv"
    rows = [
        "sensor,radius_m,bearing_deg,height_m,observed_mean_vol_pct,SLABx_mean_wind_vol_pct,observed_LFL,SLABx_mean_wind_LFL",
        "OC_01,30,45,0.1,5.0,4.0,1,1",
        "OC_02,30,45,1.0,1.0,0.5,0,0",
    ]
    prediction.write_text("\n".join(rows) + "\n", encoding="utf-8")
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({
        "source": "published DNV P04 source ledger",
        "fitting": "none",
        "mean_wind_statistics": {
            "MAE_vol_pct": 0.75,
            "RMSE_vol_pct": 0.7905694150420949,
            "mean_bias_vol_pct": -0.75,
            "observed_LFL_pairs": 1,
            "SLABx_LFL_pairs": 1,
            "TP": 1,
            "FN": 0,
            "FP": 0,
        },
    }), encoding="utf-8")
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"numerical_gate": {"accepted": gate_accepted}}), encoding="utf-8")
    return prediction, summary, gate


def test_independent_comparison_keeps_open_source_gate_restricted(tmp_path):
    prediction, summary, gate = _write_fixture(tmp_path)
    report = audit_slabx_lh2_independent_comparison(
        prediction,
        summary,
        numerical_gate_path=gate,
        expected_sensor_count=2,
    )
    assert report["status"] == "RESTRICTED_INDEPENDENT_COMPARISON_SOURCE_GATE_OPEN"
    assert report["claims"]["independent_comparison_evidence"] is True
    assert report["claims"]["independent_physical_validation_claim"] is False
    assert report["metrics"]["TP"] == 1
    assert any("source/numerical acceptance" in item for item in report["blocking_reasons"])


def test_independent_comparison_can_be_review_ready_after_gate(tmp_path):
    prediction, summary, gate = _write_fixture(tmp_path, gate_accepted=True)
    report = audit_slabx_lh2_independent_comparison(
        prediction,
        summary,
        numerical_gate_path=gate,
        expected_sensor_count=2,
    )
    assert report["status"] == "INDEPENDENT_COMPARISON_REVIEW_READY"
    assert report["claims"]["independent_physical_validation_claim"] is False
