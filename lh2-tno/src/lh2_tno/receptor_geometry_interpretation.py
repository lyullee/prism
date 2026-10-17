"""Interpret conditional receptor-risk results without promoting a facility QRA.

The generic full-scope example declares a worker receptor 20 m from the nearest
declared equipment source.  Its conditional IR/F-N can therefore be zero even
when the release-to-consequence chain is numerically executed.  This module
keeps that geometry effect explicit by comparing the full-scope record with the
separate 0.5 m near-receptor diagnostic.  The two records are intentionally
kept separate: the near-receptor result is not copied into the full facility
assessment and does not qualify a facility total.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "prism.receptor_geometry_interpretation.v1"
FACILITY_GEOMETRY_SCHEMA = "prism.facility_receptor_geometry.v1"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _positions(manifest: Mapping[str, Any]) -> tuple[list[str], list[list[float]]]:
    receptors = manifest.get("receptors")
    if not isinstance(receptors, list) or not receptors:
        raise ValueError("manifest must declare at least one receptor")
    ids: list[str] = []
    positions: list[list[float]] = []
    for row in receptors:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str):
            raise ValueError("each receptor must have a string id")
        position = row.get("position_enu_m")
        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("each receptor must have a three-element position_enu_m")
        coords = [float(value) for value in position]
        if not all(math.isfinite(value) for value in coords):
            raise ValueError("receptor coordinates must be finite")
        ids.append(row["id"])
        positions.append(coords)
    return ids, positions


def _nearest_component(
    manifest: Mapping[str, Any], receptor: Sequence[float]
) -> tuple[str, float]:
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("manifest must declare components")
    candidates: list[tuple[str, float]] = []
    for component in components:
        if not isinstance(component, Mapping) or not isinstance(component.get("id"), str):
            continue
        # A facility boundary is a bookkeeping object, not an accident source.
        # Excluding it avoids making a receptor appear closer to a release than
        # the declared equipment actually is.
        if component.get("kind") == "boundary":
            continue
        position = component.get("position_enu_m")
        if not isinstance(position, list) or len(position) != 3:
            continue
        distance = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(position, receptor)))
        candidates.append((component["id"], distance))
    if not candidates:
        raise ValueError("manifest components have no usable positions")
    return min(candidates, key=lambda item: (item[1], item[0]))


def build_facility_receptor_geometry(
    facility: Mapping[str, Any] | Any,
    *,
    annual_conditions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the explicit receptor/population contract carried by a facility result.

    The consequence backend already evaluates every declared receptor.  This
    sidecar makes the geometry and annual-condition population closure
    inspectable at the same boundary, so a zero IR/F-N value cannot be
    mistaken for a missing receptor or an implicitly invented population.
    It is descriptive only and never changes risk, frequency, or promotion
    state.
    """
    if hasattr(facility, "model_dump"):
        facility = facility.model_dump(mode="json")
    if not isinstance(facility, Mapping):
        raise ValueError("facility must be a mapping or a model with model_dump")
    receptor_ids, receptor_positions = _positions(
        {
            "receptors": facility.get("receptors"),
        }
    )
    rows: list[dict[str, Any]] = []
    for receptor_id, position in zip(receptor_ids, receptor_positions):
        component_id, distance = _nearest_component(facility, position)
        rows.append(
            {
                "receptor_id": receptor_id,
                "position_enu_m": position,
                "nearest_component_id": component_id,
                "nearest_component_distance_m": distance,
            }
        )

    condition_rows: list[dict[str, Any]] = []
    mismatch_ids: dict[str, dict[str, list[str]]] = {}
    invalid_rows: dict[str, list[int]] = {}
    population_row_count = 0
    expected = set(receptor_ids)
    for condition in annual_conditions:
        if not isinstance(condition, Mapping):
            continue
        condition_id = str(condition.get("id", ""))
        population = condition.get("population")
        observed: list[str] = []
        if isinstance(population, Sequence) and not isinstance(population, (str, bytes)):
            for index, row in enumerate(population):
                if not isinstance(row, Mapping) or not row.get("receptor_id"):
                    invalid_rows.setdefault(condition_id, []).append(index)
                    continue
                receptor_id = str(row["receptor_id"])
                observed.append(receptor_id)
                population_row_count += 1
        observed_set = set(observed)
        if observed_set != expected or len(observed) != len(observed_set):
            mismatch_ids[condition_id] = {
                "expected": sorted(expected),
                "observed": sorted(observed_set),
            }
        condition_rows.append(
            {
                "condition_id": condition_id,
                "annual_probability": condition.get("annual_probability"),
                "population_receptor_ids": sorted(observed_set),
                "population_row_count": len(observed),
                "population_provenance": condition.get("provenance"),
            }
        )
    population_status = (
        "EXPLICIT_RECEPTOR_POPULATION_CLOSED"
        if condition_rows and not mismatch_ids and not invalid_rows
        else "RECEPTOR_POPULATION_REVIEW_REQUIRED"
    )
    return {
        "schema_version": FACILITY_GEOMETRY_SCHEMA,
        "status": "EXPLICIT_FACILITY_RECEPTOR_GEOMETRY",
        "facility_id": facility.get("id", facility.get("facility_id")),
        "environment": facility.get("environment"),
        "receptor_count": len(rows),
        "receptors": rows,
        "population_contract": {
            "status": population_status,
            "annual_condition_count": len(condition_rows),
            "population_row_count": population_row_count,
            "expected_receptor_ids": sorted(expected),
            "mismatched_condition_ids": mismatch_ids,
            "invalid_population_rows": invalid_rows,
            "zero_population_rows_must_be_explicit": True,
            "frequency_inference_performed": False,
        },
        "semantics": (
            "receptor positions are facility coordinates; nearest component is a geometry diagnostic; "
            "annual-condition population is the only occupancy input and is never inferred"
        ),
    }


