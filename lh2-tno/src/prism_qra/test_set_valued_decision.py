"""Tests for exact set-valued management screening; not physical validation."""
from __future__ import annotations

import itertools

import numpy as np
import pytest

import fire
import set_valued_decision as D
import statistical_pilot as S


def fake_cache(x):
    return {S.source_key(x[0] * ratio * 1e6, x[1]):
            {"status": "OK", "flux_kg_m2s": 22000. * ratio}
            for ratio in S.PRESSURE_MULTIPLIERS}


@pytest.mark.parametrize(
    ("states", "category", "possible", "necessary"),
    [
        ([(0, 0, 0, 0)], "ALL_NO_REACH", 0, 0),
        ([(3, 1, 0, 1), (2, 1, 1, 0)], "ROBUST_UNIQUE", 1, 1),
        ([(2, 2, 0, 0), (1, 1, 0, 0)], "ROBUST_TIED_SET", 3, 3),
        ([(0, 0, 0, 0), (1, 0, 0, 0)], "INDETERMINATE_WITH_NO_REACH", 1, 0),
        ([(1, 0, 0, 0), (0, 1, 0, 0)], "INDETERMINATE_ACTIVE", 3, 0),
    ],
)
def test_decision_categories(states, category, possible, necessary):
    r = D.classify_score_states(states)
    assert r["category"] == category
    assert r["possible_top_mask"] == possible
    assert r["necessary_top_mask"] == necessary
    assert r["category"] in D.CATEGORIES


def test_correlated_states_are_not_replaced_by_independent_intervals():
    # Marginal intervals overlap, but A strictly outranks B in every correlated state.
    r = D.classify_score_states([(1, 0, 0, 0), (3, 2, 0, 0)])
    assert r["score_min"][:2] == [1, 0]
    assert r["score_max"][:2] == [3, 2]
    assert r["robust_strict_outranking"][0][1] == 1
    assert r["robust_strict_outranking"][1][0] == 0


def test_no_reach_is_never_unique_and_invalid_states_fail_closed():
    r = D.classify_score_states([(0, 0, 0, 0)])
    assert r["category"] == "ALL_NO_REACH" and r["necessary_top_count"] == 0
    for bad in ([], [(1, 2, 3)], [(1, -1, 0, 0)], [(1, np.nan, 0, 0)], [(1.5, 0, 0, 0)]):
        with pytest.raises(ValueError):
            D.classify_score_states(bad)


def test_geometry_rejects_duplicate_or_invalid_coordinates():
    with pytest.raises(ValueError):
        D.distance_matrix([(0, 0)] * 4, 1.)
    with pytest.raises(ValueError):
        D.distance_matrix([(0, 0), (1, 0), (0, 1), (1, 1)], 0.)
    dm = D.distance_matrix([(0, 0), (1, 0), (0, 1), (1, 1)], 2.)
    assert np.isinf(np.diag(dm)).all() and dm[0, 1] == 2.


def test_exact_states_contain_dense_cd_enumeration_and_information_shrinks():
    x = S.transform(np.full(S.K, .55), "linear_diameter")
    x[-1] = 5.
    result = S.evaluate(x, fake_cache(x))
    points = S.LAYOUTS["offset"]
    full = D.admissible_score_states(result, points)
    known = D.admissible_score_states(result, points, (0, 1, 2, 3))
    assert known <= full
    for source_i in range(4):
        assert known <= D.admissible_score_states(result, points, (source_i,)) <= full
    distances = D.distance_matrix(points, x[-1])
    for cds in itertools.product((.5, .625, .75, .875, 1.), repeat=4):
        for upper in (False, True):
            lengths = np.array([
                fire.molkov_flame_length(q * cd, diameter_mm * .001, upper)
                for q, cd, diameter_mm in zip(result["rate_cd1_kg_s"], cds, x[2:6])
            ])
            scores, _ = S.reach_scores(lengths, distances)
            assert tuple(int(v) for v in scores) in full


def test_curve_alternative_is_global_not_mixed_by_source():
    x = S.transform(np.full(S.K, .52), "log_diameter")
    result = S.evaluate(x, fake_cache(x))
    points = S.LAYOUTS["compact"]
    known = D.admissible_score_states(result, points, (0, 1, 2, 3))
    distances = D.distance_matrix(points, x[-1])
    expected = {
        tuple(int(v) for v in S.reach_scores(np.asarray(lengths), distances)[0])
        for lengths in result["flame_lengths_m"]
    }
    assert known == expected and len(known) <= 2


def test_permutation_invariance_of_exact_classification():
    states = {(3, 1, 2, 0), (2, 0, 3, 1), (1, 2, 3, 0)}
    permutation = [2, 0, 3, 1]
    original = D.classify_score_states(states)
    permuted = D.classify_score_states([tuple(np.asarray(s)[permutation]) for s in states])
    expected_possible = sum(
        1 << new_i for new_i, old_i in enumerate(permutation)
        if original["possible_top_mask"] & (1 << old_i)
    )
    assert permuted["category"] == original["category"]
    assert permuted["possible_top_mask"] == expected_possible
    np.testing.assert_array_equal(
        np.asarray(permuted["robust_strict_outranking"]),
        np.asarray(original["robust_strict_outranking"])[np.ix_(permutation, permutation)],
    )


def test_failed_or_nonfinite_results_fail_closed():
    points = S.LAYOUTS["linear"]
    with pytest.raises(ValueError):
        D.admissible_score_states({"status": "SOURCE_FAILED"}, points)
    x = S.transform(np.full(S.K, .5), "linear_diameter")
    result = S.evaluate(x, fake_cache(x))
    result["rate_cd1_kg_s"][0] = float("nan")
    with pytest.raises(ValueError):
        D.admissible_score_states(result, points)
