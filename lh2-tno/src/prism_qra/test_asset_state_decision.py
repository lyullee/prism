from dataclasses import replace

import pytest

from asset_state_decision import JointInfluenceState, summarize_joint_states


def state(edges, state_id="s1", assets=("A", "B", "C", "D", "E")):
    return JointInfluenceState(state_id, "fixture-model", "fixture-source", "fixture-operator",
                               ("source",), assets, (tuple(edges),))


def test_n_asset_possible_necessary_and_no_false_unique():
    a = state((True, False, False, False, False))
    b = state((False, True, False, False, False), "s2")
    r = summarize_joint_states((a, b))
    assert r["category"] == "INDETERMINATE_ACTIVE"
    assert r["possible_top"] == ["A", "B"] and r["necessary_top"] == []
    assert not r["physical_validation_claim"]


def test_no_reach_does_not_generate_priority_and_ties_retained():
    z = state((False,)*5)
    assert summarize_joint_states((z,))["admissible_top_sets"] == [[]]
    a = state((True, True, False, False, False), "s2")
    assert summarize_joint_states((a,))["category"] == "ROBUST_TIED_SET"
    r = summarize_joint_states((z, a))
    assert r["category"] == "INDETERMINATE_WITH_NO_REACH" and not r["necessary_top"]


def test_sixty_five_assets_have_no_bitmask_overflow():
    ids = tuple(f"asset-{i}" for i in range(65))
    s = state((False,)*64+(True,), assets=ids)
    assert summarize_joint_states((s,))["necessary_top"] == ["asset-64"]


def test_correlated_whole_system_states_not_marginalized():
    s = JointInfluenceState("s1", "model-a", "source", "operator", ("x", "y", "z"),
                            ("A", "B"), ((True, False), (False, False), (False, False)))
    t = replace(s, state_id="s2", model_id="model-b",
                edges=((True, True), (True, True), (True, False)))
    r = summarize_joint_states((s, t))
    assert r["score_min"] == [1, 0] and r["score_max"] == [3, 2]
    assert r["robust_strict_outranking"] == [[0, 1], [0, 0]]
    assert r["necessary_top"] == ["A"]


def test_self_edges_are_checked_by_identity_not_index():
    with pytest.raises(ValueError):
        JointInfluenceState("s", "m", "source", "operator", ("B",), ("A", "B"), ((False, True),))
    s = JointInfluenceState("s", "m", "source", "operator", ("B",), ("A", "B"), ((True, False),))
    assert s.scores == (1, 0)


@pytest.mark.parametrize("changes", [
    {"edges": ((1, 0, 0, 0, 0),)}, {"asset_ids": ("A", "A")},
    {"source_ids": ()}, {"edges": ((True,),)}, {"source_fingerprint": ""},
])
def test_invalid_state_rejected(changes):
    with pytest.raises(ValueError):
        replace(state((False,)*5), **changes)


def test_duplicate_ids_and_unmatched_operator_rejected():
    s = state((False,)*5)
    with pytest.raises(ValueError):
        summarize_joint_states((s, s))
    with pytest.raises(ValueError):
        summarize_joint_states((s, replace(s, state_id="s2", observation_operator="other")))