def _ir_values(assessment: Mapping[str, Any]) -> list[float]:
    values = assessment.get("conditional_diagnostic_facility_annual_ir_low_high")
    if not isinstance(values, Mapping):
        raise ValueError("assessment must contain conditional annual IR/FN values")
    flattened: list[float] = []
    for value in values.values():
        if not isinstance(value, list):
            raise ValueError("conditional annual IR/FN values must be lists")
        flattened.extend(float(item) for item in value)
    if not flattened:
        raise ValueError("conditional annual IR/FN values must not be empty")
    return flattened


def _positive_harm_count(verification: Mapping[str, Any]) -> int:
    harm = verification.get("harm_diagnostic")
    if isinstance(harm, Mapping) and isinstance(harm.get("positive_receptor_harm_atom_count"), int):
        return int(harm["positive_receptor_harm_atom_count"])
    # Keep the fallback conservative.  A positive IR/F/N is enough to prove a
    # nonzero receptor contribution, but it is not used to reconstruct atoms.
    return int(any(value > 0.0 for value in _ir_values(verification)))


def build_receptor_geometry_interpretation(
    full_scope_assessment: Mapping[str, Any],
    near_receptor_verification: Mapping[str, Any],
    full_scope_manifest: Mapping[str, Any],
    near_receptor_manifest: Mapping[str, Any],
    *,
    source_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a fail-closed geometry interpretation for two diagnostic records."""

    full_ids, full_positions = _positions(full_scope_manifest)
    near_ids, near_positions = _positions(near_receptor_manifest)
    full_nearest = _nearest_component(full_scope_manifest, full_positions[0])
    near_nearest = _nearest_component(near_receptor_manifest, near_positions[0])

    reasons: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, interpretation: str) -> None:
        checks.append({"id": check_id, "status": "PASS" if passed else "BLOCKED", "interpretation": interpretation})
        if not passed:
            reasons.append(interpretation)

    full_facility_id = full_scope_assessment.get("facility_id")
    near_facility_id = near_receptor_verification.get("facility_id")
    check(
        "full_scope_manifest_identity",
        full_facility_id == full_scope_manifest.get("facility_id"),
        "full-scope assessment and manifest facility IDs must match",
    )
    check(
        "near_receptor_manifest_identity",
        near_facility_id == near_receptor_manifest.get("facility_id"),
        "near-receptor verification and manifest facility IDs must match",
    )
    full_ir = _ir_values(full_scope_assessment)
    near_ir = _ir_values(near_receptor_verification)
    check(
        "full_scope_declared_receptor_is_zero",
        all(value == 0.0 for value in full_ir),
        "the declared full-scope receptor must have zero conditional IR/F-N in this diagnostic",
    )
    check(
        "near_receptor_diagnostic_is_nonzero",
        any(value > 0.0 for value in near_ir) and _positive_harm_count(near_receptor_verification) > 0,
        "the separate near-receptor diagnostic must retain a positive conditional contribution",
    )
    check(
        "geometry_is_distinct",
        full_positions != near_positions and full_nearest[1] > near_nearest[1],
        "the two diagnostics must use distinct receptor geometry and the near receptor must be closer",
    )
    check(
        "diagnostic_records_are_not_substituted",
        full_facility_id != near_facility_id,
        "near-receptor results must not be substituted into the full-scope facility record",
    )
    check(
        "promotion_remains_closed",
        full_scope_assessment.get("complete_facility_qra_claim") is False
        and full_scope_assessment.get("facility_total_risk_available") is False
        and near_receptor_verification.get("facility_qra_claim") is False
        and near_receptor_verification.get("physical_validation_claim") is False,
        "both records must remain diagnostic-only with facility QRA and physical validation closed",
    )

    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "status": "PASS_DIAGNOSTIC_ONLY" if not reasons else "BLOCKED_METADATA",
        "full_scope": {
            "facility_id": full_facility_id,
            "receptor_ids": full_ids,
            "receptor_positions_enu_m": full_positions,
            "nearest_component_id": full_nearest[0],
            "nearest_component_distance_m": full_nearest[1],
            "conditional_annual_ir_low_high": full_scope_assessment.get(
                "conditional_diagnostic_facility_annual_ir_low_high"
            ),
            "conditional_expected_death_fn_low_high": full_scope_assessment.get(
                "conditional_diagnostic_facility_expected_death_fn_low_high"
            ),
            "event_count": full_scope_assessment.get("conditional_diagnostic_facility_coverage", {}).get("event_count"),
            "case_count": full_scope_assessment.get("conditional_diagnostic_facility_coverage", {}).get("case_count"),
            "risk_atom_count": full_scope_assessment.get("conditional_diagnostic_facility_coverage", {}).get("risk_atom_count"),
        },
        "near_receptor": {
            "facility_id": near_facility_id,
            "receptor_ids": near_ids,
            "receptor_positions_enu_m": near_positions,
            "nearest_component_id": near_nearest[0],
            "nearest_component_distance_m": near_nearest[1],
            "conditional_annual_ir_low_high": near_receptor_verification.get(
                "conditional_diagnostic_facility_annual_ir_low_high"
            ),
            "conditional_expected_death_fn_low_high": near_receptor_verification.get(
                "conditional_diagnostic_facility_expected_death_fn_low_high"
            ),
            "positive_receptor_harm_atom_count": _positive_harm_count(near_receptor_verification),
            "event_count": near_receptor_verification.get("frequency_event_count"),
            "case_count": near_receptor_verification.get("campaign_case_count"),
            "risk_atom_count": near_receptor_verification.get("risk_atom_count"),
        },
        "checks": checks,
        "promotion_boundary": {
            "facility_total_risk_claim": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "near_receptor_is_chain_connectivity_diagnostic_only": True,
            "interpretation": (
                "A zero result at the declared full-scope receptor is a geometry-specific conditional result. "
                "The separate near-receptor diagnostic demonstrates that the release-to-harm chain can reach a "
                "receptor, but its result is not a full-scope facility total and is not substituted into the union."
            ),
        },
        "source_paths": dict(source_paths or {}),
        "blocking_reasons": reasons,
    }
    return result


def build_receptor_geometry_interpretation_from_paths(
    full_scope_assessment_path: Path,
    near_receptor_verification_path: Path,
    full_scope_manifest_path: Path,
    near_receptor_manifest_path: Path,
) -> dict[str, Any]:
    """Load four JSON records and retain their hashes for audit reproducibility."""

    paths = {
        "full_scope_assessment": str(full_scope_assessment_path),
        "near_receptor_verification": str(near_receptor_verification_path),
        "full_scope_manifest": str(full_scope_manifest_path),
        "near_receptor_manifest": str(near_receptor_manifest_path),
    }
    result = build_receptor_geometry_interpretation(
        _read_object(full_scope_assessment_path),
        _read_object(near_receptor_verification_path),
        _read_object(full_scope_manifest_path),
        _read_object(near_receptor_manifest_path),
        source_paths=paths,
    )
    result["source_sha256"] = {name: _digest(Path(path)) for name, path in paths.items()}
    return result
