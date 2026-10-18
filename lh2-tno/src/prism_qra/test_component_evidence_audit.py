import copy

import pytest

from audit_component_evidence import audit_levels, metrics, sensor_rows


def fixture_rows():
    rows, observations = [], []
    for i in range(30):
        o = 5. if i == 0 else 1.
        p = 5.1 if i == 0 else 1.1
        row = {"test": 4, "sensor": f"s{i}", "radius_m": 30., "height_m": .1,
               "sensor_bearing_deg": 90., "model_axis_bearing_deg": 90.,
               "x_downwind_m": 30., "y_crosswind_m": 0., "averaging_time_s": 275.,
               "observed_time_mean_vol_pct": o, "SLABx_time_mean_vol_pct": p,
               "residual_vol_pct": p-o, "observed_LFL": int(o >= 4), "SLABx_LFL": int(p >= 4)}
        rows.append(row)
        observations.append({"test": 4, "sensor": f"s{i}", "R_m": 30., "z_m": .1,
                             "bearing_deg": 90., "averaging_time_s": 275.,
                             "observed_mean_vol_pct": o})
    return rows, observations


def summaries(prior, final):
    return [{"n_field_steps": n, **metrics(sensor_rows(rows))}
            for n, rows in ((320, prior), (640, final))]


def test_metrics_and_sensorwise_gate():
    rows, obs = fixture_rows()
    r = audit_levels(rows, rows, summaries(rows, rows), obs)
    assert r["stored_refinement_gate_passed"]
    assert r["metrics"]["TN"] == 29
    assert not r["model_replayed"] and not r["physical_validation_claim"]


def test_equal_counts_do_not_hide_changed_sensor_members():
    rows, obs = fixture_rows()
    # Swap two predictions on observationally identical positive sensors.
    rows[1]["observed_time_mean_vol_pct"] = 5.
    obs[1]["observed_mean_vol_pct"] = 5.
    rows[1]["observed_LFL"] = 1
    rows[1]["residual_vol_pct"] = rows[1]["SLABx_time_mean_vol_pct"]-5.
    final = copy.deepcopy(rows)
    for i, value in ((0, 1.1), (1, 5.1)):
        final[i]["SLABx_time_mean_vol_pct"] = value
        final[i]["residual_vol_pct"] = value-5.
        final[i]["SLABx_LFL"] = int(value >= 4)
    assert metrics(sensor_rows(rows)) == metrics(sensor_rows(final))
    r = audit_levels(rows, final, summaries(rows, final), obs)
    assert r["sensor_LFL_change_count"] == 2
    assert not r["stored_refinement_gate_passed"]


@pytest.mark.parametrize("field,value", [("SLABx_time_mean_vol_pct", float("nan")),
                                         ("observed_LFL", 0), ("residual_vol_pct", 99.)])
def test_invalid_saved_values_rejected(field, value):
    rows, _ = fixture_rows()
    rows[0][field] = value
    with pytest.raises(ValueError):
        sensor_rows(rows)


def test_changed_support_observations_and_summary_rejected():
    rows, obs = fixture_rows()
    final = copy.deepcopy(rows)
    final[0]["averaging_time_s"] = 30.
    with pytest.raises(ValueError):
        audit_levels(rows, final, summaries(rows, final), obs)
    obs[0]["observed_mean_vol_pct"] = 6.
    with pytest.raises(ValueError):
        audit_levels(rows, rows, summaries(rows, rows), obs)
    rows, obs = fixture_rows()
    saved = summaries(rows, rows)
    saved[1]["TP"] = 2
    with pytest.raises(ValueError):
        audit_levels(rows, rows, saved, obs)
