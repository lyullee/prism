"""Sequential N=512 extension tests; not physical validation."""
from __future__ import annotations

import numpy as np

import statistical_convergence_extension as E
import statistical_pilot as S


def test_n256_is_exact_prefix_of_n512_for_every_block_and_seed():
    for seed in E.SEEDS:
        E.assert_prefix_identity(seed)
        prior = S.sampling_design(E.PRIOR_N, seed)
        extended = S.sampling_design(E.FINAL_N, seed)
        for block in prior:
            np.testing.assert_array_equal(prior[block], extended[block][:E.PRIOR_N])
            assert not np.array_equal(prior[block], extended[block][E.PRIOR_N:])


def make_records(final_total: float = .22, prior_total: float = .2):
    records = []
    for measure in S.MEASURES:
        for metric in E.EDGE_METRICS:
            for seed in E.SEEDS:
                for n, value in ((E.PRIOR_N, prior_total), (E.FINAL_N, final_total)):
                    records.append({
                        "measure": measure, "metric": metric, "seed": seed, "n": n,
                        "status": "ESTIMATED", "first": [.1] * S.K,
                        "total": [value] * S.K,
                    })
    return records


def test_locked_metric_rule_passes_only_when_every_condition_passes():
    summary = E.summarize(make_records())
    assert len(summary) == len(S.MEASURES) * len(E.EDGE_METRICS)
    assert all(item["status"] == "PRIMARY_ELIGIBLE" for item in summary.values())

    change_failure = E.summarize(make_records(final_total=.31))
    assert all(item["status"] == "EXPLORATORY_APPENDIX"
               for item in change_failure.values())


def test_iqr_and_estimator_excursion_fail_closed():
    records = make_records()
    target = next(r for r in records if r["n"] == E.FINAL_N)
    target["total"][0] = 1.2
    result = E.summarize(records)
    item = result[f"{target['measure']}|{target['metric']}"]
    assert item["estimator_excursion_n512"]
    assert item["status"] == "EXPLORATORY_APPENDIX"


def test_tail_design_has_expected_rows_and_no_prefix_overlap():
    tails = E.tail_designs()
    assert set(tails) == set(E.SEEDS)
    for seed, blocks in tails.items():
        assert set(blocks) == set(S.sampling_design(E.PRIOR_N, seed))
        assert all(values.shape == (E.PRIOR_N, S.K) for values in blocks.values())
        prior = S.sampling_design(E.PRIOR_N, seed)
        for block in blocks:
            assert not np.array_equal(prior[block], blocks[block])
