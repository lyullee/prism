"""Exact set-valued equipment-screening decisions for the GH2 pilot.

The output is a management-screening relation, not risk, failure probability,
fragility, or a facility acceptance decision.  Correlations between equipment
scores are retained by enumerating admissible score vectors.  The two related
Molkov curves are selected globally and are never mixed source by source.
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping, Sequence

import numpy as np

import fire
import statistical_pilot as S


CATEGORIES = (
    "ALL_NO_REACH",
    "ROBUST_UNIQUE",
    "ROBUST_TIED_SET",
    "INDETERMINATE_WITH_NO_REACH",
    "INDETERMINATE_ACTIVE",
)


def distance_matrix(points: Sequence[Sequence[float]], spacing: float) -> np.ndarray:
    """Return a four-equipment distance matrix with self-edges excluded."""
    xy = np.asarray(points, dtype=float)
    if xy.shape != (4, 2) or not np.isfinite(xy).all():
        raise ValueError("four finite two-dimensional equipment coordinates required")
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("positive finite spacing required")
    if len({tuple(row) for row in xy}) != 4:
        raise ValueError("equipment coordinates must be distinct")
    distances = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=-1) * spacing
    np.fill_diagonal(distances, np.inf)
    return distances


def _validate_known(known: Iterable[int]) -> tuple[int, ...]:
    indices = tuple(known)
    if any(isinstance(i, bool) or not isinstance(i, int) or i not in range(4)
           for i in indices):
        raise ValueError("known source indices must be distinct integers from 0 to 3")
    if len(set(indices)) != len(indices):
        raise ValueError("known source indices must be distinct")
    return indices


def admissible_score_states(
    result: Mapping,
    points: Sequence[Sequence[float]],
    known: Iterable[int] = (),
) -> set[tuple[int, int, int, int]]:
    """Exactly enumerate correlated inbound-score states.

    Unknown Cd values independently range over [0.5, 1].  Known values use the
    design-row Cd.  Each related curve is a whole-system alternative.
    """
    if result.get("status") != "OK":
        raise ValueError("cannot classify a failed calculation")
    known_indices = _validate_known(known)
    try:
        x = np.asarray(result["inputs"], dtype=float)
        rate_cd1 = np.asarray(result["rate_cd1_kg_s"], dtype=float)
        sampled_lengths = np.asarray(result["flame_lengths_m"], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("incomplete calculation result") from exc
    if (x.shape != (S.K,) or rate_cd1.shape != (4,) or sampled_lengths.shape != (2, 4)
            or not np.isfinite(x).all() or not np.isfinite(rate_cd1).all()
            or not np.isfinite(sampled_lengths).all() or (rate_cd1 <= 0).any()
            or (sampled_lengths <= 0).any()):
        raise ValueError("non-finite or invalid calculation result")

    distances = distance_matrix(points, float(x[-1]))
    states: set[tuple[int, int, int, int]] = set()
    for curve_i, upper in enumerate((False, True)):
        row_patterns: list[list[np.ndarray]] = []
        for source_i in range(4):
            if source_i in known_indices:
                length = sampled_lengths[curve_i, source_i]
                row_patterns.append([np.asarray(distances[source_i] <= length, dtype=int)])
                continue
            diameter_m = x[2 + source_i] * 0.001
            low = fire.molkov_flame_length(0.5 * rate_cd1[source_i], diameter_m,
                                           conservative=upper)
            high = fire.molkov_flame_length(rate_cd1[source_i], diameter_m,
                                            conservative=upper)
            row_patterns.append(S.source_patterns(distances[source_i], low, high))
        for rows in itertools.product(*row_patterns):
            scores = np.sum(rows, axis=0)
            states.add(tuple(int(v) for v in scores))
    if not states:
        raise AssertionError("exact enumeration produced no admissible state")
    return states


def classify_score_states(states: Iterable[Sequence[int]]) -> dict:
    """Summarize exact score states without discarding ties or empty states."""
    normalized: set[tuple[int, int, int, int]] = set()
    for state in states:
        values = np.asarray(state)
        if (values.shape != (4,) or not np.issubdtype(values.dtype, np.number)
                or not np.isfinite(values).all() or (values < 0).any()
                or not np.equal(values, np.floor(values)).all()):
            raise ValueError("score states must contain four finite non-negative integers")
        normalized.add(tuple(int(v) for v in values))
    if not normalized:
        raise ValueError("at least one admissible score state required")

    masks = tuple(sorted({S.priority_mask(np.asarray(state)) for state in normalized}))
    if masks == (0,):
        category = "ALL_NO_REACH"
    elif len(masks) == 1 and S.unique_positive(masks[0]):
        category = "ROBUST_UNIQUE"
    elif len(masks) == 1:
        category = "ROBUST_TIED_SET"
    elif 0 in masks:
        category = "INDETERMINATE_WITH_NO_REACH"
    else:
        category = "INDETERMINATE_ACTIVE"

    possible_top_mask = 0
    necessary_top_mask = 15
    for mask in masks:
        possible_top_mask |= mask
        necessary_top_mask &= mask
    values = np.asarray(sorted(normalized), dtype=int)
    robust_out = np.zeros((4, 4), dtype=bool)
    possible_out = np.zeros((4, 4), dtype=bool)
    robust_not_lower = np.zeros((4, 4), dtype=bool)
    for i in range(4):
        for j in range(4):
            if i == j:
                continue
            robust_out[i, j] = bool(np.all(values[:, i] > values[:, j]))
            possible_out[i, j] = bool(np.any(values[:, i] > values[:, j]))
            robust_not_lower[i, j] = bool(np.all(values[:, i] >= values[:, j]))

    return {
        "category": category,
        "admissible_score_state_count": len(normalized),
        "admissible_top_masks": list(masks),
        "possible_top_mask": int(possible_top_mask),
        "necessary_top_mask": int(necessary_top_mask),
        "possible_top_count": int(possible_top_mask.bit_count()),
        "necessary_top_count": int(necessary_top_mask.bit_count()),
        "score_min": values.min(axis=0).tolist(),
        "score_max": values.max(axis=0).tolist(),
        "robust_strict_outranking": robust_out.astype(int).tolist(),
        "possible_strict_outranking": possible_out.astype(int).tolist(),
        "robust_not_lower": robust_not_lower.astype(int).tolist(),
    }


def classify_result(
    result: Mapping,
    points: Sequence[Sequence[float]],
    known: Iterable[int] = (),
) -> dict:
    """Enumerate and classify one conditional design row."""
    return classify_score_states(admissible_score_states(result, points, known))
