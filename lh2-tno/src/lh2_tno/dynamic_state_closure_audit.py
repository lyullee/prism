"""Audit dynamic-state closure counts across PRISM ledgers.

The campaign and facility ledgers retain the provider's explicit dynamic
state closure status.  This module recomputes those counts from the raw case
rows and compares them with every stored coverage view.  A stale published
test-count or evidence snapshot therefore cannot hide a ledger mismatch.  It
is an accounting diagnostic only: it never infers closure from a scalar mass
balance and never promotes a facility QRA claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


DYNAMIC_STATE_CLOSURE_LEDGER_AUDIT_SCHEMA = (
    "prism.dynamic_state_closure_ledger_audit.v1"
)


class DynamicStateClosureLedgerAuditError(ValueError):
    """Raised when a ledger cannot be audited without inference."""


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise DynamicStateClosureLedgerAuditError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise DynamicStateClosureLedgerAuditError(
                f"{label}[{index}] must be an object"
            )
        rows.append(row)
    return rows


def _case_identity(row: Mapping[str, Any]) -> tuple[str, ...]:
    event_id = str(row.get("event_id", ""))
    dimensions = (
        row.get("annual_condition_id"),
        row.get("release_branch_id"),
        row.get("ignition_branch"),
    )
    if any(value is not None and str(value) for value in dimensions):
        return (event_id, *(str(value or "") for value in dimensions))
    return (event_id,)


def _status(row: Mapping[str, Any], *, missing: bool) -> str:
    value = row.get("dynamic_state_closure_status")
    if isinstance(value, str) and value.strip():
        return value
    return "NOT_EVALUATED" if missing else "NOT_DECLARED"


def _counts(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _compare_counts(
    checks: list[dict[str, Any]],
    label: str,
    expected: Mapping[str, int],
    stored: Any,
) -> None:
    normalized = (
        {str(key): int(value) for key, value in stored.items()}
        if isinstance(stored, Mapping)
        and all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in stored.values()
        )
        else None
    )
    ok = normalized == dict(expected)
    checks.append(
        {
            "name": label,
            "status": "PASS" if ok else "BLOCKED",
            "expected": dict(expected),
            "stored": normalized if normalized is not None else stored,
            "reason": None if ok else f"{label} differs from recomputed case identities",
        }
    )


def _campaign_component_expected(
    result: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, int]]:
    events = _rows(result.get("events", []), "campaign.events")
    event_component = {
        str(event.get("id")): str(event.get("model_component_id"))
        for event in events
        if event.get("id") is not None and event.get("model_component_id") is not None
    }
    values: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        values[event_component.get(str(case.get("event_id", "")), "UNMAPPED_COMPONENT")].append(
            _status(case, missing=False)
        )
    return {component: _counts(statuses) for component, statuses in sorted(values.items())}


def _facility_case_statuses(
    result: Mapping[str, Any],
) -> tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str]]:
    cases = _rows(result.get("cases", []), "facility.cases")
    missing = _rows(result.get("uncomputed_cases", []), "facility.uncomputed_cases")
    global_status: dict[tuple[str, ...], str] = {}
    component_status: dict[tuple[str, ...], str] = {}
    for case in cases:
        identity = _case_identity(case)
        global_status[identity] = _status(case, missing=False)
        component_status[identity] = _component_id(case, result)
    for case in missing:
        identity = _case_identity(case)
        if identity not in global_status:
            global_status[identity] = _status(case, missing=True)
            component_status[identity] = _component_id(case, result)
    return global_status, component_status


def _component_id(row: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    provider = row.get("provider_packet_identity")
    if isinstance(provider, Mapping) and provider.get("component_id"):
        return str(provider["component_id"])
    for key in ("component_id", "model_component_id"):
        if row.get(key):
            return str(row[key])
    event_id = str(row.get("event_id", ""))
    events = result.get("events", [])
    if isinstance(events, list):
        for event in events:
            if isinstance(event, Mapping) and str(event.get("id", "")) == event_id:
                if event.get("model_component_id"):
                    return str(event["model_component_id"])
    return "UNMAPPED_COMPONENT"


def _component_status_counts(
    result: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        grouped[_component_id(case, result)].append(_status(case, missing=False))
    return {
        component: _counts(statuses)
        for component, statuses in sorted(grouped.items())
    }


def annotate_missing_dynamic_state_closure_fields(
    ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Annotate an old saved ledger without inferring provider closure.

    Older result snapshots predate the dynamic-state fields.  This migration
    writes ``NOT_DECLARED`` for evaluated rows and ``NOT_EVALUATED`` for
    withheld rows, then rebuilds only the corresponding count views.  It does
    not inspect scalar mass balances, pressure values, or provider history to
    create a READY status.
    """
    if not isinstance(ledger, Mapping):
        raise DynamicStateClosureLedgerAuditError("ledger must be an object")
    output: dict[str, Any] = deepcopy(dict(ledger))
    target = output.get("facility_risk_ledger")
    if not isinstance(target, Mapping):
        target = output
    else:
        target = deepcopy(dict(target))
        output["facility_risk_ledger"] = target

    cases = [dict(row) for row in _rows(target.get("cases", []), "ledger.cases")]
    uncomputed = [
        dict(row)
        for row in _rows(target.get("uncomputed_cases", []), "ledger.uncomputed_cases")
    ]
    annotated_case_count = 0
    annotated_uncomputed_count = 0
    for row in cases:
        if not isinstance(row.get("dynamic_state_closure_status"), str) or not row.get(
            "dynamic_state_closure_status"
        ):
            row["dynamic_state_closure_status"] = "NOT_DECLARED"
            annotated_case_count += 1
        row.setdefault("dynamic_state_closure_ready", None)
        row.setdefault("dynamic_state_closure_blocking_reasons", [])
    for row in uncomputed:
        if not isinstance(row.get("dynamic_state_closure_status"), str) or not row.get(
            "dynamic_state_closure_status"
        ):
            row["dynamic_state_closure_status"] = "NOT_EVALUATED"
            annotated_uncomputed_count += 1
        row.setdefault("dynamic_state_closure_ready", None)
        row.setdefault("dynamic_state_closure_blocking_reasons", [])
    target["cases"] = cases
    target["uncomputed_cases"] = uncomputed

    campaign_coverage = target.get("coverage")
    if isinstance(campaign_coverage, Mapping):
        coverage = deepcopy(dict(campaign_coverage))
        coverage["dynamic_state_closure_status_counts"] = _counts(
            [_status(row, missing=False) for row in cases]
        )
        coverage["dynamic_state_closure_ready_case_count"] = sum(
            _status(row, missing=False) == "READY" for row in cases
        )
        coverage["dynamic_state_closure_blocked_case_count"] = sum(
            _status(row, missing=False) == "BLOCKED" for row in cases
        )
        component_counts = _component_status_counts(target, cases)
        existing = coverage.get("by_component")
        rows_by_component = {
            str(row.get("component_id")): deepcopy(dict(row))
            for row in existing
            if isinstance(row, Mapping) and row.get("component_id") is not None
        } if isinstance(existing, list) else {}
        for component, counts in component_counts.items():
            row = rows_by_component.setdefault("" if component is None else component, {})
            row["component_id"] = component
            row["dynamic_state_closure_status_counts"] = counts
            row["dynamic_state_closure_ready_case_count"] = counts.get("READY", 0)
            row["dynamic_state_closure_blocked_case_count"] = counts.get("BLOCKED", 0)
        coverage["by_component"] = [
            rows_by_component[key] for key in sorted(rows_by_component)
        ]
        target["coverage"] = coverage

    facility_coverage = target.get("conditional_diagnostic_facility_coverage")
    if isinstance(facility_coverage, Mapping) or isinstance(
        target.get("component_coverage"), Mapping
    ):
        facility_global, facility_components = _facility_case_statuses(target)
        grouped: dict[str, list[str]] = defaultdict(list)
        for identity, status in facility_global.items():
            grouped[facility_components[identity]].append(status)
        component_counts = {
            component: _counts(statuses)
            for component, statuses in sorted(grouped.items())
        }
        coverage = deepcopy(dict(facility_coverage)) if isinstance(
            facility_coverage, Mapping
        ) else {}
        coverage["dynamic_state_closure_status_counts"] = _counts(
            list(facility_global.values())
        )
        coverage["dynamic_state_closure_ready_case_count"] = sum(
            status == "READY" for status in facility_global.values()
        )
        coverage["dynamic_state_closure_blocked_case_count"] = sum(
            status == "BLOCKED" for status in facility_global.values()
        )
        stored_nested = coverage.get("component_case_accounting")
        stored_nested_items = (
            stored_nested.items() if isinstance(stored_nested, Mapping) else []
        )
        nested = {
            str(component): deepcopy(dict(row))
            for component, row in stored_nested_items
            if isinstance(row, Mapping)
        }
        top_level = target.get("component_coverage")
        top_level_items = top_level.items() if isinstance(top_level, Mapping) else []
        top = {
            str(component): deepcopy(dict(row))
            for component, row in top_level_items
            if isinstance(row, Mapping)
        }
        for component, counts in component_counts.items():
            for rows in (nested, top):
                row = rows.setdefault(component, {})
                row["dynamic_state_closure_status_counts"] = counts
                row["dynamic_state_closure_ready_case_count"] = counts.get("READY", 0)
                row["dynamic_state_closure_blocked_case_count"] = counts.get("BLOCKED", 0)
        coverage["component_case_accounting"] = nested
        target["conditional_diagnostic_facility_coverage"] = coverage
        target["component_coverage"] = top

    output["dynamic_state_closure_normalization"] = {
        "schema_version": "prism.dynamic_state_closure_normalization.v1",
        "status": "EXPLICIT_MISSING_EVIDENCE_ANNOTATED",
        "annotated_case_count": annotated_case_count,
        "annotated_uncomputed_case_count": annotated_uncomputed_count,
        "closure_inferred": False,
        "provider_qualification": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "policy": (
            "Missing dynamic-state fields are labeled NOT_DECLARED or NOT_EVALUATED; "
            "no READY/BLOCKED status is inferred from scalar balances or process values."
        ),
    }
    return output


