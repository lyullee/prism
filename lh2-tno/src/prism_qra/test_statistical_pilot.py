"""Statistical and physical-plumbing checks; not experimental validation."""
from __future__ import annotations

import itertools
import json

import numpy as np
import pytest

import fire
import source_term
import statistical_pilot as S


@pytest.mark.parametrize("n", [0, 1, 7, 12, True, 16.0])
def test_invalid_design_size(n):
    with pytest.raises(ValueError):
        S.sampling_design(n, 1)


def test_reproducible_paired_design():
    d = S.sampling_design(16, 12)
    again = S.sampling_design(16, 12)
    other = S.sampling_design(16, 13)
    assert len(d) == S.K + 2
    assert not np.array_equal(d["A"], other["A"])
    for key, values in d.items():
        np.testing.assert_array_equal(values, again[key])
    for j in range(S.K):
        c = d[f"AB_{j}"]
        np.testing.assert_array_equal(c[:, j], d["B"][:, j])
        np.testing.assert_array_equal(np.delete(c, j, axis=1), np.delete(d["A"], j, axis=1))


def test_transform_endpoints_and_design_measure():
    for measure in S.MEASURES:
        low = S.transform(np.zeros(S.K), measure)
        high = S.transform(np.ones(S.K), measure)
        np.testing.assert_allclose(low, [p.low for p in S.PARAMETERS])
        np.testing.assert_allclose(high, [p.high for p in S.PARAMETERS])
        S.validate_physical(low)
        S.validate_physical(high)
    mid = np.full(S.K, .5)
    assert S.transform(mid, "log_diameter")[2] == pytest.approx(np.sqrt(5.))
    assert S.transform(mid, "linear_diameter")[2] == pytest.approx(5.25)
    with pytest.raises(ValueError):
        S.transform(mid, "empirical")
    mid[0] = np.nan
    with pytest.raises(ValueError):
        S.transform(mid, S.MEASURES[0])


def test_jansen_additive_analytic_indices():
    design = S.sampling_design(4096, 71, dimensions=3)
    weights = np.array([1., 2., 0.])
    values = {key: x @ weights for key, x in design.items()}
    result = S.jansen_indices(values["A"], values["B"], [values[f"AB_{j}"] for j in range(3)])
    np.testing.assert_allclose(result["first"], [.2, .8, 0.], atol=.003)
    np.testing.assert_allclose(result["total"], [.2, .8, 0.], atol=.003)


def test_jansen_ishigami_interaction():
    design = S.sampling_design(16384, 33, dimensions=3)
    def f(u):
        x = -np.pi + 2 * np.pi * u
        return np.sin(x[:, 0]) + 7 * np.sin(x[:, 1]) ** 2 + .1 * x[:, 2] ** 4 * np.sin(x[:, 0])
    y = {key: f(x) for key, x in design.items()}
    r = S.jansen_indices(y["A"], y["B"], [y[f"AB_{j}"] for j in range(3)])
    np.testing.assert_allclose(r["first"], [.3139, .4424, 0.], atol=.015)
    np.testing.assert_allclose(r["total"], [.5576, .4424, .2437], atol=.015)


def test_no_variance_and_incomplete_design_are_not_zero_sensitivity():
    assert S.jansen_indices([1, 1], [1, 1], [[1, 1]])["status"] == "UNDEFINED_ZERO_VARIANCE"
    r = S.jansen_indices([1, 2], [1, 2], [[1, np.nan]])
    assert r["status"] == "WITHHELD_INCOMPLETE_DESIGN" and r["total"] is None
    with pytest.raises(ValueError):
        S.jansen_indices([1, 2], [1], [[1, 2]])


def test_ties_and_no_reach_not_arbitrary_rank():
    assert S.priority_mask(np.array([0, 0, 0, 0])) == 0
    assert S.priority_mask(np.array([2, 2, 1, 0])) == 3
    assert S.priority_mask(np.array([0, 0, 1, 0])) == 4
    assert S.unique_positive(4)
    assert not S.unique_positive(3)
    assert not S.unique_positive(0)
    with pytest.raises(ValueError):
        S.priority_mask(np.array([0, 0, -1, 0]))


def test_geometry_boundaries_no_self_edges_and_permutation():
    dm = S.distance_matrix("linear", 10.)
    assert np.isinf(np.diag(dm)).all()
    assert dm[0, 1] == 8.
    scores, _ = S.reach_scores(np.array([8., .1, .1, .1]), dm)
    np.testing.assert_array_equal(scores, [0, 1, 0, 0])
    length = np.array([15., 20., 5., 30.])
    scores, _ = S.reach_scores(length, dm)
    perm = [2, 0, 3, 1]
    reordered, _ = S.reach_scores(length[perm], dm[np.ix_(perm, perm)])
    np.testing.assert_array_equal(reordered, scores[perm])


