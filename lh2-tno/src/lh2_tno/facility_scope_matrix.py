"""Repair and rebuild accident-family metadata at facility-aggregation scope.

Facility ledgers can outlive the campaign code that created them.  In that
case, event and case IDs may already be correctly namespaced while older case
rows do not carry the scenario-family metadata added later.  This module
provides an explicit, auditable repair path:

* preserve any family already written by the campaign;
* derive only the base family that is unambiguously encoded by event profile
  and release mode;
* accept provider-specific families only through an exact event-ID override;
* rebuild the scope matrix from the repaired ledger, so IDs and case counts
  cannot drift through a second, stale campaign snapshot.

The functions change accounting metadata only.  They never change frequency,
harm, risk atoms, or facility-QRA qualification.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .accident_scenario_catalog import (
    accident_scenario_catalog,
    scenario_families_for_release,
)
from .contracts import canonical_digest


# ``scenario_families_for_release`` takes a manifest component kind, while a
# stored event usually carries the frequency-plan profile.  Keep this mapping
# explicit and small; unknown profiles must remain visible as unclassified.
PROFILE_COMPONENT_KINDS: dict[str, str] = {
    "LH2_VESSEL": "storage_tank",
    "LH2_PIPE": "pipe",
    "TNO_PIPE": "pipe",
    "LH2_VALVE": "valve",
    "TNO_RELIEF_DEVICE": "vent_stack",
    "TNO_PUMP_STANDARD": "pump",
    "TNO_HX_OUTSIDE_TUBES": "vaporizer",
    "TNO_HX_INSIDE_WEAK_SHELL": "reliquefier",
}


def _families(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(str(item) for item in value if str(item).strip()))


def _event_release_families(event: Mapping[str, Any]) -> tuple[str, ...]:
    release = event.get("release")
    mode = release.get("mode") if isinstance(release, Mapping) else None
    profile = event.get("profile")
    kind = PROFILE_COMPONENT_KINDS.get(str(profile)) if profile is not None else None
    if not isinstance(mode, str) or kind is None:
        return ()
    return scenario_families_for_release(kind, mode)


def _append_unique(left: Sequence[str], right: Sequence[str]) -> list[str]:
    return list(dict.fromkeys([str(value) for value in left] + [str(value) for value in right]))


def repair_facility_ledger_scenario_families(
    facility_ledger: Mapping[str, Any],
    *,
    event_family_overrides: Mapping[str, Sequence[str]] = (),
) -> dict[str, Any]:
    """Return a copy of ``facility_ledger`` with explicit family metadata.

    ``event_family_overrides`` is intentionally keyed by exact event ID.  A
    prefix or substring selector would make a namespace rebind impossible to
    audit, so it is rejected by the calling CLI rather than guessed here.
    Existing case and risk-atom families are preserved and unioned with the
    event-level family set.  Missing rows receive only the event's declared
    release-profile families plus the exact override for that event.
    """
    if not isinstance(facility_ledger, Mapping):
        raise ValueError("facility ledger must be an object")
    output = copy.deepcopy(dict(facility_ledger))
    events = output.get("events")
    if not isinstance(events, list) or any(not isinstance(row, dict) for row in events):
        raise ValueError("facility ledger events must be an array of objects")
    event_by_id = {str(row.get("id")): row for row in events if row.get("id")}
    if len(event_by_id) != len(events):
        raise ValueError("facility ledger events must have unique nonempty IDs")

    overrides: dict[str, tuple[str, ...]] = {}
    known_families = {row["family"] for row in accident_scenario_catalog()}
    for event_id, values in dict(event_family_overrides).items():
        if event_id not in event_by_id:
            raise ValueError(f"family override references unknown event: {event_id}")
        if isinstance(values, (str, bytes)):
            raise ValueError(f"family override for {event_id} must be an array")
        parsed = _families(list(values))
        unknown = sorted(set(parsed) - known_families)
        if unknown:
            raise ValueError(
                f"family override for {event_id} has unknown families: {', '.join(unknown)}"
            )
        overrides[event_id] = parsed

    # First collect family metadata that already survived the campaign merge.
    observed_by_event: dict[str, list[str]] = defaultdict(list)
    for key in ("cases", "uncomputed_cases", "risk_atoms"):
        rows = output.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"facility ledger {key} must be an array")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"facility ledger {key} entries must be objects")
            event_id = str(row.get("event_id", ""))
            if event_id in event_by_id:
                observed_by_event[event_id].extend(_families(row.get("scenario_families")))

    repair_rows: list[dict[str, Any]] = []
    for event_id, event in event_by_id.items():
        observed = tuple(dict.fromkeys(observed_by_event.get(event_id, ())))
        derived = _event_release_families(event)
        override = overrides.get(event_id, ())
        # Existing campaign tags take precedence over a later profile mapping;
        # the profile is only a safe fallback for rows that have no tag.
        families = _append_unique(observed or derived, override)
        event["scenario_families"] = families
        repair_rows.append({
            "event_id": event_id,
            "families": families,
            "source": (
                "existing_case_or_atom_metadata"
                if observed
                else "event_profile_release_mode"
                if derived
                else "explicit_event_override"
                if override
                else "unclassified"
            ),
            "existing_families": list(observed),
            "derived_release_families": list(derived),
            "explicit_override_families": list(override),
        })

    for key in ("cases", "uncomputed_cases", "risk_atoms"):
        for row in output.get(key, []):
            event_id = str(row.get("event_id", ""))
            if event_id in event_by_id:
                row["scenario_families"] = _append_unique(
                    event_by_id[event_id].get("scenario_families", ()),
                    _families(row.get("scenario_families")),
                )

    output["scenario_family_metadata"] = {
        "schema_version": "prism.facility_scenario_family_metadata.v1",
        "event_count": len(events),
        "explicit_override_event_count": len(overrides),
        "unclassified_event_ids": [
            row["event_id"] for row in repair_rows if not row["families"]
        ],
        "rows": repair_rows,
        "frequency_changed": False,
        "risk_atoms_changed": False,
        "interpretation": (
            "Metadata repair only: existing tags are preserved, base families use the "
            "stored profile/release mode, and provider-specific families require exact "
            "event-ID overrides. No frequency or harm value is inferred."
        ),
    }
    output["scenario_family_metadata_digest"] = canonical_digest(
        output["scenario_family_metadata"]
    )
    output["risk_atoms_digest"] = canonical_digest(output.get("risk_atoms", []))
    return output


def _status(case_rows: Sequence[Mapping[str, Any]]) -> str:
    if not case_rows:
        return "NO_CASE_EXECUTED"
    statuses = {str(row.get("status", "UNCOMPUTED")) for row in case_rows}
    if statuses == {"EXECUTED"}:
        return "EXECUTED"
    if any(status.startswith("EXECUTED") for status in statuses):
        return "PARTIAL"
    if statuses == {"FAILED"}:
        return "FAILED"
    return "UNCOMPUTED"


def _conditional_status(case_rows: Sequence[Mapping[str, Any]]) -> str:
    if not case_rows:
        return "NO_CASE_EXECUTED"
    executed = sum(str(row.get("status", "")).startswith("EXECUTED") for row in case_rows)
    if executed == len(case_rows):
        return "EXECUTED"
    if executed:
        return "PARTIAL"
    return "UNCOMPUTED"


def build_scope_matrix_from_facility_ledger(
    facility_ledger: Mapping[str, Any],
    *,
    required_families: Sequence[str],
) -> dict[str, Any]:
    """Build a scope matrix whose event and case sets come from one ledger."""
    if not isinstance(facility_ledger, Mapping):
        raise ValueError("facility ledger must be an object")
    families = tuple(dict.fromkeys(str(value) for value in required_families if str(value).strip()))
    if not families:
        raise ValueError("required_families must be nonempty")
    unknown = sorted(set(families) - {row["family"] for row in accident_scenario_catalog()})
    if unknown:
        raise ValueError(f"unknown required accident families: {', '.join(unknown)}")
    events = facility_ledger.get("events")
    cases = facility_ledger.get("cases")
    if not isinstance(events, list) or not isinstance(cases, list):
        raise ValueError("facility ledger must contain events and cases arrays")
    event_families: dict[str, tuple[str, ...]] = {}
    for row in events:
        if not isinstance(row, Mapping) or not row.get("id"):
            raise ValueError("facility ledger contains an invalid event")
        event_families[str(row["id"])] = _families(row.get("scenario_families"))
    case_rows = [row for row in cases if isinstance(row, Mapping)]
    rows: list[dict[str, Any]] = []
    blocking: list[str] = []
    conditional_blocking: list[str] = []
    for family in families:
        event_ids = sorted(
            event_id for event_id, observed in event_families.items() if family in observed
        )
        family_cases = [
            row for row in case_rows if family in _families(row.get("scenario_families"))
        ]
        executed = sum(str(row.get("status", "")).startswith("EXECUTED") for row in family_cases)
        conditional_uncomputed = len(family_cases) - executed
        strict_uncomputed = sum(
            str(row.get("status", ""))
            in {"UNCOMPUTED", "FAILED", "EXECUTED_OPERATOR_LIMITED", "EXECUTED_DOMAIN_INCOMPLETE"}
            for row in family_cases
        )
        fully_validated = sum(str(row.get("status", "")) == "EXECUTED" for row in family_cases)
        operator_limited = sum(
            str(row.get("status", "")) == "EXECUTED_OPERATOR_LIMITED"
            for row in family_cases
        )
        domain_incomplete = sum(
            str(row.get("status", "")) == "EXECUTED_DOMAIN_INCOMPLETE"
            for row in family_cases
        )
        failed = sum(str(row.get("status", "")) == "FAILED" for row in family_cases)
        not_numerically_executed = sum(
            str(row.get("status", "")) in {"UNCOMPUTED", "FAILED"}
            for row in family_cases
        )
        qualified_evidence_withheld = sum(
            str(row.get("status", ""))
            in {"EXECUTED_OPERATOR_LIMITED", "EXECUTED_DOMAIN_INCOMPLETE"}
            for row in family_cases
        )
        status = "NOT_APPLICABLE" if not event_ids else _status(family_cases)
        conditional_status = "NOT_APPLICABLE" if not event_ids else _conditional_status(family_cases)
        if status not in {"EXECUTED", "NOT_APPLICABLE"}:
            blocking.append(f"{family}: {status}")
        if conditional_status not in {"EXECUTED", "NOT_APPLICABLE"}:
            conditional_blocking.append(f"{family}: {conditional_status}")
        frequency = sum(
            float(events[index].get("annual_frequency_per_year", 0.0) or 0.0)
            for index in range(len(events))
            if str(events[index].get("id")) in event_ids
        )
        rows.append({
            "family": family,
            "status": status,
            "conditional_status": conditional_status,
            "event_ids": event_ids,
            "generated_event_count": len(event_ids),
            "case_count": len(family_cases),
            "executed_case_count": executed,
            "conditional_executed_case_count": executed,
            "conditional_uncomputed_case_count": conditional_uncomputed,
            "fully_validated_case_count": fully_validated,
            "operator_limited_case_count": operator_limited,
            "domain_incomplete_case_count": domain_incomplete,
            "failed_case_count": failed,
            "uncomputed_case_count": strict_uncomputed,
            "strict_uncomputed_case_count": strict_uncomputed,
            "not_numerically_executed_case_count": not_numerically_executed,
            "qualified_evidence_withheld_case_count": qualified_evidence_withheld,
            "numerically_executed_case_count": executed,
            "generated_initiation_frequency_per_year": frequency,
            "frequency_rows_are_not_additive_across_families": True,
            "source": "facility_ledger_event_and_case_metadata",
        })

    ledger_conditional_uncomputed = int(
        facility_ledger.get(
            "conditional_uncomputed_case_count",
            sum(not str(row.get("status", "")).startswith("EXECUTED") for row in case_rows),
        )
    )
    matrix_complete = not blocking and ledger_conditional_uncomputed == 0
    return {
        "schema_version": "prism.major_accident_scope.v1",
        "facility_id": facility_ledger.get("facility_id"),
        "scope": "outdoor_major_accidents",
        "required_families": list(families),
        "rows": rows,
        "event_count": len(event_families),
        "case_count": len(case_rows),
        "conditional_executed_case_count": len(case_rows) - ledger_conditional_uncomputed,
        "conditional_uncomputed_case_count": ledger_conditional_uncomputed,
        "not_numerically_executed_case_count": sum(
            str(row.get("status", "")) in {"UNCOMPUTED", "FAILED"}
            for row in case_rows
        ),
        "qualified_evidence_withheld_case_count": sum(
            str(row.get("status", ""))
            in {"EXECUTED_OPERATOR_LIMITED", "EXECUTED_DOMAIN_INCOMPLETE"}
            for row in case_rows
        ),
        "numerically_executed_case_count": sum(
            str(row.get("status", "")).startswith("EXECUTED")
            for row in case_rows
        ),
        "conditional_chain_complete": ledger_conditional_uncomputed == 0,
        "conditional_chain_blocking_reasons": list(dict.fromkeys(conditional_blocking)),
        "facility_total_risk_available": facility_ledger.get("facility_total_risk_available") is True,
        "matrix_complete": matrix_complete,
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "source_facility_ledger_digest": canonical_digest(facility_ledger),
        "source": "facility_ledger_event_and_case_metadata",
        "physical_validation_claim": False,
        "interpretation": (
            "This matrix is regenerated from the exact merged facility ledger. "
            "Overlapping family rows are views of the same cases and must not be summed."
        ),
    }


__all__ = [
    "PROFILE_COMPONENT_KINDS",
    "repair_facility_ledger_scenario_families",
    "build_scope_matrix_from_facility_ledger",
]
