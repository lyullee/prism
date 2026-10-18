from dataclasses import replace
import hashlib

import pytest

from evidence_registry import (
    Artifact, EvidenceRecord, EvidenceRegistry, EvidenceUse as U,
    ReplayLevel as R, assess_registered_outputs,
)
from physics_assurance import AssuranceState as A, ComponentOutput, EvidenceStatus as E


@pytest.fixture
def chain(tmp_path):
    artifacts = []
    for role in ("code", "configuration", "observations", "predictions", "replay-audit"):
        path = tmp_path / role
        path.write_text("test-only fixture", encoding="utf-8")
        artifacts.append(Artifact(role, str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
    record = EvidenceRecord("e1", "SLAB", "code-digest", "reach", "m", "operator-a",
                            "fixture-campaign", "experiment", U.DEVELOPMENT,
                            R.MODEL, E.DIRECT, tuple(artifacts), reviewed=True)
    output = ComponentOutput("SLAB", "code-digest", "reach", "m", "operator-a",
                             "source-a", "receptor-a", ("e1",), E.DIRECT, (1., 2.))
    return record, output


def test_locked_fixture_authorizes_reporting_not_independent_validation(chain):
    record, output = chain
    result = assess_registered_outputs((output,), EvidenceRegistry((record,)))
    assert result.state is A.QUALIFIED_SINGLE
    assert not result.physical_validation_claim and not record.independent


@pytest.mark.parametrize("changes", [
    {"revision": "other"}, {"observation_operator": "other"},
    {"quantity": "height"}, {"reviewed": False}, {"replay": R.METRICS},
    {"replay": R.DOCUMENTED}, {"evidence_kind": "CFD"},
    {"evidence_kind": "synthetic"}, {"maximum_status": E.DIAGNOSTIC},
])
def test_unqualified_evidence_withheld(chain, changes):
    record, output = chain
    result = assess_registered_outputs((output,), EvidenceRegistry((replace(record, **changes),)))
    assert result.state is A.WITHHOLD_OR_ESCALATE and result.interval is None


def test_mutation_and_missing_artifact_detected(chain):
    record, output = chain
    registry = EvidenceRegistry((record,))
    from pathlib import Path
    Path(record.artifacts[0].path).write_text("changed", encoding="utf-8")
    assert "STALE_OR_MISSING_ARTIFACT:e1" in registry.check(output)
    Path(record.artifacts[0].path).unlink()
    assert "STALE_OR_MISSING_ARTIFACT:e1" in registry.check(output)


def test_unknown_and_incomplete_chain_withheld(chain):
    record, output = chain
    assert EvidenceRegistry(()).check(output) == ("UNKNOWN_EVIDENCE:e1",)
    registry = EvidenceRegistry((replace(record, artifacts=record.artifacts[:1]),))
    assert "INCOMPLETE_EVIDENCE_CHAIN:e1" in registry.check(output)


def test_conditional_evidence_cannot_promote_itself_to_direct(chain):
    record, output = chain
    record = replace(record, maximum_status=E.CONDITIONAL, conditions=("fixed effective source",))
    registry = EvidenceRegistry((record,))
    assert assess_registered_outputs((output,), registry).state is A.WITHHOLD_OR_ESCALATE
    conditional = replace(output, status=E.CONDITIONAL, conditions=record.conditions,
                          conditions_satisfied=True)
    assert assess_registered_outputs((conditional,), registry).state is A.QUALIFIED_SINGLE


def test_duplicates_and_bad_digest_rejected(chain):
    record, _ = chain
    with pytest.raises(ValueError):
        EvidenceRegistry((record, record))
    with pytest.raises(ValueError):
        Artifact("code", "path", "not-a-digest")


def test_explicit_holdout_only(chain):
    record, _ = chain
    assert replace(record, use=U.HOLDOUT).independent
    assert not replace(record, use=U.RETROSPECTIVE).independent
    assert not replace(record, use=U.HOLDOUT, evidence_kind="synthetic").independent
