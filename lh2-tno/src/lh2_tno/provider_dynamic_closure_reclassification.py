"""Compare a facility ledger with a newer provider campaign's closure evidence.

The comparison is deliberately advisory.  A newer provider packet can prove
that a source used dynamic pressure/inventory feedback, but that fact alone
does not qualify the packet for facility QRA.  This module therefore reports
case-level candidates and keeps promotion disabled until the normal provider
qualification, physical-validation, and release-boundary gates pass.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "prism.dynamic_state_closure_reclassification_audit.v1"


def _case_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("event_id", "")),
        str(row.get("annual_condition_id", "")),
        str(row.get("operating_mode", "")),
    )


def _rows(value: Mapping[str, Any], key: str = "cases") -> list[Mapping[str, Any]]:
    raw = value.get(key, [])
    return [row for row in raw if isinstance(row, Mapping)]


def _closure_reasons(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("dynamic_state_closure_blocking_reasons", [])
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def build_dynamic_closure_reclassification_audit(
    current_result: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
    *,
    current_record: str | None = None,
    candidate_record: str | None = None,
) -> dict[str, Any]:
    """Build a fail-closed comparison between two campaign result ledgers.

    Matching uses event, annual-condition, and operating-mode identity.  A
    candidate is *eligible* only when its row is numerically executed and its
    provider-owned dynamic closure is explicitly READY.  No row is promoted
    in either input ledger; ``promotion_allowed`` is always false here.
    """

    current = {_case_key(row): row for row in _rows(current_result)}
    candidate = {_case_key(row): row for row in _rows(candidate_result)}
    rows: list[dict[str, Any]] = []
    for key in sorted(set(current) | set(candidate)):
        old = current.get(key)
        new = candidate.get(key)
        candidate_ready = new is not None and new.get("dynamic_state_closure_ready") is True
        candidate_executed = new is not None and new.get("status") == "EXECUTED"
        eligible = bool(candidate_ready and candidate_executed)
        old_status = old.get("status") if old is not None else "MISSING"
        new_status = new.get("status") if new is not None else "MISSING"
        rows.append(
            {
                "event_id": key[0],
                "annual_condition_id": key[1],
                "operating_mode": key[2],
                "current_status": old_status,
                "candidate_status": new_status,
                "current_dynamic_state_closure_status": (
                    old.get("dynamic_state_closure_status") if old is not None else None
                ),
                "candidate_dynamic_state_closure_status": (
                    new.get("dynamic_state_closure_status") if new is not None else None
                ),
                "candidate_dynamic_state_closure_ready": (
                    new.get("dynamic_state_closure_ready") if new is not None else None
                ),
                "candidate_blocking_reasons": _closure_reasons(new or {}),
                "candidate_eligible_for_reclassification": eligible,
                "reclassification_applied": False,
                "promotion_allowed": False,
                "reason": (
                    "candidate has explicit READY dynamic closure and numerical execution; "
                    "provider qualification and facility gates remain open"
                    if eligible
                    else "candidate is missing a READY dynamic closure or numerical execution"
                ),
            }
        )

    status_counts = Counter(row["current_status"] for row in rows)
    candidate_status_counts = Counter(row["candidate_status"] for row in rows)
    eligible_count = sum(
        row["candidate_eligible_for_reclassification"] for row in rows
    )
    new_reclassification_count = sum(
        row["candidate_eligible_for_reclassification"]
        and row["current_status"] == "EXECUTED_OPERATOR_LIMITED"
        for row in rows
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ADVISORY_RECLASSIFICATION_CANDIDATES",
        "promotion_allowed": False,
        "reclassification_applied": False,
        "current_record": current_record,
        "candidate_record": candidate_record,
        "current_case_count": len(current),
        "candidate_case_count": len(candidate),
        "matched_case_count": sum(key in candidate for key in current),
        "unmatched_current_case_count": sum(key not in candidate for key in current),
        "unmatched_candidate_case_count": sum(key not in current for key in candidate),
        "candidate_eligible_case_count": eligible_count,
        "new_reclassification_candidate_count": new_reclassification_count,
        "current_status_counts": dict(sorted(status_counts.items())),
        "candidate_status_counts": dict(sorted(candidate_status_counts.items())),
        "rows": rows,
        "interpretation": (
            "This record identifies newer provider rows whose dynamic state closure is "
            "explicitly ready. It does not rewrite the authoritative facility ledger, "
            "infer missing termination evidence, or permit facility IR/F-N promotion."
        ),
    }


__all__ = ["SCHEMA_VERSION", "build_dynamic_closure_reclassification_audit"]
