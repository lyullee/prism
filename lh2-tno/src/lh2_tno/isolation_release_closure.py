"""Audit isolation-success/failure release closure for the LH2 chain.

The isolation extension is a useful diagnostic branch, but it is not a
qualified plant barrier model.  This module checks the branch-owned
termination basis, mass residual, and state-snapshot identity without
assigning a barrier probability or promoting facility QRA.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any


SCHEMA = "prism.isolation_release_closure_audit.v1"
_RESIDUAL_TOLERANCE_KG = 1.0e-8


def _read(value: Mapping[str, Any] | str | Path, label: str) -> Mapping[str, Any]:
    if isinstance(value, (str, Path)):
        try:
            value = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read {label}") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def audit_isolation_release_closure(
    campaign_result: Mapping[str, Any] | str | Path,
    *,
    verification: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Return a fail-closed case-level isolation termination audit."""

    campaign = _read(campaign_result, "campaign_result")
    raw_cases = campaign.get("cases")
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, (str, bytes)):
        raise ValueError("campaign_result.cases must be an array")
    rows: list[dict[str, Any]] = []
    blocking: list[str] = []
    basis_counts: Counter[str] = Counter()
    branch_counts: Counter[str] = Counter()
    max_residual = 0.0
    state_snapshot_count = 0
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, Mapping):
            raise ValueError(f"campaign_result.cases[{index}] must be an object")
        branch = str(raw.get("release_branch_id", ""))
        if branch not in {"provider-isolation-success", "provider-isolation-failure"}:
            blocking.append(f"case[{index}] has unsupported isolation branch: {branch}")
        branch_counts[branch] += 1
        termination = raw.get("termination")
        termination = termination if isinstance(termination, Mapping) else {}
        basis = termination.get("basis")
        basis_text = str(basis) if basis is not None else "missing"
        basis_counts[basis_text] += 1
        expected_basis = (
            "reviewed_isolation_success"
            if branch == "provider-isolation-success"
            else "synthetic_diagnostic_horizon"
        )
        basis_matches = basis_text == expected_basis
        if not basis_matches:
            blocking.append(
                f"{raw.get('event_id', index)}: branch {branch} has termination basis {basis_text}; "
                f"expected {expected_basis}"
            )
        ledger = raw.get("mass_ledger")
        ledger = ledger if isinstance(ledger, Mapping) else {}
        residual = ledger.get("end_to_end_residual_kg")
        try:
            residual_value = abs(float(residual))
        except (TypeError, ValueError):
            residual_value = float("inf")
        max_residual = max(max_residual, residual_value)
        mass_closed = residual_value <= _RESIDUAL_TOLERANCE_KG
        if not mass_closed:
            blocking.append(f"{raw.get('event_id', index)}: mass residual exceeds tolerance")
        identity = raw.get("provider_packet_identity")
        identity = identity if isinstance(identity, Mapping) else {}
        snapshot_bound = isinstance(identity.get("state_snapshot"), Mapping) and bool(
            identity.get("state_snapshot_digest")
        )
        state_snapshot_count += int(snapshot_bound)
        qualification = identity.get("qualified_provider_packet") is True
        if qualification:
            # Diagnostic isolation identities are intentionally never accepted
            # as qualification evidence by this audit.
            blocking.append(f"{raw.get('event_id', index)}: diagnostic identity claimed qualification")
        rows.append(
            {
                "case_index": index,
                "event_id": raw.get("event_id"),
                "release_branch_id": branch,
                "status": raw.get("status"),
                "termination_basis": basis_text,
                "termination_time_s": termination.get("time_s"),
                "termination_basis_matches_branch": basis_matches,
                "mass_residual_kg": residual_value if residual is not None else None,
                "mass_closure_status": "CLOSED" if mass_closed else "OPEN",
                "state_snapshot_bound": snapshot_bound,
                "provider_result_digest_count": len(
                    identity.get("provider_result_digests", [])
                    if isinstance(identity.get("provider_result_digests"), list)
                    else []
                ),
                "qualified_provider_packet": False,
                "diagnostic_only": True,
            }
        )
    if verification is not None:
        verification_value = _read(verification, "verification")
        if verification_value.get("status") not in {
            "ISOLATION_UNION_EXTENSION_DIAGNOSTIC",
            "ISOLATION_RESPONSE_CHAIN_DIAGNOSTIC",
        }:
            blocking.append("verification status is not an isolation diagnostic status")
    success_count = branch_counts.get("provider-isolation-success", 0)
    failure_count = branch_counts.get("provider-isolation-failure", 0)
    if failure_count:
        blocking.append(
            f"{failure_count} isolation-failure case(s) remain synthetic diagnostic horizons"
        )
    blocking.append("isolation branch probability is not promoted to plant reliability")
    blocking.append("qualified provider sidecars and independent physical validation remain open")
    return {
        "schema_version": SCHEMA,
        "status": "ISOLATION_RELEASE_CLOSURE_DIAGNOSTIC",
        "facility_id": campaign.get("facility_id"),
        "campaign_result": str(campaign_result) if isinstance(campaign_result, (str, Path)) else "inline",
        "case_count": len(rows),
        "branch_counts": dict(sorted(branch_counts.items())),
        "success_case_count": success_count,
        "failure_case_count": failure_count,
        "termination_basis_counts": dict(sorted(basis_counts.items())),
        "state_snapshot_bound_case_count": state_snapshot_count,
        "mass_residual_tolerance_kg": _RESIDUAL_TOLERANCE_KG,
        "maximum_mass_residual_kg": max_residual,
        "mass_closed_case_count": sum(row["mass_closure_status"] == "CLOSED" for row in rows),
        "qualified_provider_packet_case_count": 0,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "barrier_probability_promoted": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "promotion": {
            "release_boundary": False,
            "provider_packet": False,
            "barrier_reliability": False,
            "frequency": False,
            "physical_validation": False,
            "facility_qra": False,
        },
        "interpretation": (
            "Isolation-success rows have an explicit diagnostic termination basis and closed mass ledger; "
            "isolation-failure rows remain horizon-bounded. No branch probability, provider qualification, "
            "or facility QRA is inferred."
        ),
    }


__all__ = ["SCHEMA", "audit_isolation_release_closure"]
