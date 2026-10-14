"""Audit the executed release-to-final-damage chain at case and atom level.

The facility ledger already checks frequency, receptor-harm and expected-death
closure.  This module adds the missing structural question: for every executed
case, did the saved release boundary, mass ledger, consequence stages and all
ignition risk atoms remain connected?  It is deliberately diagnostic.  A
closed chain does not qualify a provider packet, physical validation, or a
facility IR/F-N result.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


RISK_ATOM_CHAIN_AUDIT_SCHEMA = "prism.risk_atom_chain_audit.v1"
IGNITION_BRANCHES = frozenset(
    {"direct_fire", "delayed_flash_fire", "delayed_explosion", "no_ignition"}
)
REQUIRED_STAGE_NAMES = (
    "source",
    "pool",
    "near_field_and_dispersion",
    "cloud_observation",
    "fire_explosion_damage_risk",
)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _finite_nonnegative(value: Any) -> bool:
    return _finite(value) and float(value) >= 0.0


def _case_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("event_id", "")),
        str(row.get("annual_condition_id", "")),
        str(row.get("release_branch_id", "")),
    )


def _atom_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    event_id, condition_id, branch_id = _case_key(row)
    return event_id, condition_id, branch_id, str(row.get("ignition_branch", ""))


def _row_identity(row: Mapping[str, Any]) -> str:
    key = _case_key(row)
    return "/".join(key)


def build_risk_atom_chain_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a fail-closed case/atom chain audit for one facility result.

    ``EXECUTED_OPERATOR_LIMITED`` is accepted as a numerically executed case,
    but is counted separately.  The audit therefore answers whether the
    numerical chain is connected without confusing that answer with provider
    qualification.
    """
    if not isinstance(result, Mapping):
        raise TypeError("facility result must be a mapping")
    raw_cases = result.get("cases", ())
    raw_atoms = result.get("risk_atoms", ())
    cases = tuple(row for row in raw_cases if isinstance(row, Mapping)) if isinstance(raw_cases, Sequence) and not isinstance(raw_cases, (str, bytes)) else ()
    atoms = tuple(row for row in raw_atoms if isinstance(row, Mapping)) if isinstance(raw_atoms, Sequence) and not isinstance(raw_atoms, (str, bytes)) else ()

    blockers: list[str] = []
    case_keys: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    duplicate_case_keys: list[str] = []
    for case in cases:
        key = _case_key(case)
        label = _row_identity(case)
        if not all(key):
            blockers.append(f"case {label}: event, condition and release branch identity are required")
        if key in case_keys:
            duplicate_case_keys.append(label)
        case_keys[key] = case
    if duplicate_case_keys:
        blockers.append("duplicate case identities: " + ", ".join(sorted(set(duplicate_case_keys))))

    atoms_by_case: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    duplicate_atom_keys: list[str] = []
    for atom in atoms:
        key = _atom_key(atom)
        label = "/".join(key)
        if not all(key):
            blockers.append(f"atom {label}: event, condition, release branch and ignition identity are required")
        if key in {( _atom_key(existing) ) for rows in atoms_by_case.values() for existing in rows}:
            duplicate_atom_keys.append(label)
        atoms_by_case[key[:3]].append(atom)
    if duplicate_atom_keys:
        blockers.append("duplicate atom identities: " + ", ".join(sorted(set(duplicate_atom_keys))))

    missing_atom_case_ids: list[str] = []
    extra_atom_case_ids: list[str] = []
    incomplete_case_ids: list[str] = []
    complete_case_ids: list[str] = []
    stage_counts: Counter[str] = Counter()
    operator_limited_case_count = 0
    zero_harm_atom_count = 0
    positive_harm_atom_count = 0
    empty_harm_atom_count = 0
    zero_expected_death_atom_count = 0
    positive_expected_death_atom_count = 0

    for key, case in case_keys.items():
        label = _row_identity(case)
        status = str(case.get("status", ""))
        if status == "EXECUTED_OPERATOR_LIMITED":
            operator_limited_case_count += 1
        case_errors: list[str] = []
        if not status.startswith("EXECUTED"):
            case_errors.append(f"status {status or 'missing'} is not numerically executed")

        termination = case.get("termination")
        if not isinstance(termination, Mapping) or not isinstance(termination.get("basis"), str) or not _finite_nonnegative(termination.get("time_s")) or float(termination.get("time_s", 0.0)) <= 0.0:
            case_errors.append("release termination basis/time is missing or invalid")

        mass = case.get("mass_ledger")
        # Numerical conservation can leave a tiny signed residual (for
        # example -5e-11 kg).  The released mass must be non-negative, while
        # the residual only needs to be finite; the strict release-boundary
        # gate separately decides whether that residual is closed.
        if not isinstance(mass, Mapping) or not _finite_nonnegative(mass.get("released_kg")) or not _finite(mass.get("end_to_end_residual_kg")):
            case_errors.append("release mass ledger is missing or invalid")

        stages = case.get("stage_elapsed_ms")
        if not isinstance(stages, Mapping):
            case_errors.append("stage timing is missing")
        else:
            generic_stages_valid = True
            for stage in REQUIRED_STAGE_NAMES:
                elapsed = stages.get(stage)
                if not _finite_nonnegative(elapsed):
                    generic_stages_valid = False
                    break
            paired_endpoint_stages_valid = all(
                _finite_nonnegative(stages.get(stage))
                for stage in ("endpoint_a", "endpoint_b", "endpoint_aggregation")
            )
            if generic_stages_valid:
                for stage in REQUIRED_STAGE_NAMES:
                    stage_counts[stage] += 1
            elif paired_endpoint_stages_valid:
                # Two-sided releases use endpoint_a/endpoint_b and an
                # explicit aggregation stage.  This is the same conceptual
                # release-to-damage chain, while the joint-plume physics
                # remains outside this structural audit.
                for stage in REQUIRED_STAGE_NAMES:
                    stage_counts[stage] += 1
            else:
                for stage in REQUIRED_STAGE_NAMES:
                    if not _finite_nonnegative(stages.get(stage)):
                        case_errors.append(f"stage {stage} is missing or invalid")

        domain = case.get("domain_assessment")
        if not isinstance(domain, Mapping):
            case_errors.append("domain assessment is missing")

        identity = case.get("provider_packet_identity")
        if not isinstance(identity, Mapping):
            case_errors.append("provider packet/state identity is missing")

        case_atoms = atoms_by_case.get(key, [])
        branches = [str(atom.get("ignition_branch", "")) for atom in case_atoms]
        if set(branches) != set(IGNITION_BRANCHES) or len(branches) != len(IGNITION_BRANCHES):
            case_errors.append("the four ignition branches do not map exactly to this case")
        for atom in case_atoms:
            harm = atom.get("receptor_harm_low_high")
            deaths = atom.get("expected_deaths_low_high")
            if not isinstance(harm, Mapping) or not harm:
                empty_harm_atom_count += 1
                case_errors.append("risk atom receptor harm mapping is empty")
            else:
                atom_positive = False
                for receptor_id, endpoints in harm.items():
                    if (
                        not isinstance(endpoints, Sequence)
                        or isinstance(endpoints, (str, bytes))
                        or len(endpoints) != 2
                        or any(not _finite_nonnegative(value) for value in endpoints)
                    ):
                        case_errors.append(f"risk atom receptor harm endpoints are invalid for {receptor_id}")
                        break
                    atom_positive = atom_positive or any(float(value) > 0.0 for value in endpoints)
                if atom_positive:
                    positive_harm_atom_count += 1
                else:
                    zero_harm_atom_count += 1
            if not isinstance(deaths, Sequence) or isinstance(deaths, (str, bytes)) or len(deaths) != 2:
                case_errors.append("risk atom lacks receptor harm and two expected-death endpoints")
                break
            if any(not _finite_nonnegative(value) for value in deaths):
                case_errors.append("risk atom expected-death endpoint is invalid")
                break
            if any(float(value) > 0.0 for value in deaths):
                positive_expected_death_atom_count += 1
            else:
                zero_expected_death_atom_count += 1

        if case_errors:
            incomplete_case_ids.append(label)
            blockers.extend(f"{label}: {error}" for error in case_errors)
        else:
            complete_case_ids.append(label)

    for key in sorted(set(atoms_by_case) - set(case_keys)):
        extra_atom_case_ids.append("/".join(key))
    for key in sorted(set(case_keys) - set(atoms_by_case)):
        missing_atom_case_ids.append("/".join(key))
    if missing_atom_case_ids:
        blockers.append("cases without risk atoms: " + ", ".join(missing_atom_case_ids))
    if extra_atom_case_ids:
        blockers.append("risk atoms without cases: " + ", ".join(extra_atom_case_ids))

    blockers = list(dict.fromkeys(blockers))
    complete = bool(cases) and bool(atoms) and not blockers
    return {
        "schema_version": RISK_ATOM_CHAIN_AUDIT_SCHEMA,
        "status": "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC" if complete else "PARTIAL_RISK_ATOM_CHAIN",
        "facility_id": result.get("facility_id"),
        "case_count": len(cases),
        "risk_atom_count": len(atoms),
        "complete_case_count": len(complete_case_ids),
        "incomplete_case_count": len(incomplete_case_ids),
        "complete_case_ids": sorted(complete_case_ids),
        "incomplete_case_ids": sorted(incomplete_case_ids),
        "missing_atom_case_ids": sorted(missing_atom_case_ids),
        "extra_atom_case_ids": sorted(extra_atom_case_ids),
        "duplicate_case_count": len(duplicate_case_keys),
        "duplicate_atom_count": len(duplicate_atom_keys),
        "required_stage_names": list(REQUIRED_STAGE_NAMES),
        "stage_complete_case_counts": {
            stage: stage_counts.get(stage, 0) for stage in REQUIRED_STAGE_NAMES
        },
        "operator_limited_case_count": operator_limited_case_count,
        "zero_harm_atom_count": zero_harm_atom_count,
        "positive_harm_atom_count": positive_harm_atom_count,
        "empty_harm_atom_count": empty_harm_atom_count,
        "zero_expected_death_atom_count": zero_expected_death_atom_count,
        "positive_expected_death_atom_count": positive_expected_death_atom_count,
        "blocking_reasons": blockers,
        "diagnostic_only": True,
        "provider_packet_promoted": False,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_ir_fn_promotion": False,
        "facility_qra_claim": False,
        "interpretation": (
            "Every numerical case must retain its release termination, mass closure, consequence-stage timing, "
            "domain record and four ignition-specific risk atoms. Harm and expected-death endpoints are counted "
            "separately so a computed zero is distinguishable from an empty or invalid consequence. Operator-limited "
            "cases can close this structural chain, but remain non-qualified evidence."
        ),
    }


__all__ = ["RISK_ATOM_CHAIN_AUDIT_SCHEMA", "REQUIRED_STAGE_NAMES", "build_risk_atom_chain_audit"]
