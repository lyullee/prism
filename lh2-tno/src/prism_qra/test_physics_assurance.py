"""Contract/decision logic verification only; no experimental validation."""
from dataclasses import replace

import pytest

from physics_assurance import (
    AssuranceState as A, ComponentOutput, EvidenceStatus as E, assess_outputs,
)


def output(**changes):
    base = ComponentOutput("SLAB", "test-version", "LFL reach", "m",
                           "instantaneous at z=1m", "source-a", "receptor-a",
                           ("test-evidence",), E.DIRECT, (10., 20.),
                           shared_limitations=("integral-model",))
    return replace(base, **changes)


def test_single_and_overlap_envelope_do_not_claim_validation():
    r = assess_outputs((output(),))
    assert r.state is A.QUALIFIED_SINGLE and r.interval == (10., 20.)
    r = assess_outputs((output(), output(component="DEGADIS", interval=(15., 30.))))
    assert r.state is A.QUALIFIED_ENVELOPE and r.interval == (10., 30.)
    assert r.shared_limitations == ("integral-model",)
    assert not r.physical_validation_claim


def test_disjoint_sets_are_not_averaged_or_reported_as_safe_bound():
    r = assess_outputs((output(), output(component="DEGADIS", interval=(21., 30.))))
    assert r.state is A.MODEL_CONFLICT and r.interval is None
    assert len(r.components) == 2


@pytest.mark.parametrize("field,value", [
    ("quantity", "cloud height"), ("unit", "cm"),
    ("observation_operator", "30-second mean"),
    ("source_fingerprint", "source-b"), ("receptor_fingerprint", "receptor-b"),
])
def test_mismatched_outputs_withheld(field, value):
    r = assess_outputs((output(), output(component="DEGADIS", **{field: value})))
    assert r.state is A.WITHHOLD_OR_ESCALATE and r.interval is None


@pytest.mark.parametrize("status", [E.DIAGNOSTIC, E.ADVISORY, E.OUT_OF_SCOPE])
def test_nonreportable_member_not_silently_dropped(status):
    member = output(component="DEGADIS", status=status,
                    interval=None if status is E.OUT_OF_SCOPE else (10., 20.))
    assert assess_outputs((output(), member)).state is A.WITHHOLD_OR_ESCALATE


def test_conditional_requires_declared_and_satisfied_conditions():
    with pytest.raises(ValueError):
        output(status=E.CONDITIONAL)
    c = output(status=E.CONDITIONAL, conditions=("declared pool-source mapping",))
    assert assess_outputs((c,)).interval is None
    assert assess_outputs((replace(c, conditions_satisfied=True),)).state is A.QUALIFIED_SINGLE


@pytest.mark.parametrize("changes", [
    {"interval": (float("nan"), 20.)}, {"interval": (20., 10.)},
    {"interval": (True, 20.)}, {"evidence_ids": ()}, {"version": ""},
    {"status": "direct"}, {"conditions_satisfied": "yes"},
    {"status": E.OUT_OF_SCOPE}, {"interval": [10., 20.]},
])
def test_invalid_contract_rejected(changes):
    with pytest.raises(ValueError):
        output(**changes)


def test_missing_and_duplicate_outputs_withheld():
    assert assess_outputs(()).state is A.WITHHOLD_OR_ESCALATE
    assert assess_outputs((output(), output())).state is A.WITHHOLD_OR_ESCALATE


def test_touching_intervals_keep_full_envelope():
    r = assess_outputs((output(), output(component="DEGADIS", interval=(20., 30.))))
    assert r.state is A.QUALIFIED_ENVELOPE and r.interval == (10., 30.)