def _audit_campaign(result: Mapping[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    cases = _rows(result.get("cases", []), "campaign.cases")
    expected = _counts([_status(case, missing=False) for case in cases])
    coverage = result.get("coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    _compare_counts(
        checks,
        "campaign.coverage.dynamic_state_closure_status_counts",
        expected,
        coverage.get("dynamic_state_closure_status_counts"),
    )
    expected_components = _campaign_component_expected(result, cases)
    stored_components = coverage.get("by_component")
    stored_by_component = {
        str(row.get("component_id")): row.get("dynamic_state_closure_status_counts")
        for row in stored_components
        if isinstance(row, Mapping) and row.get("component_id") is not None
    } if isinstance(stored_components, list) else {}
    for component, component_expected in expected_components.items():
        _compare_counts(
            checks,
            f"campaign.coverage.by_component[{component}].dynamic_state_closure_status_counts",
            component_expected,
            stored_by_component.get(component),
        )
    return {"status_counts": expected, "component_status_counts": expected_components}


def _audit_facility(result: Mapping[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    global_status, component_status = _facility_case_statuses(result)
    expected = _counts(list(global_status.values()))
    coverage = result.get("conditional_diagnostic_facility_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    _compare_counts(
        checks,
        "facility.conditional_diagnostic_facility_coverage.dynamic_state_closure_status_counts",
        expected,
        coverage.get("dynamic_state_closure_status_counts"),
    )
    expected_components: dict[str, dict[str, int]] = defaultdict(dict)
    grouped: dict[str, list[str]] = defaultdict(list)
    for identity, status in global_status.items():
        grouped[component_status[identity]].append(status)
    expected_components = {
        component: _counts(statuses) for component, statuses in sorted(grouped.items())
    }
    stored_components = result.get("component_coverage")
    if not isinstance(stored_components, Mapping):
        stored_components = {}
    nested_components = coverage.get("component_case_accounting")
    if not isinstance(nested_components, Mapping):
        nested_components = {}
    for component, component_expected in expected_components.items():
        for prefix, source in (
            ("facility.component_coverage", stored_components),
            ("facility.conditional_diagnostic_facility_coverage.component_case_accounting", nested_components),
        ):
            row = source.get(component) if isinstance(source, Mapping) else None
            stored = row.get("dynamic_state_closure_status_counts") if isinstance(row, Mapping) else None
            _compare_counts(
                checks,
                f"{prefix}[{component}].dynamic_state_closure_status_counts",
                component_expected,
                stored,
            )
    return {"status_counts": expected, "component_status_counts": expected_components}


def _aggregate_campaign_results(
    results: Sequence[Mapping[str, Any]],
) -> tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str]]:
    global_status: dict[tuple[str, ...], str] = {}
    component_status: dict[tuple[str, ...], str] = {}
    for result in results:
        cases = _rows(result.get("cases", []), "campaign.cases")
        events = _rows(result.get("events", []), "campaign.events")
        event_component = {
            str(event.get("id")): str(event.get("model_component_id"))
            for event in events
            if event.get("id") is not None and event.get("model_component_id") is not None
        }
        missing = _rows(result.get("uncomputed_cases", []), "campaign.uncomputed_cases")
        for case in cases:
            identity = _case_identity(case)
            global_status[identity] = _status(case, missing=False)
            component_status[identity] = event_component.get(
                str(case.get("event_id", "")), "UNMAPPED_COMPONENT"
            )
        for case in missing:
            identity = _case_identity(case)
            if identity not in global_status:
                global_status[identity] = _status(case, missing=True)
                component_status[identity] = event_component.get(
                    str(case.get("event_id", "")), "UNMAPPED_COMPONENT"
                )
    return global_status, component_status


def build_dynamic_state_closure_ledger_audit(
    *,
    campaign_results: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    facility_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute and compare dynamic closure status ledgers.

    ``campaign_results`` may contain all campaign ledgers used to build the
    facility result.  When both inputs are provided, their deduplicated case
    identities are compared in addition to each ledger's stored coverage.
    """
    checks: list[dict[str, Any]] = []
    if campaign_results is None:
        campaigns: list[Mapping[str, Any]] = []
    elif isinstance(campaign_results, Mapping):
        campaigns = [campaign_results]
    elif isinstance(campaign_results, Sequence) and not isinstance(campaign_results, (str, bytes)):
        campaigns = [row for row in campaign_results if isinstance(row, Mapping)]
        if len(campaigns) != len(campaign_results):
            raise DynamicStateClosureLedgerAuditError("campaign_results must contain objects")
    else:
        raise DynamicStateClosureLedgerAuditError("campaign_results must be an object or array")

    campaign_audits = [_audit_campaign(result, checks) for result in campaigns]
    facility_audit = _audit_facility(facility_result, checks) if facility_result is not None else None
    if campaigns and facility_result is not None:
        campaign_global, campaign_components = _aggregate_campaign_results(campaigns)
        facility_global, facility_components = _facility_case_statuses(facility_result)
        _compare_counts(
            checks,
            "cross_ledger.global_dynamic_state_closure_status_counts",
            _counts(list(campaign_global.values())),
            _counts(list(facility_global.values())),
        )
        campaign_grouped: dict[str, list[str]] = defaultdict(list)
        facility_grouped: dict[str, list[str]] = defaultdict(list)
        for identity, status in campaign_global.items():
            campaign_grouped[campaign_components[identity]].append(status)
        for identity, status in facility_global.items():
            facility_grouped[facility_components[identity]].append(status)
        _compare_counts(
            checks,
            "cross_ledger.component_id_counts",
            _counts(list(campaign_grouped)),
            _counts(list(facility_grouped)),
        )
        for component in sorted(set(campaign_grouped) | set(facility_grouped)):
            _compare_counts(
                checks,
                f"cross_ledger.component[{component}].dynamic_state_closure_status_counts",
                _counts(campaign_grouped.get(component, [])),
                _counts(facility_grouped.get(component, [])),
            )

    blocking = [check["reason"] for check in checks if check["status"] == "BLOCKED"]
    return {
        "schema_version": DYNAMIC_STATE_CLOSURE_LEDGER_AUDIT_SCHEMA,
        "status": "PASS" if not blocking else "BLOCKED",
        "campaign_count": len(campaigns),
        "facility_supplied": facility_result is not None,
        "checks": checks,
        "check_count": len(checks),
        "blocking_reason_count": len(blocking),
        "blocking_reasons": blocking,
        "campaign_audits": campaign_audits,
        "facility_audit": facility_audit,
        "diagnostic_only": True,
        "frequency_reallocation_performed": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "interpretation": (
            "Counts are recomputed from explicit case status fields and case identities. "
            "A PASS proves ledger accounting consistency only; it does not qualify provider "
            "packets, physical validation, accident scope, or facility QRA."
        ),
    }


__all__ = [
    "DYNAMIC_STATE_CLOSURE_LEDGER_AUDIT_SCHEMA",
    "DynamicStateClosureLedgerAuditError",
    "annotate_missing_dynamic_state_closure_fields",
    "build_dynamic_state_closure_ledger_audit",
]