def fake_cache(x):
    return {S.source_key(x[0] * ratio * 1e6, x[1]):
            {"status": "OK", "flux_kg_m2s": 22000. * ratio}
            for ratio in S.PRESSURE_MULTIPLIERS}


def test_unresolved_paths_are_never_called(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("unresolved physics called")
    for name in ("notional_nozzle", "flame_length", "radiant_fraction", "heat_flux"):
        monkeypatch.setattr(fire, name, refuse)
    x = S.transform(np.full(S.K, .5), "log_diameter")
    r = S.evaluate(x, fake_cache(x))
    assert r["status"] == "OK"
    np.testing.assert_allclose(np.array(r["flame_lengths_m"])[1] / np.array(r["flame_lengths_m"])[0], 116 / 76)
    assert np.isfinite(r["rates_kg_s"]).all()
    json.dumps(r, allow_nan=False)


def test_source_failure_and_domain_fail_closed():
    x = S.transform(np.full(S.K, .5), "log_diameter")
    cache = fake_cache(x)
    key = next(iter(cache))
    cache[key] = {"status": "FAILED", "key": key}
    r = S.evaluate(x, cache)
    assert r["status"] == "SOURCE_FAILED" and "scores" not in r
    assert np.isnan(list(S.scalar_metrics(r).values())).all()
    x[2] = 25.
    with pytest.raises(ValueError, match="REFUSED"):
        S.evaluate(x, {})


def test_source_area_and_cd_cache_factorization_and_energy():
    p, t = 35e6, 293.15
    r = S.solve_source((S.source_key(p, t), (p, t)))
    assert r["status"] == "OK"
    direct = source_term.discharge(p, t, "Hydrogen", .006, Cd=.61)
    assert direct.rate_kg_s == pytest.approx(r["flux_kg_m2s"] * np.pi * .006 ** 2 / 4 * .61, rel=1e-12)
    assert r["source_energy_relative_residual"] < 1e-12


def test_exact_source_patterns_include_interior_changes():
    # Endpoint-only enumeration would miss the two middle patterns.
    patterns = {tuple(p) for p in S.source_patterns(np.array([np.inf, 1., 2., 3.]), .5, 3.5)}
    assert patterns == {(0, 0, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0), (0, 1, 1, 1)}
    assert {tuple(p) for p in S.source_patterns(np.array([np.inf, 1., 2., 3.]), 2., 2.)} == {(0, 1, 1, 0)}


def test_information_sets_contain_dense_brute_force_and_shrink():
    x = S.transform(np.full(S.K, .55), "linear_diameter")
    x[-1] = 5.
    r = S.evaluate(x, fake_cache(x))
    for layout in S.LAYOUTS:
        full = S.possible_priorities(r, layout)
        known_all = S.possible_priorities(r, layout, (0, 1, 2, 3))
        li = list(S.LAYOUTS).index(layout)
        assert known_all == set(r["priority_masks"][li])
        assert known_all <= full
        for i in range(4):
            assert known_all <= S.possible_priorities(r, layout, (i,)) <= full
        dm = S.distance_matrix(layout, x[-1])
        for cds in itertools.product((.5, .625, .75, .875, 1.), repeat=4):
            for upper in (False, True):
                lengths = np.array([fire.molkov_flame_length(q * cd, d * .001, upper)
                                    for q, cd, d in zip(r["rate_cd1_kg_s"], cds, x[2:6])])
                _, mask = S.reach_scores(lengths, dm)
                assert mask in full


def test_all_zero_information_does_not_claim_unique_management_priority():
    x = S.transform(np.zeros(S.K), "log_diameter")
    x[-1] = 40.
    r = S.evaluate(x, fake_cache(x))
    summary = S.information_summary([r])
    for row in summary.values():
        assert row["mean_possible_priority_sets"] == [1.] * 6
        assert row["unique_priority_guaranteed_fraction"] == [0.] * 6


def test_protocol_declares_no_empirical_probabilities():
    p = S.study_protocol(256, [1, 2])
    assert len(p["parameters"]) == 11
    assert "independent physical validation" in p["claims_withheld"]
    assert "notional nozzle M01" in p["excluded"]
    assert len(p["source_hashes"]) == 3
    json.dumps(p, allow_nan=False)
