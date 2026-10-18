"""Check the numeric mass handoff from an equipment state to a release packet.

The identity audit proves that a state snapshot and a provider packet refer to
the same event.  This companion diagnostic checks the small, important numeric
boundary that identity alone cannot prove: the snapshot inventory must agree
with the provider mass-balance initial inventory.  It is deliberately
diagnostic-only and never qualifies a provider packet or a facility QRA.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


AUDIT_SCHEMA = "prism.state_release_mass_consistency_audit.v1"

# These are intentionally explicit contract fields.  The audit must not infer
# that two masses share an inventory basis merely because their component IDs
# happen to match: a provider may report an upstream reserve while the state
# snapshot reports the local vessel inventory.
_MASS_BASIS_KEYS = (
    "mass_basis_id",
    "inventory_owner_id",
    "inventory_scope",
    "mass_scope",
    "provider_mass_basis_id",
    "provider_inventory_owner_id",
)


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _case_label(case: Mapping[str, Any]) -> str:
    event_id = case.get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    case_id = case.get("case_id")
    if isinstance(case_id, str) and case_id:
        return case_id
    return "<unidentified-case>"


def _explicit_mass_basis(*mappings: Mapping[str, Any] | None) -> str | None:
    """Return a declared mass-basis token, without guessing one."""
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        for key in _MASS_BASIS_KEYS:
            value = mapping.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                token = str(value).strip()
                if token:
                    return token
    return None


def build_state_release_mass_consistency_audit(
    campaign_result: Mapping[str, Any],
    *,
    relative_tolerance: float = 1e-6,
    absolute_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Return a fail-closed numeric state-to-release consistency ledger.

    A case is comparable only when both the provider state snapshot's
    ``mass_kg`` and the first provider mass balance's ``initial_mass_kg`` are
    present, finite, and non-negative.  Missing fields are reported separately
    from matches; they are never treated as agreement.
    """
    if not _finite_nonnegative(relative_tolerance) or float(relative_tolerance) < 0.0:
        raise ValueError("relative_tolerance must be finite and non-negative")
    if not _finite_nonnegative(absolute_tolerance) or float(absolute_tolerance) < 0.0:
        raise ValueError("absolute_tolerance must be finite and non-negative")
    cases = campaign_result.get("cases")
    if not isinstance(cases, list):
        raise ValueError("campaign_result.cases must be a list")

    mismatch_rows: list[dict[str, Any]] = []
    mismatch_classification_counts: dict[str, int] = {}
    not_comparable_case_ids: list[str] = []
    comparable = matched = 0
    for raw_case in cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("campaign_result.cases must contain objects")
        label = _case_label(raw_case)
        packet = raw_case.get("provider_packet_identity")
        packet = packet if isinstance(packet, Mapping) else {}
        snapshot = packet.get("state_snapshot")
        snapshot = snapshot if isinstance(snapshot, Mapping) else {}
        balances = packet.get("provider_mass_balances")
        balance = balances[0] if isinstance(balances, list) and balances and isinstance(balances[0], Mapping) else None
        state_mass = snapshot.get("mass_kg")
        initial_mass = balance.get("initial_mass_kg") if balance is not None else None
        if not (_finite_nonnegative(state_mass) and _finite_nonnegative(initial_mass)):
            not_comparable_case_ids.append(label)
            continue
        state_value = float(state_mass)
        initial_value = float(initial_mass)
        comparable += 1
        if math.isclose(state_value, initial_value, rel_tol=float(relative_tolerance), abs_tol=float(absolute_tolerance)):
            matched += 1
            continue
        state_basis = _explicit_mass_basis(snapshot)
        provider_basis = _explicit_mass_basis(balance, packet)
        if state_basis is None and provider_basis is None:
            classification = "MASS_BASIS_UNDECLARED_REVIEW_REQUIRED"
            classification_reason = (
                "state and provider masses differ, but neither side declares a comparable "
                "inventory basis"
            )
        elif state_basis is not None and provider_basis is not None and state_basis != provider_basis:
            classification = "MASS_BASIS_ID_MISMATCH_REVIEW_REQUIRED"
            classification_reason = "state and provider declare different inventory-basis tokens"
        else:
            classification = "MASS_VALUE_MISMATCH_REVIEW_REQUIRED"
            classification_reason = "both masses declare a comparable basis, but their values differ"
        mismatch_classification_counts[classification] = mismatch_classification_counts.get(classification, 0) + 1
        mismatch_rows.append({
            "case_id": label,
            "event_id": raw_case.get("event_id"),
            "asset_id": raw_case.get("asset_id"),
            "state_snapshot_component_id": snapshot.get("component_id"),
            "state_mass_kg": state_value,
            "provider_initial_mass_kg": initial_value,
            "absolute_difference_kg": abs(state_value - initial_value),
            "relative_difference": abs(state_value - initial_value) / max(abs(initial_value), 1e-300),
            "classification": classification,
            "classification_reason": classification_reason,
            "state_mass_basis": state_basis,
            "provider_mass_basis": provider_basis,
        })

    mismatch_count = len(mismatch_rows)
    status = (
        "MASS_STATE_CONSISTENCY_PASS"
        if mismatch_count == 0 and not not_comparable_case_ids
        else "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED"
    )
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "case_count": len(cases),
        "comparable_case_count": comparable,
        "matched_case_count": matched,
        "mismatch_case_count": mismatch_count,
        "mismatch_classification_counts": mismatch_classification_counts,
        "mass_basis_review_required_case_count": sum(
            count for classification, count in mismatch_classification_counts.items()
            if classification in {
                "MASS_BASIS_UNDECLARED_REVIEW_REQUIRED",
                "MASS_BASIS_ID_MISMATCH_REVIEW_REQUIRED",
            }
        ),
        "not_comparable_case_count": len(not_comparable_case_ids),
        "relative_tolerance": float(relative_tolerance),
        "absolute_tolerance_kg": float(absolute_tolerance),
        "mismatch_rows": mismatch_rows,
        "not_comparable_case_ids": not_comparable_case_ids,
        "diagnostic_only": True,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "promotion_allowed": False,
        "interpretation": (
            "This is a numeric boundary diagnostic. A mismatch or missing field is retained as an "
            "open model-input issue. Mass-basis classifications use only explicit contract fields; "
            "no inventory owner or scope is inferred from component IDs. No mass is corrected, and no provider packet, frequency, "
            "physical-validation, or facility-QRA claim is promoted."
        ),
    }


__all__ = ["AUDIT_SCHEMA", "build_state_release_mass_consistency_audit"]
