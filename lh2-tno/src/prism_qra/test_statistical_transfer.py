"""Protocol and transfer-plumbing tests; not external physical validation."""
from __future__ import annotations

import json

import numpy as np
import pytest

import set_valued_decision as D
import statistical_pilot as S
import statistical_transfer as T


def fake_result():
    x = S.transform(np.full(S.K, .5), "linear_diameter")
    cache = {S.source_key(x[0] * ratio * 1e6, x[1]):
             {"status": "OK", "flux_kg_m2s": 22000. * ratio}
             for ratio in S.PRESSURE_MULTIPLIERS}
    return S.evaluate(x, cache)


def test_layout_partition_is_distinct_and_valid():
    T.validate_layout_partition()
    assert len(T.ALL_LAYOUTS) == 6
    assert not set(S.LAYOUTS) & set(T.HOLDOUT_LAYOUTS)
    for points in T.ALL_LAYOUTS.values():
        dm = D.distance_matrix(points, 1.)
        assert dm.shape == (4, 4) and np.isinf(np.diag(dm)).all()


def test_layout_outputs_and_scalar_metric_order():
    result = fake_result()
    layouts = T.layout_outputs(result)
    assert list(layouts) == list(T.ALL_LAYOUTS)
    for value in layouts.values():
        assert np.asarray(value["scores"]).shape == (2, 4)
        assert len(value["priority_masks"]) == 2
        assert value["edge_counts"] == np.asarray(value["scores"]).sum(axis=1).tolist()
    metrics = T.scalar_metrics(result, layouts)
    assert len(metrics) == 2 + len(T.ALL_LAYOUTS) * len(S.CURVES)
    assert np.isfinite(list(metrics.values())).all()


def test_sensitivity_summary_uses_eight_scrambles_and_declared_rule():
    records = []
    for seed in (*T.PILOT_SEEDS, *T.NEW_SEEDS):
        for n, total in ((128, [.2] * S.K), (256, [.21] * S.K)):
            records.append({"measure": "m", "metric": "y", "seed": seed, "n": n,
                            "status": "ESTIMATED", "first": [.1] * S.K, "total": total})
    r = T.summarize_sensitivity(records, 256)["m|y"]
    assert r["scrambles"] == 8
    assert r["exploratory_convergence_supported"]
    assert r["max_total_prefix_change_128_to_256"] == pytest.approx(.01)
    records[-1]["total"][0] = 1.2
    r = T.summarize_sensitivity(records, 256)["m|y"]
    assert not r["exploratory_convergence_supported"]


def test_rank_and_decision_helpers_preserve_empty_and_ties():
    result = fake_result()
    result.update({"measure": "linear_diameter", "seed": T.PILOT_SEEDS[0],
                   "block": "A", "index": 0})
    rank = T.rank_replicates([result])
    assert len(rank) == len(T.ALL_LAYOUTS)
    for row in rank:
        assert 0 <= row["priority_set_change_fraction"] <= 1
    decision = D.classify_result(result, T.HOLDOUT_LAYOUTS["triangle_tail"])
    compact = T.compact_decision(decision)
    assert compact["category"] in D.CATEGORIES
    assert "robust_strict_outranking" in compact


def test_prepare_locks_before_evaluation_and_refuses_nonempty(tmp_path):
    pilot = tmp_path / "pilot"
    pilot.mkdir()
    pilot_protocol = S.study_protocol(256, list(T.PILOT_SEEDS))
    (pilot / "protocol.json").write_text(json.dumps(pilot_protocol), encoding="utf-8")
    for name in ("design_results.jsonl", "sensitivity_estimates.json", "summary.json"):
        (pilot / name).write_text("{}\n", encoding="utf-8")
    hashes = {name: T.sha256(pilot / name) for name in
              ("protocol.json", "design_results.jsonl", "sensitivity_estimates.json", "summary.json")}
    (pilot / "artifact_hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    output = tmp_path / "out"
    declared = T.prepare_output(output, 256, pilot)
    assert declared["post_pilot_pre_evaluation_layouts"] == T.HOLDOUT_LAYOUTS
    assert (output / "protocol.json").is_file()
    T.prepare_output(output, 256, pilot)
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "unexpected.txt").write_text("x")
    with pytest.raises(ValueError, match="empty"):
        T.prepare_output(dirty, 256, pilot)
