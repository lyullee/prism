"""Regression guards for explicit refusal boundaries."""

import model_gaps as G


def test_both_high_consequence_unmodelled_sequences_are_registered():
    assert {gap.gap_id for gap in G.DECLARED_GAPS} == {
        "VENT_INTERNAL_PREMIXING", "JACKET_BRITTLE_FRACTURE"
    }
    assert all(gap.status.startswith("REFUSED") for gap in G.DECLARED_GAPS)


def test_emeryville_is_not_overclaimed_as_a_confirmed_detonation():
    gap = G.VENT_INTERNAL_PREMIXING
    assert "does not establish detonation" in gap.reason
    assert "detonation pressure" in gap.prohibited_claims[1]


def test_jacket_basis_is_cryogenic_transfer_not_lh2_validation():
    gap = G.JACKET_BRITTLE_FRACTURE
    assert "nitrogen" in gap.reason
    assert "not LH2 validation" in gap.reason
    assert any("fracture-toughness" in item for item in gap.required_inputs)
