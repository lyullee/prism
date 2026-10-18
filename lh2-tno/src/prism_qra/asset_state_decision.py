"""General N-asset screening from whole-system joint influence states.

No independent marginal-interval combinations or model averaging. The score
is inbound reach count only: NOT failure probability, risk or fragility.
Physical qualification belongs to the upstream registered-component boundary.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JointInfluenceState:
    state_id: str
    model_id: str
    source_fingerprint: str
    observation_operator: str
    source_ids: tuple[str, ...]
    asset_ids: tuple[str, ...]
    edges: tuple[tuple[bool, ...], ...]

    def __post_init__(self):
        for name in ("state_id", "model_id", "source_fingerprint", "observation_operator"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} required")
        for name in ("source_ids", "asset_ids"):
            values = getattr(self, name)
            if (not isinstance(values, tuple) or not values
                    or any(not isinstance(x, str) or not x.strip() for x in values)
                    or len(set(values)) != len(values)):
                raise ValueError(f"unique nonempty {name} required")
        if not isinstance(self.edges, tuple) or len(self.edges) != len(self.source_ids):
            raise ValueError("one edge row required per source")
        for source_id, row in zip(self.source_ids, self.edges):
            if (not isinstance(row, tuple) or len(row) != len(self.asset_ids)
                    or any(type(x) is not bool for x in row)):
                raise ValueError("boolean edge required per asset")
            if source_id in self.asset_ids and row[self.asset_ids.index(source_id)]:
                raise ValueError("self-influence edges must be excluded")

    @property
    def scores(self) -> tuple[int, ...]:
        return tuple(sum(row[i] for row in self.edges) for i in range(len(self.asset_ids)))


def summarize_joint_states(states: tuple[JointInfluenceState, ...]) -> dict:
    """Exact logical summary of a declared finite set; no truth-coverage claim."""
    if (not isinstance(states, tuple) or not states
            or any(not isinstance(s, JointInfluenceState) for s in states)):
        raise ValueError("nonempty tuple of joint influence states required")
    if len({s.state_id for s in states}) != len(states):
        raise ValueError("state ids must be unique")
    first = states[0]
    for state in states[1:]:
        if (state.asset_ids != first.asset_ids or state.source_ids != first.source_ids
                or state.observation_operator != first.observation_operator):
            raise ValueError("states require matched asset/source order and observation operator")
    score_vectors = sorted({s.scores for s in states})
    top_sets = set()
    for scores in score_vectors:
        highest = max(scores)
        top_sets.add(tuple(i for i, x in enumerate(scores) if x == highest) if highest else ())
    possible = set().union(*(set(t) for t in top_sets))
    necessary = set(range(len(first.asset_ids))).intersection(*(set(t) for t in top_sets))
    if top_sets == {()}:
        category = "ALL_NO_REACH"
    elif len(top_sets) == 1:
        category = "ROBUST_UNIQUE" if len(next(iter(top_sets))) == 1 else "ROBUST_TIED_SET"
    else:
        category = "INDETERMINATE_WITH_NO_REACH" if () in top_sets else "INDETERMINATE_ACTIVE"
    n = len(first.asset_ids)
    return {
        "category": category, "asset_ids": list(first.asset_ids),
        "declared_state_count": len(states), "distinct_score_state_count": len(score_vectors),
        "model_ids": sorted({s.model_id for s in states}),
        "admissible_top_sets": [[first.asset_ids[i] for i in t] for t in sorted(top_sets)],
        "possible_top": [first.asset_ids[i] for i in sorted(possible)],
        "necessary_top": [first.asset_ids[i] for i in sorted(necessary)],
        "score_min": [min(s[i] for s in score_vectors) for i in range(n)],
        "score_max": [max(s[i] for s in score_vectors) for i in range(n)],
        "robust_strict_outranking": [[int(i != j and all(s[i] > s[j] for s in score_vectors))
                                      for j in range(n)] for i in range(n)],
        "score_definition": "inbound reach count; not probability, risk or fragility",
        "physical_validation_claim": False,
        "qualification": "logical summary only; upstream evidence/applicability gate required",
    }
