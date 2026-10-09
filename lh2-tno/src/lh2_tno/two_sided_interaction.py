"""Conservative diagnostics for paired two-sided rupture endpoints.

The two provider endpoints are still solved independently.  This module does
not invent a joint plume solution; it records the Frechet intersection range
that remains unresolved and keeps the conservative union upper bound used by
the facility risk ledger.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


IGNITION_BRANCHES = (
    "direct_fire",
    "delayed_flash_fire",
    "delayed_explosion",
    "no_ignition",
)


def combine_endpoint_harm(
    endpoint_harms: Sequence[Mapping[str, Sequence[Mapping[str, float]]]],
    receptor_ids: Sequence[str],
) -> dict[str, Any]:
    """Combine two endpoint harm maps without assigning a second frequency.

    ``endpoint_harms`` contains the ``branch_harm_low_high`` map from each
    endpoint result.  For every receptor and ignition branch, the returned
    ``intersection_interval_low_high`` gives the Frechet lower/upper interval
    for the unknown joint harm.  The reported harm remains the conservative
    union upper bound ``min(1, h_a + h_b)``.
    """
    if len(endpoint_harms) != 2:
        raise ValueError("two-sided interaction requires exactly two endpoint harm maps")
    ids = tuple(str(value) for value in receptor_ids)
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("two-sided interaction requires unique receptor IDs")
    if any(set(mapping) != set(ids) for mapping in endpoint_harms):
        raise ValueError("each endpoint must report every facility receptor exactly once")

    combined: dict[str, Any] = {}
    unresolved = 0
    for receptor_id in ids:
        first = endpoint_harms[0][receptor_id]
        second = endpoint_harms[1][receptor_id]
        if len(first) != 2 or len(second) != 2:
            raise ValueError("endpoint harm must contain low/high radiation endpoints")
        if any(set(row) != set(IGNITION_BRANCHES) for row in (*first, *second)):
            raise ValueError("endpoint harm must contain all ignition branches")
        if any(
            first[0][branch] > first[1][branch] + 1e-12
            or second[0][branch] > second[1][branch] + 1e-12
            for branch in IGNITION_BRANCHES
        ):
            raise ValueError("endpoint harm must preserve low/high radiation ordering")
        branch_harm: list[dict[str, float]] = []
        endpoint_harm: dict[str, list[list[float]]] = {}
        intersection: dict[str, list[list[float]]] = {}
        for radiation_index in range(2):
            branch_row: dict[str, float] = {}
            for branch in IGNITION_BRANCHES:
                left = float(first[radiation_index][branch])
                right = float(second[radiation_index][branch])
                if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in (left, right)):
                    raise ValueError("endpoint harm probabilities must be finite in [0, 1]")
                if branch == "no_ignition" and (left != 0.0 or right != 0.0):
                    raise ValueError("no-ignition branch cannot carry harm")
                branch_row[branch] = min(1.0, left + right)
                if radiation_index == 0:
                    endpoint_harm[branch] = [
                        [float(first[0][branch]), float(first[1][branch])],
                        [float(second[0][branch]), float(second[1][branch])],
                    ]
                    intersection[branch] = [
                        [max(0.0, left + right - 1.0), min(left, right)],
                        [
                            max(0.0, float(first[1][branch]) + float(second[1][branch]) - 1.0),
                            min(float(first[1][branch]), float(second[1][branch])),
                        ],
                    ]
                    if intersection[branch][0][1] > intersection[branch][0][0] + 1e-12 or intersection[branch][1][1] > intersection[branch][1][0] + 1e-12:
                        unresolved += 1
            branch_harm.append(branch_row)
        if any(branch_harm[0][key] > branch_harm[1][key] + 1e-12 for key in IGNITION_BRANCHES):
            raise ValueError("combined harm must preserve low/high radiation ordering")
        combined[receptor_id] = {
            "branch_harm_low_high": branch_harm,
            "endpoint_harm_low_high": endpoint_harm,
            "intersection_interval_low_high": intersection,
        }
    return {
        "receptors": combined,
        "schema_version": "prism.two_sided_interaction_diagnostic.v1",
        "endpoint_count": 2,
        "combination": "frechet_union_upper_bound",
        "intersection_interval": "Frechet lower/upper bounds; joint plume interaction is unresolved",
        "unresolved_branch_count": unresolved,
        "joint_interaction_resolved": False,
        "frequency_application": "one shared two-sided initiating event; endpoint frequency is not split or duplicated",
    }


__all__ = ["IGNITION_BRANCHES", "combine_endpoint_harm"]
