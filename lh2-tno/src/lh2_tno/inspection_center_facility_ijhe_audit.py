"""Fail-closed audit for the reconstructed facility HAZOP handoff.

This audit is intentionally narrower than the full IJHE completion audit.  It
checks that the new facility bridge, annual handoff, and literature-frequency
sensitivity records are internally traceable.  It never promotes diagnostic
provider packets to qualified facility QRA evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _check(check_id: str, passed: bool, reason: str, **evidence: Any) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "PASS" if passed else "BLOCKED",
        "passed": bool(passed),
        "blocking_reason": None if passed else reason,
        "evidence": evidence,
    }


def build_inspection_center_facility_ijhe_audit(
    bridge: Mapping[str, Any], handoff: Mapping[str, Any]
) -> dict[str, Any]:
    """Audit the facility handoff and preserve its qualification boundary."""
    checks: list[dict[str, Any]] = []
    bridge_schema = bridge.get("schema_version")
    checks.append(_check(
        "facility_bridge_schema",
        bridge_schema == "prism.inspection_center_facility_hazop_bridge.v1",
        "facility bridge schema is not the declared PRISM facility bridge contract",
        schema_version=bridge_schema,
    ))
    components = bridge.get("components")
    components = components if isinstance(components, Mapping) else {}
    withheld = sorted(
        str(component_id)
        for component_id, component in components.items()
        if isinstance(component, Mapping)
        and component.get("status") == "WITHHELD_HAZOP_NO_DEVIATION"
    )
    selected = [
        (str(component_id), component)
        for component_id, component in components.items()
        if isinstance(component, Mapping)
        and component.get("status") == "CONSEQUENCE_BRANCHES_EVALUATED"
    ]
    checks.append(_check(
        "facility_bridge_component_partition",
        len(components) == 3 and len(selected) == 1 and len(withheld) == 2,
        "bridge must contain one evaluated deviation and two explicitly withheld normal components",
        component_count=len(components),
        selected_component_ids=[row[0] for row in selected],
        withheld_component_ids=withheld,
    ))
    mapping = bridge.get("facility_bridge_audit", {}).get("explicit_provider_component_mapping")
    mapping_ok = isinstance(mapping, Mapping) and all(
        isinstance(mapping.get(key), str) and mapping.get(key)
        for key in ("observed_component_id", "provider_component_id", "provider_port_id")
    )
    checks.append(_check(
        "explicit_provider_component_mapping",
        mapping_ok,
        "provider boundary identity must be established by an explicit mapping record",
        mapping=dict(mapping) if isinstance(mapping, Mapping) else mapping,
    ))
    state_handoff = bridge.get("facility_bridge_audit", {}).get("state_snapshot_handoff")
    state_handoff_valid = (
        isinstance(state_handoff, list)
        and len(state_handoff) == len(components)
        and all(
            isinstance(row, Mapping)
            and isinstance(row.get("observed_component_id"), str)
            and row.get("state_snapshot_schema") == "prism.equipment_state_snapshot.v1"
            and isinstance(row.get("state_snapshot_digest"), str)
            and len(row.get("state_snapshot_digest")) == 64
            and isinstance(row.get("captured_at_s"), (int, float))
            and row.get("provider_state_snapshot_echo") is False
            and row.get("qualification_status") == "WITHHELD_PROVIDER_ECHO_NOT_CONFIRMED"
            for row in state_handoff
        )
    )
    checks.append(_check(
        "state_snapshot_handoff_boundary",
        bool(state_handoff_valid),
        "state snapshots must be carried to the explicit provider boundary while provider echo remains unqualified",
        row_count=len(state_handoff) if isinstance(state_handoff, list) else None,
        provider_state_snapshot_echoes=(
            sum(bool(row.get("provider_state_snapshot_echo")) for row in state_handoff)
            if isinstance(state_handoff, list) else None
        ),
    ))

    handoff_schema = handoff.get("schema_version")
    checks.append(_check(
        "facility_handoff_schema",
        handoff_schema == "prism.inspection_center_facility_campaign_handoff.v1",
        "facility campaign handoff schema is not the declared PRISM contract",
        schema_version=handoff_schema,
    ))
    ledger = handoff.get("facility_ledger")
    ledger = ledger if isinstance(ledger, Mapping) else {}
    population = ledger.get("population_accounting")
    population = population if isinstance(population, Mapping) else {}
    checks.append(_check(
        "explicit_annual_condition_population",
        population.get("status") == "EXPLICIT_CONDITION_POPULATION",
        "annual population must come from an explicit condition record",
        status=population.get("status"),
    ))
    checks.append(_check(
        "diagnostic_qra_boundary",
        handoff.get("status") == "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
        and ledger.get("status") == "PARTIAL_FACILITY_SCOPE"
        and ledger.get("total_facility_annual_ir_low_high") is None
        and ledger.get("total_facility_expected_death_fn_low_high") is None,
        "partial diagnostic handoff must not claim complete facility IR/F-N",
        handoff_status=handoff.get("status"),
        ledger_status=ledger.get("status"),
        facility_ir_available=ledger.get("total_facility_annual_ir_low_high") is not None,
        facility_fn_available=ledger.get("total_facility_expected_death_fn_low_high") is not None,
    ))
    frequency = handoff.get("frequency_uncertainty")
    frequency = frequency if isinstance(frequency, Mapping) else {}
    rows = frequency.get("rows")
    rows = rows if isinstance(rows, list) else []
    frequency_ok = (
        frequency.get("schema_version") == "prism.facility_frequency_sensitivity.v1"
        and frequency.get("status") == "LITERATURE_SCENARIO_SENSITIVITY_AVAILABLE"
        and frequency.get("facility_credible_interval") is False
        and frequency.get("frequency_inference_performed") is False
        and rows
        and all(
            isinstance(row, Mapping)
            and row.get("frequency_is_not_inferred") is True
            and row.get("status") == "FIXED_CATALOGUE_RATE_SCENARIO"
            for row in rows
        )
    )
    checks.append(_check(
        "literature_frequency_sensitivity_boundary",
        bool(frequency_ok),
        "frequency sensitivity must remain an explicit literature scenario ledger, not inferred confidence bounds",
        schema_version=frequency.get("schema_version"),
        status=frequency.get("status"),
        row_count=len(rows),
        marginal_p05_per_year=frequency.get("marginal_p05_per_year"),
        marginal_p95_per_year=frequency.get("marginal_p95_per_year"),
    ))
    audit_meta = handoff.get("facility_campaign_handoff_audit")
    audit_meta = audit_meta if isinstance(audit_meta, Mapping) else {}
    checks.append(_check(
        "no_qualification_or_physical_validation_claim",
        audit_meta.get("provider_packet_qualification") == "UNQUALIFIED_DIAGNOSTIC"
        and audit_meta.get("physical_validation_claim") is False
        and audit_meta.get("facility_qra_claim") is False,
        "diagnostic handoff must keep provider qualification and physical validation closed",
        provider_packet_qualification=audit_meta.get("provider_packet_qualification"),
        physical_validation_claim=audit_meta.get("physical_validation_claim"),
        facility_qra_claim=audit_meta.get("facility_qra_claim"),
    ))

    blocking = [row["blocking_reason"] for row in checks if row["blocking_reason"]]
    return {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS" if not blocking else "INCOMPLETE_EVIDENCE",
        "checks": checks,
        "blocking_reasons": blocking,
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "provider_packet_qualification": "UNQUALIFIED_DIAGNOSTIC",
            "physical_validation_claim": False,
            "interpretation": (
                "Structural traceability passes only when all checks pass; this record "
                "does not close the full IJHE evidence audit or promote facility QRA."
            ),
        },
    }
