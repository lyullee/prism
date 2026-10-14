"""Fail-closed IJHE readiness audit for one PRISM campaign.

This module does not certify a QRA.  It collects the existing evidence ledgers
and states whether the declared scope can be presented as complete.  Missing
physical validation, missing accident families, or withheld facility risk are
blocking evidence rather than a zero-valued result.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .release_ledger import evaluate_facility_release_boundary


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and value not in (float("inf"), float("-inf"))


def _check(name: str, passed: bool, evidence: Any, blocking_reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if passed else "BLOCKED",
        "evidence": evidence,
        "blocking_reason": None if passed else blocking_reason,
    }


def _normalise_uncertainty_result(
    uncertainty_result: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Accept either the standalone uncertainty ledger or a campaign wrapper.

    The CLI may receive the complete campaign JSON, where the uncertainty
    ledger lives under ``literature_frequency_uncertainty``.  Treating that
    wrapper as an empty uncertainty report would hide existing scenarios in
    the IJHE audit.  This helper only unwraps an explicit mapping; it never
    creates a scenario or promotes an incomplete facility interval.
    """
    if uncertainty_result is None:
        return None
    if isinstance(uncertainty_result.get("scenarios"), list):
        return uncertainty_result
    # ``build_facility_assessment`` wraps the same ledger under
    # ``frequency_uncertainty``.  Accept that explicit wrapper as well as the
    # campaign-level historical name; never synthesize a missing scenario.
    for key in ("literature_frequency_uncertainty", "frequency_uncertainty"):
        nested = uncertainty_result.get(key)
        if isinstance(nested, Mapping):
            return nested
    return uncertainty_result


def build_ijhe_completion_audit(
    current_status: Mapping[str, Any],
    scope_matrix: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    uncertainty_result: Mapping[str, Any] | None = None,
    provider_worklist: Mapping[str, Any] | None = None,
    diagnostic_adapter_registry: Mapping[str, Any] | None = None,
    diagnostic_adapter_execution: Mapping[str, Any] | None = None,
    diagnostic_worklist_evidence: Mapping[str, Any] | None = None,
    diagnostic_campaign_binding: Mapping[str, Any] | None = None,
    facility_assessment: Mapping[str, Any] | None = None,
    vertical_handoff_result: Mapping[str, Any] | None = None,
    native_model_contract_audit: Mapping[str, Any] | None = None,
    frequency_provenance_report: Mapping[str, Any] | None = None,
    scenario_evidence_report: Mapping[str, Any] | None = None,
    native_full_bore_result: Mapping[str, Any] | None = None,
    native_full_bore_frequency_result: Mapping[str, Any] | None = None,
    native_packet_coverage_ledger: Mapping[str, Any] | None = None,
    native_packet_campaign_ledger: Mapping[str, Any] | None = None,
    provider_qualification_coverage: Mapping[str, Any] | None = None,
    validation_evidence_matrix: Mapping[str, Any] | None = None,
    scope_ledger_consistency: Mapping[str, Any] | None = None,
    native_binding_reconciliation: Mapping[str, Any] | None = None,
    facility_case_packet_coverage: Mapping[str, Any] | None = None,
    combined_chain_closure: Mapping[str, Any] | None = None,
    risk_atom_chain_audit: Mapping[str, Any] | None = None,
    equipment_state_release_audit: Mapping[str, Any] | None = None,
    slabx_validation_evidence: Mapping[str, Any] | None = None,
    realtime_cache_benchmark: Mapping[str, Any] | None = None,
    domain_recovery_audit: Mapping[str, Any] | None = None,
    state_snapshot_binding_audit: Mapping[str, Any] | None = None,
    native_scope_packet_catalog_verification: Mapping[str, Any] | None = None,
    observed_state_evidence: Mapping[str, Any] | None = None,
    facility_aggregate_closure_audit: Mapping[str, Any] | None = None,
    facility_component_contribution_audit: Mapping[str, Any] | None = None,
    facility_frequency_uncertainty_audit: Mapping[str, Any] | None = None,
    isolation_union_extension_verification: Mapping[str, Any] | None = None,
    observed_state_model_binding_audit: Mapping[str, Any] | None = None,
    external_equipment_model_contract_audit: Mapping[str, Any] | None = None,
    hazop_forecast_scan: Mapping[str, Any] | None = None,
    realtime_hazop_mode_trace: Mapping[str, Any] | None = None,
    external_document_evidence: Mapping[str, Any] | None = None,
    external_release_artifact_intake: Mapping[str, Any] | None = None,
    facility_evidence_request: Mapping[str, Any] | None = None,
    hazop_integrated_risk: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an evidence-based readiness report without promoting claims."""
    uncertainty = _normalise_uncertainty_result(uncertainty_result)
    # The status ledger historically used
    # ``external_provider_evidence_accident_release_promotion_status`` while
    # the newer release-inventory record uses
    # ``external_provider_evidence_release_inventory_status``.  Read both
    # names so a readiness report never turns a known fail-closed result into
    # an unexplained ``null`` merely because the ledger predates the alias.
    release_inventory_status = current_status.get("external_provider_evidence_release_inventory_status")
    if release_inventory_status is None:
        release_inventory_status = current_status.get("external_provider_evidence_accident_release_promotion_status")
    actual_packet_available = current_status.get("provider_release_contract_actual_facility_packet_available")
    if actual_packet_available is None:
        qualified_count = current_status.get("external_provider_evidence_accident_release_qualified_files")
        if isinstance(qualified_count, int) and qualified_count >= 0:
            actual_packet_available = qualified_count > 0
        elif release_inventory_status is not None:
            actual_packet_available = release_inventory_status == "QUALIFIED_ACCIDENT_RELEASE_EXPORT"
    qualification_status = None
    qualified_provider_packet_count = None
    qualified_worklist_coverage = False
    if provider_qualification_coverage is not None:
        qualification_status = provider_qualification_coverage.get("qualification_status")
        qualified_provider_packet_count = provider_qualification_coverage.get(
            "qualified_provider_packet_count"
        )
        qualified_worklist_coverage = (
            qualification_status == "QUALIFIED_FULL_WORKLIST"
            and isinstance(qualified_provider_packet_count, int)
            and qualified_provider_packet_count > 0
            and provider_qualification_coverage.get("exact_match_count")
            == provider_qualification_coverage.get("worklist_event_count")
            and provider_qualification_coverage.get("unqualified_exact_match_count") == 0
        )
        # A partial coverage report may contain one qualified-looking row, but
        # it is not evidence that the current facility campaign has an actual
        # qualified provider release.  Only a complete worklist qualification
        # may fill an otherwise absent status-ledger value, and an explicit
        # status-ledger ``False`` always remains authoritative.
        if (
            actual_packet_available is None
            and qualified_worklist_coverage
            and isinstance(qualified_provider_packet_count, int)
            and qualified_provider_packet_count > 0
        ):
            actual_packet_available = True
    cases = campaign_result.get("cases", [])
    events = campaign_result.get("events", [])
    timing = campaign_result.get("timing", {})
    fresh_physics_cases = timing.get("fresh_physics_cases")
    if provider_worklist is not None:
        worklist_event_count = provider_worklist.get("generated_event_count")
        worklist_packet_count = provider_worklist.get("provider_packet_count")
        status_counts = provider_worklist.get("status_counts", {})
        worklist_uncomputed_count = (
            status_counts.get("UNCOMPUTED_PROVIDER_PACKET", 0)
            + status_counts.get("UNCOMPUTED_NO_ACCIDENT_PORT", 0)
        ) if isinstance(status_counts, Mapping) else None
        worklist_status = provider_worklist.get("status")
        worklist_diagnostic_adapter_count = provider_worklist.get(
            "model_binding_diagnostic_release_adapter_component_count"
        )
    else:
        worklist_event_count = current_status.get("equipment_provider_release_worklist_event_count")
        worklist_packet_count = current_status.get("equipment_provider_release_worklist_provider_packet_count")
        worklist_uncomputed_count = current_status.get("equipment_provider_release_worklist_uncomputed_count")
        worklist_status = current_status.get("equipment_provider_release_worklist_status")
        worklist_diagnostic_adapter_count = current_status.get(
            "equipment_model_binding_diagnostic_release_adapter_component_count"
        )
    worklist_complete = (
        isinstance(worklist_event_count, int)
        and worklist_event_count > 0
        and isinstance(worklist_packet_count, int)
        and worklist_packet_count == worklist_event_count
        and isinstance(worklist_uncomputed_count, int)
        and worklist_uncomputed_count == 0
        and isinstance(worklist_status, str)
        and worklist_status.startswith("READY_FOR_PROVIDER_PACKETS")
    )
    worklist_complete = worklist_complete or qualified_worklist_coverage
    registry = diagnostic_adapter_registry
    if registry is None and current_status.get("diagnostic_adapter_runner_implemented") is True:
        registry = {
            "status": current_status.get("diagnostic_adapter_registry_live_audit_status"),
            "adapter_count": current_status.get("diagnostic_adapter_registry_adapter_count"),
            "resolved_adapter_count": current_status.get(
                "diagnostic_adapter_registry_resolved_adapter_count"
            ),
            "provider_instance_count": current_status.get(
                "diagnostic_adapter_registry_provider_instance_count"
            ),
            "qualified_provider_packet_count": current_status.get(
                "diagnostic_adapter_registry_qualified_packet_count"
            ),
            "record": current_status.get("diagnostic_adapter_registry_live_audit_record"),
        }
    registry_complete = (
        isinstance(registry, Mapping)
        and isinstance(registry.get("adapter_count"), int)
        and registry.get("adapter_count") > 0
        and registry.get("resolved_adapter_count") == registry.get("adapter_count")
        and isinstance(registry.get("status"), str)
        and registry.get("status", "").startswith("DECLARED_ADAPTERS_RESOLVED")
    ) if registry is not None else None
    executed_cases = [
        row for row in cases
        if isinstance(row, Mapping) and str(row.get("status", "")).startswith("EXECUTED")
    ]
    ledger_cases = [
        row for row in executed_cases
        if isinstance(row.get("termination"), Mapping)
        and _finite(row["termination"].get("time_s"))
        and row["termination"].get("time_s") > 0
        and isinstance(row.get("mass_ledger"), Mapping)
        and _finite(row["mass_ledger"].get("end_to_end_residual_kg"))
    ]
    release_ledger = campaign_result.get("release_termination_inventory_ledger")
    release_ledger_summary = (
        release_ledger.get("summary")
        if isinstance(release_ledger, Mapping)
        and isinstance(release_ledger.get("summary"), Mapping)
        else None
    )
    release_ledger_rows = (
        release_ledger.get("rows")
        if isinstance(release_ledger, Mapping)
        and isinstance(release_ledger.get("rows"), list)
        else None
    )
    release_ledger_valid = release_ledger is None or (
        isinstance(release_ledger, Mapping)
        and release_ledger.get("schema_version")
        == "prism.release_termination_inventory_ledger.v1"
        and release_ledger_rows is not None
        and len(release_ledger_rows) == len(cases)
        and release_ledger_summary is not None
        and release_ledger_summary.get("case_count") == len(cases)
    )
    structural_worklist_coverage = False
    native_catalog_structural_coverage = False
    native_catalog_evidence: dict[str, Any] = {}
    if native_scope_packet_catalog_verification is not None:
        native_catalog = native_scope_packet_catalog_verification
        catalog_rows = native_catalog.get("event_rows")
        state_binding = native_catalog.get("state_snapshot_binding")
        state_binding = state_binding if isinstance(state_binding, Mapping) else {}
        frequency_event_count = native_catalog.get("frequency_event_count")
        exact_packet_count = native_catalog.get("exact_native_packet_count")
        uncomputed_event_count = native_catalog.get("uncomputed_event_count")
        native_catalog_structural_coverage = (
            native_catalog.get("schema_version")
            == "prism.native_generic_scope_packet_catalog.v1"
            and native_catalog.get("status") == "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED"
            and isinstance(catalog_rows, list)
            and isinstance(frequency_event_count, int)
            and frequency_event_count > 0
            and isinstance(exact_packet_count, int)
            and exact_packet_count == frequency_event_count
            and isinstance(uncomputed_event_count, int)
            and uncomputed_event_count == 0
            and all(
                isinstance(row, Mapping) and row.get("status") == "EXACT_NATIVE_PACKET"
                for row in catalog_rows
            )
            and native_catalog.get("provider_packet_promoted") is False
            and native_catalog.get("frequency_inference_performed") is False
            and native_catalog.get("physical_validation_claim") is False
            and native_catalog.get("facility_qra_claim") is False
            and state_binding.get("status") == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
            and state_binding.get("record_count") == frequency_event_count
            and state_binding.get("bound_count") == frequency_event_count
            and state_binding.get("unbound_count") == 0
            and state_binding.get("digest_mismatch_count") == 0
        )
        native_catalog_evidence = {
            "record": native_catalog.get("_record_path"),
            "schema_version": native_catalog.get("schema_version"),
            "status": native_catalog.get("status"),
            "frequency_event_count": frequency_event_count,
            "exact_native_packet_count": exact_packet_count,
            "uncomputed_event_count": uncomputed_event_count,
            "state_snapshot_binding": state_binding,
            "provider_packet_promoted": native_catalog.get("provider_packet_promoted"),
            "frequency_inference_performed": native_catalog.get("frequency_inference_performed"),
            "physical_validation_claim": native_catalog.get("physical_validation_claim"),
            "facility_qra_claim": native_catalog.get("facility_qra_claim"),
        }
    structural_worklist_coverage = native_catalog_structural_coverage
    checks = [
        _check(
            "equipment_state_to_release_to_consequence",
            bool(events) and bool(cases) and bool(executed_cases),
            {
                "generated_event_count": len(events),
                "case_count": len(cases),
                "executed_case_count": len(executed_cases),
            },
            "no executed release-to-consequence case is present",
        ),
    ]
    if observed_state_evidence is not None:
        observed = observed_state_evidence
        policy = observed.get("policy")
        policy = policy if isinstance(policy, Mapping) else {}
        model_binding = observed_state_model_binding_audit
        model_binding_policy = (
            model_binding.get("policy")
            if isinstance(model_binding, Mapping)
            and isinstance(model_binding.get("policy"), Mapping)
            else {}
        )
        model_binding_rows = (
            model_binding.get("rows")
            if isinstance(model_binding, Mapping)
            else None
        )
        model_binding_valid = True
        if model_binding is not None:
            model_binding_valid = (
                model_binding.get("schema")
                == "prism.observed_state_model_binding_audit.v1"
                and model_binding.get("status")
                == "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY"
                and isinstance(model_binding.get("observed_component_count"), int)
                and model_binding.get("observed_component_count") > 0
                and model_binding.get("state_model_bound_component_count")
                == model_binding.get("observed_component_count")
                and model_binding.get("diagnostic_release_adapter_component_count")
                == model_binding.get("observed_component_count")
                and model_binding.get("qualified_provider_packet_count") == 0
                and isinstance(model_binding_rows, list)
                and len(model_binding_rows)
                == model_binding.get("observed_component_count")
                and all(
                    isinstance(row, Mapping)
                    and row.get("status")
                    == "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"
                    and row.get("state_export_status") == "supported"
                    and row.get("diagnostic_release_adapter_status") == "available"
                    and row.get("accident_release_export_status") == "missing"
                    for row in model_binding_rows
                )
                and model_binding.get("blocking_reasons") == []
                and model_binding_policy.get(
                    "normal_state_model_is_not_accident_release"
                ) is True
                and model_binding_policy.get(
                    "diagnostic_adapter_is_not_qualified_provider"
                ) is True
                and model_binding_policy.get("release_event_binding_is_not_created")
                is True
                and model_binding_policy.get("frequency_is_not_assigned") is True
                and model_binding_policy.get("facility_ir_fn_promotion") is False
            )
        observed_valid = (
            observed.get("schema_version") == "prism.observed_equipment_state_evidence.v1"
            and observed.get("status") == "OBSERVATION_STATE_EVIDENCE_ONLY"
            and isinstance(observed.get("source_count"), int)
            and observed.get("source_count") > 0
            and isinstance(observed.get("sample_count"), int)
            and observed.get("sample_count") > 0
            and isinstance(observed.get("component_count"), int)
            and observed.get("component_count") > 0
            and isinstance(observed.get("source_rows"), list)
            and len(observed.get("source_rows")) == observed.get("source_count")
            and isinstance(observed.get("component_rows"), list)
            and len(observed.get("component_rows")) == observed.get("component_count")
            and policy.get("canonical_snapshot_schema") == "prism.equipment_state_snapshot.v1"
            and policy.get("state_only") is True
            and policy.get("release_scenario_generated") is False
            and policy.get("frequency_inference_performed") is False
            and policy.get("sensor_frequency_learning_used") is False
            and policy.get("provider_packet_promoted") is False
            and policy.get("physical_validation_claim") is False
            and policy.get("facility_qra_claim") is False
            and policy.get("diagnostic_only") is True
            and model_binding_valid
        )
        checks.append(
            {
                "name": "diagnostic_observed_equipment_state_evidence",
                "status": "PASS" if observed_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None if observed_valid else "observed equipment-state evidence is missing or malformed",
                "evidence": {
                    "record": observed.get("_record_path"),
                    "schema_version": observed.get("schema_version"),
                    "status": observed.get("status"),
                    "source_count": observed.get("source_count"),
                    "sample_count": observed.get("sample_count"),
                    "component_count": observed.get("component_count"),
                    "policy": policy,
                    "model_binding": {
                        "record": (
                            model_binding.get("_record_path")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "schema": (
                            model_binding.get("schema")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "status": (
                            model_binding.get("status")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "observed_component_count": (
                            model_binding.get("observed_component_count")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "state_model_bound_component_count": (
                            model_binding.get("state_model_bound_component_count")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "diagnostic_release_adapter_component_count": (
                            model_binding.get(
                                "diagnostic_release_adapter_component_count"
                            )
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "facility_component_identity_resolved_count": (
                            model_binding.get("facility_component_identity_resolved_count")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "facility_component_identity_unresolved_count": (
                            model_binding.get("facility_component_identity_unresolved_count")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "qualified_provider_packet_count": (
                            model_binding.get("qualified_provider_packet_count")
                            if isinstance(model_binding, Mapping)
                            else None
                        ),
                        "valid": model_binding_valid,
                    },
                },
                "interpretation": (
                    "Observed telemetry supports equipment-state calibration and snapshot review. "
                    "The optional model-binding ledger confirms the facility-neutral normal-state "
                    "model and keeps its diagnostic adapter separate from accident release. "
                    "The evidence does not generate an accident, infer frequency, qualify a provider "
                    "packet, or promote facility IR/F-N."
                ),
            }
        )
    if native_model_contract_audit is not None:
        native_audit = native_model_contract_audit
        native_rows = native_audit.get("rows")
        native_audit_valid = (
            native_audit.get("schema_version") == "prism.external_model_contract_audit.v1"
            and native_audit.get("status") in {
                "NATIVE_ACCIDENT_EXPORT_MISSING",
                "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND",
                "CONTRACT_AUDIT_INCOMPLETE",
            }
            and isinstance(native_rows, list)
            and isinstance(native_audit.get("binding_count"), int)
            and native_audit.get("binding_count") == len(native_rows)
            and native_audit.get("provider_packet_promoted") is False
            and native_audit.get("frequency_inference_performed") is False
            and native_audit.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "external_native_model_contract_audit",
                "status": "PASS" if native_audit_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None if native_audit_valid else "native external model contract audit is missing or malformed",
                "evidence": {
                    "record": native_audit.get("_record_path"),
                    "status": native_audit.get("status"),
                    "binding_count": native_audit.get("binding_count"),
                    "native_accident_export_component_count": native_audit.get(
                        "native_accident_export_component_count"
                    ),
                    "diagnostic_adapter_contract_verified_count": native_audit.get(
                        "diagnostic_adapter_contract_verified_count"
                    ),
                    "provider_packet_promoted": native_audit.get("provider_packet_promoted"),
                    "frequency_inference_performed": native_audit.get("frequency_inference_performed"),
                    "facility_qra_claim": native_audit.get("facility_qra_claim"),
                },
                "interpretation": (
                    "This static audit separates native external accident export methods from "
                    "PRISM-side diagnostic wrappers. It is evidence of the integration boundary, "
                    "not a qualified provider packet or facility QRA."
                ),
            }
        )
    if native_binding_reconciliation is not None:
        reconciliation = native_binding_reconciliation
        reconciliation_valid = (
            reconciliation.get("schema_version") == "prism.native_binding_reconciliation.v1"
            and reconciliation.get("status") == "RECONCILED_NATIVE_INTERFACES"
            and isinstance(reconciliation.get("rows"), list)
            and isinstance(reconciliation.get("native_accident_export_component_count"), int)
            and reconciliation.get("reconciled_native_component_count")
            == reconciliation.get("native_accident_export_component_count")
            and reconciliation.get("provider_packet_promoted") is False
            and reconciliation.get("frequency_inference_performed") is False
            and reconciliation.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "native_model_binding_reconciliation",
                "status": "PASS" if reconciliation_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if reconciliation_valid
                    else "native model binding catalog does not reconcile with the external source audit"
                ),
                "evidence": {
                    "record": reconciliation.get("_record_path"),
                    "status": reconciliation.get("status"),
                    "native_accident_export_component_count": reconciliation.get(
                        "native_accident_export_component_count"
                    ),
                    "reconciled_native_component_count": reconciliation.get(
                        "reconciled_native_component_count"
                    ),
                    "blocking_reason_count": len(reconciliation.get("blocking_reasons", []))
                    if isinstance(reconciliation.get("blocking_reasons"), list)
                    else None,
                    "provider_packet_promoted": reconciliation.get("provider_packet_promoted"),
                    "frequency_inference_performed": reconciliation.get(
                        "frequency_inference_performed"
                    ),
                    "facility_qra_claim": reconciliation.get("facility_qra_claim"),
                },
                "interpretation": (
                    "The model catalog and native source audit agree on accident-export interface presence. "
                    "This closes a bookkeeping mismatch only; runtime packets, field qualification, frequency "
                    "evidence and facility IR/F-N remain separate gates."
                ),
            }
        )
    if native_full_bore_result is not None:
        full_bore = native_full_bore_result
        residual = full_bore.get("provider_mass_residual_kg")
        natural_termination = full_bore.get("provider_termination_basis") == "model_pressure_equalization"
        full_bore_valid = (
            full_bore.get("schema_version") == "prism.native_lh2dt_dynamic_pipe_full_bore_case.v1"
            and full_bore.get("status") == "END_TO_END_DIAGNOSTIC_EXECUTED"
            and natural_termination
            and full_bore.get("provider_pressure_equalized") is True
            and full_bore.get("provider_final_pressure_matches_ambient") is True
            and _finite(residual)
            and abs(float(residual)) <= 1e-8
            and full_bore.get("consequence_chain_executed") is True
            and full_bore.get("frequency_applied") is False
            and full_bore.get("facility_qra_claim") is False
            and full_bore.get("physical_validation_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_native_full_bore_chain",
                "status": "PASS" if full_bore_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None if full_bore_valid else "native full-bore diagnostic evidence is missing or malformed",
                "evidence": {
                    "record": full_bore.get("_record_path"),
                    "status": full_bore.get("status"),
                    "event_id": full_bore.get("event_id"),
                    "component_id": full_bore.get("component_id"),
                    "termination_basis": full_bore.get("provider_termination_basis"),
                    "provider_duration_s": full_bore.get("provider_duration_s"),
                    "provider_final_pressure_pa_abs": full_bore.get("provider_final_pressure_pa_abs"),
                    "provider_pressure_equalized": full_bore.get("provider_pressure_equalized"),
                    "provider_final_pressure_matches_ambient": full_bore.get("provider_final_pressure_matches_ambient"),
                    "provider_mass_residual_kg": residual,
                    "consequence_chain_executed": full_bore.get("consequence_chain_executed"),
                    "frequency_applied": full_bore.get("frequency_applied"),
                    "facility_qra_claim": full_bore.get("facility_qra_claim"),
                    "physical_validation_claim": full_bore.get("physical_validation_claim"),
                },
                "interpretation": (
                    "Native finite full-bore pressure-equalization output reached the PRISM liquid/two-phase "
                    "consequence chain. This is diagnostic integration evidence; it does not qualify a provider, "
                    "assign a frequency, or promote facility IR/F-N."
                ),
            }
        )
    if state_snapshot_binding_audit is not None:
        snapshot_audit = state_snapshot_binding_audit
        policy = snapshot_audit.get("policy")
        if not isinstance(policy, Mapping):
            policy = {}
        bound_count = snapshot_audit.get("bound_count")
        mismatch_count = snapshot_audit.get("digest_mismatch_count")
        snapshot_binding_valid = (
            snapshot_audit.get("schema_version") == "prism.state_snapshot_binding_audit.v1"
            and snapshot_audit.get("status") in {
                "STATE_SNAPSHOT_BOUND_AND_ECHOED",
                "PARTIAL_STATE_SNAPSHOT_BINDING",
            }
            and isinstance(bound_count, int)
            and bound_count > 0
            and mismatch_count == 0
            and policy.get("digest_only_is_binding") is False
            and policy.get("provider_echo_required") is True
            and snapshot_audit.get("physical_validation_claim") is False
            and snapshot_audit.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_equipment_state_snapshot_binding",
                "status": "PASS" if snapshot_binding_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if snapshot_binding_valid
                    else "no validated equipment state snapshot is both carried and echoed by a provider"
                ),
                "evidence": {
                    "record": snapshot_audit.get("_record_path"),
                    "schema_version": snapshot_audit.get("schema_version"),
                    "status": snapshot_audit.get("status"),
                    "record_count": snapshot_audit.get("record_count"),
                    "bound_count": bound_count,
                    "declared_digest_only_count": snapshot_audit.get(
                        "declared_digest_only_count"
                    ),
                    "unbound_count": snapshot_audit.get("unbound_count"),
                    "digest_mismatch_count": mismatch_count,
                    "policy": policy,
                },
                "interpretation": (
                    "At least one diagnostic provider received a canonical equipment state snapshot and "
                    "echoed its digest. Campaign rows without the payload remain unbound; this check "
                    "does not qualify physical accuracy, frequency or facility IR/F-N."
                ),
            }
        )
    if native_scope_packet_catalog_verification is not None:
        catalog = native_scope_packet_catalog_verification
        snapshot_summary = catalog.get("state_snapshot_binding")
        if not isinstance(snapshot_summary, Mapping):
            snapshot_summary = {}
        event_count = catalog.get("frequency_event_count")
        exact_count = catalog.get("exact_native_packet_count")
        uncomputed_count = catalog.get("uncomputed_event_count")
        catalog_valid = (
            catalog.get("schema_version") == "prism.native_generic_scope_packet_catalog.v1"
            and catalog.get("status") == "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED"
            and isinstance(event_count, int)
            and event_count > 0
            and exact_count == event_count
            and uncomputed_count == 0
            and snapshot_summary.get("status") == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
            and snapshot_summary.get("record_count") == event_count
            and snapshot_summary.get("bound_count") == event_count
            and snapshot_summary.get("unbound_count") == 0
            and catalog.get("provider_packet_promoted") is False
            and catalog.get("frequency_inference_performed") is False
            and catalog.get("physical_validation_claim") is False
            and catalog.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_native_scope_packet_catalog_coverage",
                "status": "PASS" if catalog_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if catalog_valid
                    else "native generic-scope catalog is missing exact packets or state-snapshot reconciliation"
                ),
                "evidence": {
                    "record": catalog.get("_record_path"),
                    "schema_version": catalog.get("schema_version"),
                    "status": catalog.get("status"),
                    "frequency_event_count": event_count,
                    "exact_native_packet_count": exact_count,
                    "uncomputed_event_count": uncomputed_count,
                    "state_snapshot_binding": snapshot_summary,
                    "provider_packet_promoted": catalog.get("provider_packet_promoted"),
                    "frequency_inference_performed": catalog.get("frequency_inference_performed"),
                    "physical_validation_claim": catalog.get("physical_validation_claim"),
                    "facility_qra_claim": catalog.get("facility_qra_claim"),
                },
                "interpretation": (
                    "The native generic-scope catalog closes diagnostic exact-packet coverage and preserves "
                    "the state snapshot gate. It remains separate from qualified provider evidence and does "
                    "not unlock facility IR/F-N."
                ),
            }
        )
    if native_full_bore_frequency_result is not None:
        full_bore_frequency = native_full_bore_frequency_result
        residual = full_bore_frequency.get("provider_mass_residual_kg")
        event_id = full_bore_frequency.get("event_id")
        frequency_event_id = full_bore_frequency.get("frequency_event_id")
        facility_campaign_present = "facility_campaign_executed" in full_bore_frequency
        facility_campaign_valid = (
            not facility_campaign_present
            or (
                full_bore_frequency.get("facility_campaign_executed") is True
                and full_bore_frequency.get("facility_campaign_status") == "PARTIAL_DECLARED_SCOPE"
                and full_bore_frequency.get("facility_campaign_event_count") == 5
                and full_bore_frequency.get("facility_campaign_case_count") == 5
                and full_bore_frequency.get("facility_campaign_executed_case_count") == 1
                and full_bore_frequency.get("facility_campaign_uncomputed_case_count") == 4
                and full_bore_frequency.get("facility_campaign_risk_atom_count") == 4
                and full_bore_frequency.get("facility_campaign_conditional_risk_available") is True
                and full_bore_frequency.get("facility_total_risk_available") is False
            )
        )
    if native_packet_coverage_ledger is not None:
        packet_ledger = native_packet_coverage_ledger
        packet_rows = packet_ledger.get("rows")
        packet_policy = packet_ledger.get("policy")
        if not isinstance(packet_policy, Mapping):
            packet_policy = {}
        expected_worklist_packets = (
            provider_worklist.get("generated_event_count")
            if isinstance(provider_worklist, Mapping)
            else None
        )
        ledger_valid = (
            packet_ledger.get("schema_version") == "prism.native_lh2dt_packet_coverage_ledger.v1"
            and packet_ledger.get("status") == "PARTIAL_NATIVE_DIAGNOSTIC_EVIDENCE"
            and isinstance(packet_rows, list)
            and len(packet_rows) == packet_ledger.get("packet_count")
            and packet_ledger.get("packet_count", 0) > 0
            and packet_ledger.get("consequence_chain_event_count", 0) <= packet_ledger.get("packet_count", 0)
            and packet_ledger.get("provider_packet_promoted_count") == 0
            and packet_ledger.get("physical_validation_claim_count") == 0
            and packet_ledger.get("facility_qra_claim_count") == 0
            and packet_policy.get("diagnostic_only") is True
            and packet_policy.get("frequency_inference_performed") is False
            and packet_policy.get("provider_packet_promoted") is False
            and packet_policy.get("facility_qra_claim") is False
            and packet_policy.get("physical_validation_claim") is False
            and all(
                isinstance(row, Mapping)
                and row.get("diagnostic_only") is True
                and row.get("provider_packet_promoted") is False
                and row.get("facility_qra_claim") is False
                and row.get("physical_validation_claim") is False
                for row in packet_rows
            )
            and (
                expected_worklist_packets is None
                or (
                    isinstance(packet_ledger.get("exact_worklist_event_count"), int)
                    and 0 <= packet_ledger.get("exact_worklist_event_count") <= expected_worklist_packets
                )
            )
        )
        checks.append(
            {
                "name": "diagnostic_native_lh2dt_packet_coverage",
                "status": "PASS" if ledger_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if ledger_valid
                    else "native lh2dt packet coverage ledger is missing, malformed, or contains a promoted claim"
                ),
                "evidence": {
                    "record": packet_ledger.get("_record_path"),
                    "status": packet_ledger.get("status"),
                    "packet_count": packet_ledger.get("packet_count"),
                    "exact_worklist_event_count": packet_ledger.get("exact_worklist_event_count"),
                    "expected_worklist_event_count": expected_worklist_packets,
                    "consequence_chain_event_count": packet_ledger.get("consequence_chain_event_count"),
                    "frequency_bound_event_count": packet_ledger.get("frequency_bound_event_count"),
                    "provider_packet_promoted_count": packet_ledger.get("provider_packet_promoted_count"),
                    "physical_validation_claim_count": packet_ledger.get("physical_validation_claim_count"),
                    "facility_qra_claim_count": packet_ledger.get("facility_qra_claim_count"),
                    "family_summary": packet_ledger.get("family_summary"),
                },
                "interpretation": (
                    "Saved native lh2dt packet outputs are indexed by equipment family and opening. "
                    "The ledger demonstrates diagnostic interface coverage only; it does not qualify "
                    "the provider, assign a facility frequency, or unlock facility IR/F-N."
                ),
            }
        )
    if native_packet_campaign_ledger is not None:
        packet_campaign = native_packet_campaign_ledger
        expected_worklist_events = (
            provider_worklist.get("generated_event_count")
            if isinstance(provider_worklist, Mapping)
            else None
        )
        event_count = packet_campaign.get("event_count")
        case_count = packet_campaign.get("case_count")
        chain_count = packet_campaign.get("chain_executed_case_count")
        failed_count = packet_campaign.get("failed_case_count")
        packet_identity_count = packet_campaign.get("packet_identity_case_count")
        packet_digest_count = packet_campaign.get("packet_digest_case_count")
        uncomputed_count = packet_campaign.get("uncomputed_case_count", 0)
        uncomputed_without_identity_count = packet_campaign.get(
            "uncomputed_without_packet_identity_case_count", 0
        )
        partial_packet_scope = (
            isinstance(packet_identity_count, int)
            and isinstance(packet_digest_count, int)
            and isinstance(uncomputed_count, int)
            and isinstance(uncomputed_without_identity_count, int)
            and packet_identity_count + uncomputed_without_identity_count == case_count
            and packet_digest_count == packet_identity_count
            and uncomputed_without_identity_count == uncomputed_count
        )
        campaign_valid = (
            packet_campaign.get("schema_version") == "prism.native_lh2dt_packet_campaign_execution.v1"
            and packet_campaign.get("status") == "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED"
            and isinstance(event_count, int)
            and event_count > 0
            and case_count == event_count
            and isinstance(chain_count, int)
            and isinstance(failed_count, int)
            and chain_count + failed_count + uncomputed_count == case_count
            and packet_campaign.get("packet_identity_consumed") is True
            and partial_packet_scope
            and isinstance(packet_campaign.get("failed_cases"), list)
            and len(packet_campaign.get("failed_cases")) == failed_count
            and packet_campaign.get("facility_total_risk_available") is False
            and packet_campaign.get("provider_packet_promoted") is False
            and packet_campaign.get("frequency_from_provider_packet") is False
            and packet_campaign.get("facility_qra_claim") is False
            and packet_campaign.get("physical_validation_claim") is False
            and isinstance(packet_campaign.get("policy"), Mapping)
            and packet_campaign["policy"].get("provider_packet_promoted") is False
            and packet_campaign["policy"].get("frequency_inference_performed") is False
            and packet_campaign["policy"].get("frequency_from_provider_packet") is False
            and packet_campaign["policy"].get("facility_qra_claim") is False
            and packet_campaign["policy"].get("physical_validation_claim") is False
            and (expected_worklist_events is None or event_count == expected_worklist_events)
        )
        checks.append(
            {
                "name": "diagnostic_native_packet_campaign_execution",
                "status": "PASS" if campaign_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if campaign_valid
                    else "native packet campaign ledger is missing, malformed, or hides a failed case"
                ),
                "evidence": {
                    "record": packet_campaign.get("_record_path"),
                    "status": packet_campaign.get("status"),
                    "event_count": event_count,
                    "expected_worklist_event_count": expected_worklist_events,
                    "case_count": case_count,
                    "chain_executed_case_count": chain_count,
                    "packet_identity_case_count": packet_campaign.get("packet_identity_case_count"),
                    "packet_digest_case_count": packet_campaign.get("packet_digest_case_count"),
                    "uncomputed_case_count": uncomputed_count,
                    "uncomputed_without_packet_identity_case_count": uncomputed_without_identity_count,
                    "packet_identity_consumed": packet_campaign.get("packet_identity_consumed"),
                    "operator_limited_case_count": packet_campaign.get("operator_limited_case_count"),
                    "failed_case_count": failed_count,
                    "failed_cases": packet_campaign.get("failed_cases"),
                    "risk_atom_count": packet_campaign.get("risk_atom_count"),
                    "facility_total_risk_available": packet_campaign.get("facility_total_risk_available"),
                    "facility_qra_claim": packet_campaign.get("facility_qra_claim"),
                },
                "interpretation": (
                    "The native packet identities were consumed by the facility campaign and every failed "
                    "case is preserved explicitly. This diagnostic result does not qualify the provider, "
                    "invent a frequency, or expose facility total IR/F-N."
                ),
            }
        )
        handoff = packet_campaign.get("compressible_handoff_rebind")
        if isinstance(handoff, Mapping):
            handoff_valid = (
                handoff.get("consumed") is True
                and isinstance(handoff.get("event_id"), str)
                and isinstance(handoff.get("original_provider_result_digest"), str)
                and isinstance(handoff.get("handoff_provider_result_digest"), str)
                and handoff.get("original_provider_result_digest") != handoff.get("handoff_provider_result_digest")
                and handoff.get("physical_validation_claim") is False
                and handoff.get("frequency_inference") is False
            )
            checks.append(
                {
                    "name": "diagnostic_native_packet_compressible_handoff_rebind",
                    "status": "PASS" if handoff_valid else "BLOCKED",
                    "diagnostic_only": True,
                    "blocking_reason": (
                        None
                        if handoff_valid
                        else "compressible handoff ledger is missing identity, digest, or non-promotion controls"
                    ),
                    "evidence": {
                        "record": packet_campaign.get("_record_path"),
                        "consumed": handoff.get("consumed"),
                        "event_id": handoff.get("event_id"),
                        "original_provider_result_digest": handoff.get("original_provider_result_digest"),
                        "handoff_provider_result_digest": handoff.get("handoff_provider_result_digest"),
                        "physical_validation_claim": handoff.get("physical_validation_claim"),
                        "frequency_inference": handoff.get("frequency_inference"),
                    },
                    "interpretation": (
                        "The campaign records an explicit same-source compressible-plane handoff rebind. "
                        "This confirms packet identity controls only; it does not validate the near field, "
                        "infer frequency, or promote facility QRA."
                    ),
                }
            )
    if native_full_bore_frequency_result is not None:
        full_bore_frequency_valid = (
            full_bore_frequency.get("schema_version") in {
                "prism.native_lh2dt_dynamic_pipe_full_bore_frequency_case.v1",
                "prism.native_lh2dt_dynamic_pipe_full_bore_facility_frequency_case.v1",
            }
            and full_bore_frequency.get("status") in {
                "END_TO_END_DIAGNOSTIC_EXECUTED",
                "PARTIAL_DECLARED_SCOPE",
            }
            and isinstance(event_id, str)
            and event_id.endswith("/AREA_100%")
            and frequency_event_id == event_id
            and full_bore_frequency.get("full_bore_match") is True
            and full_bore_frequency.get("provider_termination_basis") == "model_pressure_equalization"
            and full_bore_frequency.get("provider_pressure_equalized") is True
            and full_bore_frequency.get("provider_final_pressure_matches_ambient") is True
            and _finite(residual)
            and abs(float(residual)) <= 1e-8
            and _finite(full_bore_frequency.get("annual_frequency_per_year"))
            and float(full_bore_frequency.get("annual_frequency_per_year")) > 0
            and isinstance(full_bore_frequency.get("annual_frequency_provenance"), str)
            and full_bore_frequency.get("frequency_applied") is True
            and full_bore_frequency.get("frequency_exact_opening_match") is True
            and full_bore_frequency.get("consequence_chain_executed") is True
            and facility_campaign_valid
            and full_bore_frequency.get("facility_qra_claim") is False
            and full_bore_frequency.get("physical_validation_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_native_full_bore_frequency_binding",
                "status": "PASS" if full_bore_frequency_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if full_bore_frequency_valid
                    else "native full-bore literature-frequency binding evidence is missing or malformed"
                ),
                "evidence": {
                    "record": full_bore_frequency.get("_record_path"),
                    "status": full_bore_frequency.get("status"),
                    "event_id": event_id,
                    "frequency_event_id": frequency_event_id,
                    "full_bore_match": full_bore_frequency.get("full_bore_match"),
                    "termination_basis": full_bore_frequency.get("provider_termination_basis"),
                    "provider_duration_s": full_bore_frequency.get("provider_duration_s"),
                    "provider_pressure_equalized": full_bore_frequency.get("provider_pressure_equalized"),
                    "provider_final_pressure_matches_ambient": full_bore_frequency.get(
                        "provider_final_pressure_matches_ambient"
                    ),
                    "provider_mass_residual_kg": residual,
                    "annual_frequency_per_year": full_bore_frequency.get("annual_frequency_per_year"),
                    "annual_frequency_provenance": full_bore_frequency.get("annual_frequency_provenance"),
                    "frequency_applied": full_bore_frequency.get("frequency_applied"),
                    "frequency_exact_opening_match": full_bore_frequency.get(
                        "frequency_exact_opening_match"
                    ),
                    "consequence_chain_executed": full_bore_frequency.get("consequence_chain_executed"),
                    "facility_campaign_executed": full_bore_frequency.get("facility_campaign_executed"),
                    "facility_campaign_status": full_bore_frequency.get("facility_campaign_status"),
                    "facility_campaign_event_count": full_bore_frequency.get("facility_campaign_event_count"),
                    "facility_campaign_case_count": full_bore_frequency.get("facility_campaign_case_count"),
                    "facility_campaign_executed_case_count": full_bore_frequency.get(
                        "facility_campaign_executed_case_count"
                    ),
                    "facility_campaign_uncomputed_case_count": full_bore_frequency.get(
                        "facility_campaign_uncomputed_case_count"
                    ),
                    "facility_campaign_risk_atom_count": full_bore_frequency.get(
                        "facility_campaign_risk_atom_count"
                    ),
                    "facility_campaign_conditional_risk_available": full_bore_frequency.get(
                        "facility_campaign_conditional_risk_available"
                    ),
                    "facility_total_risk_available": full_bore_frequency.get(
                        "facility_total_risk_available"
                    ),
                    "facility_qra_claim": full_bore_frequency.get("facility_qra_claim"),
                    "physical_validation_claim": full_bore_frequency.get("physical_validation_claim"),
                },
                "interpretation": (
                    "The native finite full-bore provider packet is bound to the declared LH2_PIPE AREA_100% "
                    "literature event at one reviewed outlet and reaches the PRISM consequence chain. This "
                    "diagnostic evidence does not calibrate a site frequency, complete the facility event set, "
                    "or promote facility IR/F-N."
                ),
            }
        )
    if frequency_provenance_report is not None:
        provenance = frequency_provenance_report
        provenance_checks = provenance.get("checks")
        provenance_policy = provenance.get("policy")
        if not isinstance(provenance_policy, Mapping):
            provenance_policy = {}
        provenance_valid = (
            provenance.get("schema_version") == "prism.frequency_provenance.v1"
            and provenance.get("status") == "PASS_WITH_SCOPE_LIMITATIONS"
            and isinstance(provenance.get("generated_events"), list)
            and len(provenance.get("generated_events")) > 0
            and isinstance(provenance.get("profile_provenance"), list)
            and len(provenance.get("profile_provenance")) > 0
            and isinstance(provenance_checks, list)
            and len(provenance_checks) > 0
            and all(isinstance(row, Mapping) and row.get("passed") is True for row in provenance_checks)
            and provenance_policy.get("field_frequency_collection_used") is False
            and provenance_policy.get("sensor_frequency_learning_used") is False
            and provenance_policy.get("physical_validation_claim") is False
        )
        checks.append(
            {
                "name": "literature_frequency_provenance_evidence",
                "status": "PASS" if provenance_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None if provenance_valid else "literature frequency provenance report is missing or malformed",
                "evidence": {
                    "record": provenance.get("_record_path"),
                    "status": provenance.get("status"),
                    "profile_count": len(provenance.get("profile_provenance", []))
                    if isinstance(provenance.get("profile_provenance"), list) else None,
                    "event_count": len(provenance.get("generated_events", []))
                    if isinstance(provenance.get("generated_events"), list) else None,
                    "catalogue_digest": provenance.get("catalogue", {}).get("digest"),
                    "field_frequency_collection_used": provenance_policy.get("field_frequency_collection_used"),
                    "sensor_frequency_learning_used": provenance_policy.get("sensor_frequency_learning_used"),
                    "physical_validation_claim": provenance_policy.get("physical_validation_claim"),
                },
                "interpretation": (
                    "The selected literature frequency profiles and generated event rows have source "
                    "and catalogue digest provenance. This does not make the rates field-validated or "
                    "create a facility credible interval."
                ),
            }
        )
    if scenario_evidence_report is not None:
        scenario_evidence = scenario_evidence_report
        scenario_policy = scenario_evidence.get("policy")
        if not isinstance(scenario_policy, Mapping):
            scenario_policy = {}
        scenario_evidence_valid = (
            scenario_evidence.get("schema_version") == "prism.external_scenario_evidence.v1"
            and scenario_evidence.get("status") in {
                "SCREENING_EVIDENCE_IMPORTED",
                "PARTIAL_SCREENING_EVIDENCE",
            }
            and isinstance(scenario_evidence.get("source_files"), list)
            and len(scenario_evidence.get("source_files")) > 0
            and isinstance(scenario_evidence.get("records"), list)
            and len(scenario_evidence.get("records")) > 0
            and scenario_policy.get("facility_neutral") is True
            and scenario_policy.get("frequency_applied") is False
            and scenario_policy.get("sensor_frequency_learning_used") is False
            and scenario_policy.get("provider_packet_created") is False
            and scenario_policy.get("facility_qra_claim") is False
            and scenario_policy.get("candidate_family_map_is_not_a_frequency_map") is True
        )
        checks.append(
            {
                "name": "external_scenario_evidence_import",
                "status": "PASS" if scenario_evidence_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None if scenario_evidence_valid else "external scenario evidence report is missing or malformed",
                "evidence": {
                    "record": scenario_evidence.get("_record_path"),
                    "status": scenario_evidence.get("status"),
                    "source_file_count": scenario_evidence.get("source_file_count"),
                    "record_count": len(scenario_evidence.get("records", []))
                    if isinstance(scenario_evidence.get("records"), list) else None,
                    "scope_status_counts": scenario_evidence.get("summary", {}).get("scope_status_counts"),
                    "frequency_applied": scenario_policy.get("frequency_applied"),
                    "sensor_frequency_learning_used": scenario_policy.get("sensor_frequency_learning_used"),
                    "provider_packet_created": scenario_policy.get("provider_packet_created"),
                    "facility_qra_claim": scenario_policy.get("facility_qra_claim"),
                },
                "interpretation": (
                    "External procedure and failure tables are retained as facility-neutral screening "
                    "evidence. Candidate families and monitoring tags do not create a frequency, "
                    "provider release packet or facility IR/F-N result."
                ),
            }
        )
    worklist_alignment = scope_matrix.get("provider_worklist_alignment")
    if isinstance(worklist_alignment, Mapping):
        alignment_valid = (
            worklist_alignment.get("status") == "ALIGNED"
            and isinstance(worklist_alignment.get("worklist_event_count"), int)
            and worklist_alignment.get("worklist_event_count") > 0
            and worklist_alignment.get("aligned_event_count")
            == worklist_alignment.get("worklist_event_count")
            and worklist_alignment.get("provider_packet_created") is False
            and worklist_alignment.get("frequency_inference_performed") is False
        )
        checks.append(
            {
                "name": "provider_worklist_scope_alignment",
                "status": "PASS" if alignment_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "status": worklist_alignment.get("status"),
                    "worklist_event_count": worklist_alignment.get(
                        "worklist_event_count"
                    ),
                    "campaign_event_count": worklist_alignment.get(
                        "campaign_event_count"
                    ),
                    "aligned_event_count": worklist_alignment.get(
                        "aligned_event_count"
                    ),
                    "missing_event_ids": worklist_alignment.get("missing_event_ids"),
                    "primary_family_mismatches": worklist_alignment.get(
                        "primary_family_mismatches"
                    ),
                    "provider_packet_created": worklist_alignment.get(
                        "provider_packet_created"
                    ),
                    "frequency_inference_performed": worklist_alignment.get(
                        "frequency_inference_performed"
                    ),
                },
                "interpretation": (
                    "The provider worklist and campaign share event IDs and primary accident "
                    "families. This is a structural diagnostic check; it does not create a "
                    "provider packet or qualify facility risk."
                ),
            }
        )
    if registry is not None:
        checks.append(
            _check(
                "diagnostic_adapter_execution_contract",
                bool(registry_complete),
                {
                    "source": "diagnostic_adapter_registry" if diagnostic_adapter_registry is not None else "current_status",
                    "status": registry.get("status"),
                    "adapter_count": registry.get("adapter_count"),
                    "resolved_adapter_count": registry.get("resolved_adapter_count"),
                    "provider_instance_count": registry.get("provider_instance_count"),
                    "qualified_provider_packet_count": registry.get("qualified_provider_packet_count"),
                    "record": registry.get("record"),
                },
                "the declared diagnostic adapter registry is not fully resolved",
            )
        )
    if diagnostic_adapter_execution is not None:
        execution = diagnostic_adapter_execution
        adapter_execution = execution.get("adapter_execution")
        exact_match = execution.get("worklist_exact_match")
        exact_match_fields = ("event_id", "component_id", "port_id", "opening_diameter_m")
        exact_match_complete = (
            isinstance(exact_match, Mapping)
            and all(exact_match.get(field) is True for field in exact_match_fields)
        )
        execution_valid = (
            isinstance(execution.get("status"), str)
            and execution.get("status", "").startswith("EXECUTED")
            and isinstance(adapter_execution, Mapping)
            and isinstance(execution.get("worklist_item_id"), str)
            and bool(execution.get("worklist_item_id"))
            and exact_match_complete
            and execution.get("consequence_chain_executed") is True
            and isinstance(execution.get("consequence_chain_status"), str)
            and execution.get("consequence_chain_status", "").startswith("END_TO_END")
            and execution.get("qualified_provider_packet_count") == 0
            and execution.get("provider_packet_promoted") is False
            and execution.get("worklist_frequency_bound") is False
            and execution.get("consequence_context_frequency_bound") is False
            and execution.get("frequency_inference_performed") is False
            and execution.get("facility_qra_claim") is False
            and execution.get("physical_validation_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_worklist_execution_evidence",
                "status": "PASS" if execution_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": execution.get("_record_path"),
                    "status": execution.get("status"),
                    "worklist_item_id": execution.get("worklist_item_id"),
                    "provider_instance_id": adapter_execution.get("provider_instance_id")
                    if isinstance(adapter_execution, Mapping)
                    else None,
                    "worklist_exact_match": exact_match,
                    "consequence_chain_executed": execution.get("consequence_chain_executed"),
                    "consequence_chain_status": execution.get("consequence_chain_status"),
                    "consequence_chain_elapsed_ms": execution.get("consequence_chain_elapsed_ms"),
                    "fresh_adapter_execution_elapsed_ms": execution.get("fresh_execution_elapsed_ms"),
                    "qualified_provider_packet_count": execution.get(
                        "qualified_provider_packet_count"
                    ),
                    "provider_packet_promoted": execution.get("provider_packet_promoted"),
                    "worklist_frequency_bound": execution.get("worklist_frequency_bound"),
                    "consequence_context_frequency_bound": execution.get(
                        "consequence_context_frequency_bound"
                    ),
                    "frequency_inference_performed": execution.get("frequency_inference_performed"),
                    "facility_qra_claim": execution.get("facility_qra_claim"),
                    "physical_validation_claim": execution.get("physical_validation_claim"),
                },
                "interpretation": (
                    "A worklist item reached the diagnostic provider and consequence-chain boundary; "
                    "this evidence is intentionally non-qualifying and does not satisfy the provider, "
                    "frequency, facility-QRA, or physical-validation gates."
                ),
            }
        )
    if diagnostic_worklist_evidence is not None:
        evidence = diagnostic_worklist_evidence
        worklist_count = evidence.get("worklist_event_count")
        candidate_count = evidence.get("candidate_event_count")
        exact_count = evidence.get("exact_match_event_count")
        strict_count = evidence.get("strict_packet_valid_event_count")
        chain_count = evidence.get("consequence_chain_event_count")
        coverage_valid = (
            isinstance(evidence.get("status"), str)
            and evidence.get("status", "").startswith("PARTIAL_DIAGNOSTIC_EVIDENCE")
            and isinstance(worklist_count, int)
            and worklist_count > 0
            and isinstance(candidate_count, int)
            and isinstance(exact_count, int)
            and isinstance(strict_count, int)
            and isinstance(chain_count, int)
            and 0 < exact_count == strict_count <= candidate_count <= worklist_count
            and chain_count > 0
            and evidence.get("qualified_provider_packet_count") == 0
            and evidence.get("frequency_bound") is False
            and evidence.get("facility_qra_claim") is False
            and evidence.get("physical_validation_claim") is False
        )
        structural_worklist_coverage = bool(
            coverage_valid
            and exact_count == worklist_count
            and strict_count == worklist_count
        ) or structural_worklist_coverage
        checks.append(
            {
                "name": "diagnostic_worklist_packet_coverage_evidence",
                "status": "PASS" if coverage_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": evidence.get("_record_path"),
                    "status": evidence.get("status"),
                    "worklist_event_count": worklist_count,
                    "candidate_event_count": candidate_count,
                    "exact_match_event_count": exact_count,
                    "strict_packet_valid_event_count": strict_count,
                    "consequence_chain_event_count": chain_count,
                    "qualified_provider_packet_count": evidence.get(
                        "qualified_provider_packet_count"
                    ),
                    "frequency_bound": evidence.get("frequency_bound"),
                    "facility_qra_claim": evidence.get("facility_qra_claim"),
                    "physical_validation_claim": evidence.get("physical_validation_claim"),
                    "qualification_readiness": evidence.get("qualification_readiness"),
                },
                "interpretation": (
                    "Saved external-model packets cover only the exact-matched worklist subset; "
                    "this diagnostic evidence does not close the missing events or qualify the "
                    "provider packets. Qualification-readiness blockers are copied separately so "
                    "exact packet identity is not mistaken for actual facility evidence."
                ),
            }
        )
    if diagnostic_campaign_binding is not None:
        binding = diagnostic_campaign_binding
        packet_count = binding.get("packet_event_count")
        event_match_count = binding.get("packet_event_to_campaign_event_match_count")
        case_match_count = binding.get("packet_event_to_campaign_case_match_count")
        atom_match_count = binding.get("packet_event_to_campaign_risk_atom_match_count")
        packet_subset_binding_valid = (
            isinstance(binding.get("status"), str)
            and binding.get("status", "").startswith("PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING")
            and isinstance(packet_count, int)
            and packet_count > 0
            and event_match_count == packet_count
            and case_match_count == packet_count
            and atom_match_count == packet_count
            and binding.get("structural_binding_complete") is True
            and isinstance(binding.get("packet_identity_consumed"), bool)
            and binding.get("frequency_from_provider_packet") is False
            and binding.get("packet_claims_preserved") is True
        )
        # The generic provider worklist and the vertical-handoff adapter are
        # intentionally maintained as separate evidence classes.  A partial
        # packet-to-campaign binding therefore does not mean that a declared
        # event is missing when the combined chain audit proves that the
        # packet subset plus the handoff subset cover the exact campaign event
        # count.  This branch changes only the diagnostic closure label; it
        # never qualifies a provider packet or opens facility IR/F-N.
        combined = combined_chain_closure if isinstance(combined_chain_closure, Mapping) else None
        union_chain_closure_valid = (
            not packet_subset_binding_valid
            and isinstance(combined, Mapping)
            and combined.get("schema_version") == "prism.facility_combined_chain_closure_audit.v1"
            and combined.get("status") == "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED"
            and combined.get("event_count_matches_declared_scope") is True
            and combined.get("mismatch_event_ids") == []
            and combined.get("combined_diagnostic_closed_event_count")
            == combined.get("declared_event_count")
            and isinstance(binding.get("campaign_event_count"), int)
            and binding.get("campaign_event_count") == combined.get("declared_event_count")
            and binding.get("packet_event_count") == combined.get("packet_subset_event_count")
            and binding.get("packet_subset_identity_consumed") is True
            and binding.get("frequency_from_provider_packet") is False
            and binding.get("packet_claims_preserved") is True
        )
        campaign_binding_valid = packet_subset_binding_valid or union_chain_closure_valid
        checks.append(
            {
                "name": "diagnostic_worklist_campaign_binding_evidence",
                "status": "PASS" if campaign_binding_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": binding.get("_record_path"),
                    "status": binding.get("status"),
                    "packet_event_count": packet_count,
                    "campaign_event_count": binding.get("campaign_event_count"),
                    "campaign_case_count": binding.get("campaign_case_count"),
                    "campaign_risk_atom_count": binding.get("campaign_risk_atom_count"),
                    "packet_event_to_campaign_event_match_count": event_match_count,
                    "packet_event_to_campaign_case_match_count": case_match_count,
                    "packet_event_to_campaign_risk_atom_match_count": atom_match_count,
                    "structural_binding_complete": binding.get("structural_binding_complete"),
                    "packet_scope_subset_complete": binding.get("packet_scope_subset_complete"),
                    "campaign_scope_packet_coverage_complete": binding.get(
                        "campaign_scope_packet_coverage_complete"
                    ),
                    "unbound_campaign_event_count": binding.get("unbound_campaign_event_count"),
                    "unbound_campaign_event_ids": binding.get("unbound_campaign_event_ids"),
                    "packet_event_coverage_ratio": binding.get("packet_event_coverage_ratio"),
                    "packet_case_coverage_ratio": binding.get("packet_case_coverage_ratio"),
                    "packet_risk_atom_event_coverage_ratio": binding.get(
                        "packet_risk_atom_event_coverage_ratio"
                    ),
                    "packet_identity_consumed": binding.get("packet_identity_consumed"),
                    "packet_subset_identity_consumed": binding.get(
                        "packet_subset_identity_consumed"
                    ),
                    "packet_subset_binding_valid": packet_subset_binding_valid,
                    "union_chain_closure_used": union_chain_closure_valid,
                    "union_chain_closure_status": (
                        combined.get("status") if isinstance(combined, Mapping) else None
                    ),
                    "union_chain_closure_record": (
                        combined.get("_record_path") if isinstance(combined, Mapping) else None
                    ),
                    "diagnostic_scope_closure_complete": union_chain_closure_valid,
                    "packet_digest_checked_event_count": binding.get(
                        "packet_digest_checked_event_count"
                    ),
                    "packet_digest_match_event_count": binding.get(
                        "packet_digest_match_event_count"
                    ),
                    "frequency_from_provider_packet": binding.get("frequency_from_provider_packet"),
                    "packet_claims_preserved": binding.get("packet_claims_preserved"),
                    "executed_case_count": binding.get("executed_case_count"),
                    "campaign_provider_identity_case_count": binding.get(
                        "campaign_provider_identity_case_count"
                    ),
                    "campaign_provider_identity_recorded": binding.get(
                        "campaign_provider_identity_recorded"
                    ),
                },
                "interpretation": (
                    "Provider worklist event IDs structurally reach campaign events, cases, and risk atoms. "
                    "When the combined packet/vertical chain audit closes the same declared event set, "
                    "the diagnostic scope is considered connected even though the evidence classes remain "
                    "separate. This does not qualify packets, assign frequency, or promote facility risk."
                    if union_chain_closure_valid
                    else
                    "Provider worklist event IDs structurally reach campaign events, cases, and risk atoms. "
                    "The matched packet subset may have exact digest consumption, but any campaign-only "
                    "events keep the full facility binding gate blocked; the result stays diagnostic-only."
                ),
            }
        )
    if facility_assessment is not None:
        assessment = facility_assessment
        # Keep a separate diagnostic-only trace check for the numerical
        # release-to-consequence handoff. The strict gate below intentionally
        # rejects operator-limited/synthetic cases, but that must not hide
        # whether every declared case carried a release branch, duration,
        # termination provenance, and mass ledger into the facility assessment.
        # This check proves structural connection only; it never qualifies a
        # provider packet or opens facility IR/F-N.
        raw_release_trace = assessment.get("release_termination_inventory_ledger")
        trace_rows = (
            raw_release_trace.get("rows")
            if isinstance(raw_release_trace, Mapping)
            else None
        )
        trace_rows = (
            trace_rows
            if isinstance(trace_rows, Sequence)
            and not isinstance(trace_rows, (str, bytes))
            else []
        )
        diagnostic_termination_bases = {
            "reviewed_isolation_success",
            "inventory_depletion",
            "inventory_over_600s",
            "synthetic_diagnostic_horizon",
            "emergency_relief_discharge",
            "two_sided_rupture",
        }
        trace_failures: list[str] = []
        trace_status_counts: dict[str, int] = {}
        trace_basis_counts: dict[str, int] = {}
        for index, row in enumerate(trace_rows):
            label = (
                str(
                    row.get("event_id")
                    or row.get("release_branch_id")
                    or f"row-{index + 1}"
                )
                if isinstance(row, Mapping)
                else f"row-{index + 1}"
            )
            if not isinstance(row, Mapping):
                trace_failures.append(f"{label}: row is not an object")
                continue
            status = row.get("status")
            trace_status_counts[str(status)] = trace_status_counts.get(str(status), 0) + 1
            termination = row.get("termination")
            termination = termination if isinstance(termination, Mapping) else {}
            basis = termination.get("basis")
            if isinstance(basis, str):
                trace_basis_counts[basis] = trace_basis_counts.get(basis, 0) + 1
            required_fields = (
                ("event_id", row.get("event_id")),
                ("asset_id", row.get("asset_id")),
                ("release_branch_id", row.get("release_branch_id")),
                ("annual_condition_id", row.get("annual_condition_id")),
                ("termination.basis", basis),
                ("termination.provenance", termination.get("provenance")),
            )
            for field, value in required_fields:
                if not isinstance(value, str) or not value.strip():
                    trace_failures.append(f"{label}: missing {field}")
            if basis not in diagnostic_termination_bases:
                trace_failures.append(f"{label}: unsupported diagnostic termination basis")
            duration = termination.get("time_s")
            if not _finite(duration) or float(duration) < 0.0:
                trace_failures.append(f"{label}: missing finite nonnegative duration")
            mass = row.get("mass_ledger")
            mass = mass if isinstance(mass, Mapping) else {}
            if not _finite(mass.get("released_kg")) or not _finite(
                mass.get("end_to_end_residual_kg")
            ):
                trace_failures.append(f"{label}: incomplete mass ledger")
        trace_summary = (
            raw_release_trace.get("summary")
            if isinstance(raw_release_trace, Mapping)
            else {}
        )
        trace_summary = trace_summary if isinstance(trace_summary, Mapping) else {}
        trace_expected_case_count = trace_summary.get("case_count")
        trace_count_matches = (
            isinstance(trace_expected_case_count, int)
            and trace_expected_case_count > 0
            and len(trace_rows) == trace_expected_case_count
        )
        diagnostic_trace_valid = bool(trace_rows) and trace_count_matches and not trace_failures
        if isinstance(raw_release_trace, Mapping) and "rows" in raw_release_trace:
            checks.append(
                {
                "name": "diagnostic_release_trace_coverage",
                "status": "PASS" if diagnostic_trace_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if diagnostic_trace_valid
                    else "one or more declared cases lacks a complete diagnostic release trace"
                ),
                "evidence": {
                    "record": assessment.get("_record_path"),
                    "release_ledger_schema": (
                        raw_release_trace.get("schema_version")
                        if isinstance(raw_release_trace, Mapping)
                        else None
                    ),
                    "trace_row_count": len(trace_rows),
                    "expected_case_count": trace_expected_case_count,
                    "trace_count_matches": trace_count_matches,
                    "status_counts": trace_status_counts,
                    "termination_basis_counts": trace_basis_counts,
                    "trace_failure_count": len(trace_failures),
                    "trace_failures": trace_failures[:20],
                    "strict_release_boundary_ready": (
                        assessment.get("strict_release_boundary", {}).get(
                            "strict_release_boundary_ready"
                        )
                        if isinstance(assessment.get("strict_release_boundary"), Mapping)
                        else None
                    ),
                    "provider_qualification_claim": False,
                    "facility_ir_fn_promotion": False,
                },
                "interpretation": (
                    "Every declared numerical case has an explicit release branch, duration, "
                    "termination basis/provenance and mass ledger in the diagnostic chain. "
                    "Synthetic, operator-limited and horizon rows remain non-qualified and "
                    "do not promote facility IR/F-N."
                ),
                }
            )
        coverage = assessment.get("conditional_diagnostic_facility_coverage")
        conditional_ir = assessment.get("conditional_diagnostic_facility_annual_ir_low_high")
        conditional_fn = assessment.get(
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        )
        diagnostic_facility_valid = (
            assessment.get("conditional_diagnostic_facility_risk_available") is True
            and isinstance(conditional_ir, Mapping)
            and bool(conditional_ir)
            and isinstance(conditional_fn, list)
            and len(conditional_fn) == 2
            and isinstance(coverage, Mapping)
            and isinstance(coverage.get("event_count"), int)
            and coverage.get("event_count") > 0
            and isinstance(coverage.get("case_count"), int)
            and coverage.get("case_count") > 0
            and isinstance(coverage.get("risk_atom_count"), int)
            and coverage.get("risk_atom_count") > 0
            and assessment.get("facility_total_risk_available") is False
            and assessment.get("complete_facility_qra_claim") is not True
        )
        checks.append(
            {
                "name": "diagnostic_conditional_facility_risk_evidence",
                "status": "PASS" if diagnostic_facility_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": assessment.get("_record_path"),
                    "status": assessment.get("status"),
                    "conditional_diagnostic_facility_risk_available": assessment.get(
                        "conditional_diagnostic_facility_risk_available"
                    ),
                    "conditional_diagnostic_facility_annual_ir_low_high": conditional_ir,
                    "conditional_diagnostic_facility_expected_death_fn_low_high": conditional_fn,
                    "conditional_diagnostic_facility_expected_death_fn_diagnostics": assessment.get(
                        "conditional_diagnostic_facility_expected_death_fn_diagnostics"
                    ),
                    "population_accounting": assessment.get("population_accounting"),
                    "scenario_branch_accounting": assessment.get("scenario_branch_accounting"),
                    "release_termination_inventory_ledger": assessment.get(
                        "release_termination_inventory_ledger"
                    ),
                    "timing": assessment.get("timing"),
                    "coverage": coverage,
                    "facility_total_risk_available": assessment.get(
                        "facility_total_risk_available"
                    ),
                    "complete_facility_qra_claim": assessment.get(
                        "complete_facility_qra_claim"
                    ),
                },
                "interpretation": (
                    "The facility IR/F-N aggregation is present as a conditional diagnostic view "
                    "over the saved risk atoms; withheld total-facility qualification and the "
                    "remaining scope, provider, frequency, and validation gates are preserved."
                ),
            }
        )
        # The final assessment must retain the same reviewed accident-port
        # identity that entered the frequency and provider ledgers.  This is
        # diagnostic evidence only: the strict facility-QRA gates remain
        # independent, but a stale/missing port trace must be visible in the
        # completion report rather than silently disappearing in nesting.
        port_binding = assessment.get("frequency_port_binding")
        port_binding_source = "facility_assessment"
        if not isinstance(port_binding, Mapping) and isinstance(facility_evidence_request, Mapping):
            request_port_binding = facility_evidence_request.get("frequency_port_binding")
            if isinstance(request_port_binding, Mapping):
                port_binding = request_port_binding
                port_binding_source = "facility_evidence_request"
        nested_ledger = assessment.get("facility_risk_ledger")
        nested_port_binding = (
            nested_ledger.get("frequency_port_binding")
            if isinstance(nested_ledger, Mapping)
            else None
        )
        port_binding_aligned = (
            isinstance(port_binding, Mapping)
            and port_binding.get("schema_version") == "prism.frequency_port_binding.v1"
            and port_binding.get("status") == "ALIGNED"
            and port_binding.get("mismatch_count") == 0
            and port_binding.get("port_unbound_event_count") == 0
            and port_binding.get("frequency_inference_allowed") is False
            and (
                nested_port_binding is None
                or nested_port_binding == port_binding
            )
        )
        port_binding_withheld = (
            isinstance(port_binding, Mapping)
            and port_binding.get("schema_version") == "prism.frequency_port_binding.v1"
            and port_binding.get("status") == "PORT_BINDING_WITHHELD"
            and isinstance(port_binding.get("case_count"), int)
            and port_binding.get("case_count", 0) > 0
            and isinstance(port_binding.get("reviewed_frequency_port_case_count"), int)
            and port_binding.get("reviewed_frequency_ports_complete") is False
            and port_binding.get("frequency_inference_allowed") is False
            and port_binding.get("facility_qra_allowed") is False
        )
        port_binding_valid = port_binding_aligned or port_binding_withheld
        checks.append(
            {
                "name": "diagnostic_facility_frequency_port_binding",
                "status": "PASS" if port_binding_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": assessment.get("_record_path"),
                    "source": port_binding_source,
                    "trace_status": (
                        "ALIGNED"
                        if port_binding_aligned
                        else "WITHHELD_REVIEW_REQUIRED"
                        if port_binding_withheld
                        else None
                    ),
                    "frequency_port_binding": port_binding,
                    "nested_ledger_frequency_port_binding": nested_port_binding,
                },
                "interpretation": (
                    "The reviewed accident-port list remains aligned from the public facility "
                    "assessment to the merged ledger."
                    if port_binding_aligned
                    else
                    "The evidence-request catalog explicitly records that reviewed frequency "
                    "ports are still withheld; provider outlet ports are not substituted for "
                    "frequency ports, and no facility QRA is opened."
                ),
            }
        )
        # The facility assessment owns the authoritative release-boundary
        # gate.  Keep this as a separate strict check so a conditional
        # consequence chain cannot be mistaken for a closed facility release
        # ledger.  Older assessments may not carry the new gate yet; in that
        # case the historical audit shape is preserved and the caller can
        # regenerate the assessment before relying on this check.
        release_boundary = assessment.get("strict_release_boundary")
        if isinstance(release_boundary, Mapping):
            # ``evaluate_facility_release_boundary`` publishes the gate as
            # ``schema_version``/``checks``/``policy``.  Accept the older
            # aliases too because saved diagnostic assessments may still use
            # them, but always expose the normalized values in the audit.
            gate_schema = release_boundary.get("schema") or release_boundary.get(
                "schema_version"
            )
            gate_checks = release_boundary.get("facility_gate_checks")
            if not isinstance(gate_checks, Mapping):
                gate_checks = release_boundary.get("checks")
            gate_checks = gate_checks if isinstance(gate_checks, Mapping) else {}
            promotion_policy = release_boundary.get("promotion_policy")
            if not isinstance(promotion_policy, Mapping):
                promotion_policy = release_boundary.get("policy")
            gate_ready = release_boundary.get("strict_release_boundary_ready") is True
            required_gate_checks = {
                "all_rows_complete",
                "all_termination_bases_allowed",
                "all_isolation_or_inventory_statuses_closed",
                "all_mass_residuals_closed",
                "no_withheld_cases",
            }
            # When the assessment carries the raw release ledger, recompute
            # the gate from those rows and compare the published summary.  A
            # stale or hand-edited assessment must not silently become the
            # authoritative strict result.  Older diagnostic fixtures may
            # contain only the summarized gate; those remain auditable with an
            # explicit NOT_PROVIDED reconciliation state.
            raw_release_ledger = assessment.get("release_termination_inventory_ledger")
            reconciliation: dict[str, Any] = {"status": "NOT_PROVIDED"}
            reconciliation_blocked = False
            raw_rows = raw_release_ledger.get("rows") if isinstance(raw_release_ledger, Mapping) else None
            if (
                isinstance(raw_release_ledger, Mapping)
                and isinstance(raw_rows, Sequence)
                and not isinstance(raw_rows, (str, bytes))
            ):
                try:
                    recomputed_gate = evaluate_facility_release_boundary(raw_release_ledger)
                except (TypeError, ValueError) as error:
                    reconciliation = {
                        "status": "INVALID_RAW_LEDGER",
                        "error": str(error),
                    }
                    reconciliation_blocked = True
                else:
                    declared_projection = {
                        "schema_version": gate_schema,
                        "strict_release_boundary_ready": gate_ready,
                        "case_count": release_boundary.get("case_count"),
                        "withheld_case_count": release_boundary.get("withheld_case_count"),
                        "checks": dict(gate_checks),
                        "blocking_reasons": list(
                            release_boundary.get("blocking_reasons", [])
                        ),
                        "residual_tolerance_kg": release_boundary.get(
                            "residual_tolerance_kg"
                        ),
                    }
                    recomputed_projection = {
                        key: recomputed_gate.get(key)
                        for key in declared_projection
                    }
                    mismatches = [
                        key
                        for key in declared_projection
                        if declared_projection[key] != recomputed_projection[key]
                    ]
                    reconciliation = {
                        "status": "MATCHED" if not mismatches else "MISMATCHED",
                        "compared_fields": list(declared_projection),
                        "mismatched_fields": mismatches,
                        "recomputed_schema_version": recomputed_gate.get("schema_version"),
                        "recomputed_case_count": recomputed_gate.get("case_count"),
                        "recomputed_withheld_case_count": recomputed_gate.get(
                            "withheld_case_count"
                        ),
                        "recomputed_checks": recomputed_gate.get("checks"),
                        "recomputed_blocking_reasons": recomputed_gate.get(
                            "blocking_reasons", []
                        ),
                    }
                    reconciliation_blocked = bool(mismatches)
            gate_valid = (
                gate_schema == "prism.facility_release_boundary_gate.v1"
                and gate_ready
                and not release_boundary.get("blocking_reasons")
                and required_gate_checks.issubset(gate_checks)
                and all(value is True for value in gate_checks.values())
                and not reconciliation_blocked
            )
            checks.append(
                {
                    "name": "facility_release_boundary",
                    "status": "PASS" if gate_valid else "BLOCKED",
                    "diagnostic_only": False,
                    "blocking_reason": (
                        None
                        if gate_valid
                        else "facility release boundary is not closed across all declared cases"
                    ),
                    "evidence": {
                        "record": assessment.get("_record_path"),
                        "schema": gate_schema,
                        "schema_version": release_boundary.get("schema_version"),
                        "strict_release_boundary_ready": release_boundary.get(
                            "strict_release_boundary_ready"
                        ),
                        "case_count": release_boundary.get("case_count"),
                        "facility_gate_checks": dict(gate_checks),
                        "blocking_reasons": release_boundary.get("blocking_reasons", []),
                        "promotion_policy": promotion_policy,
                        "raw_ledger_reconciliation": reconciliation,
                    },
                    "interpretation": (
                        "Every declared case must have an allowed provider-owned termination "
                        "basis and a closed mass/inventory ledger before the facility chain can "
                        "be promoted. This gate does not assign frequency or validate physics."
                    ),
                }
            )
    if uncertainty is not None:
        scenarios = uncertainty.get("scenarios")
        valid_scenarios = [
            row
            for row in scenarios
            if isinstance(row, Mapping)
            and isinstance(row.get("scenario"), Mapping)
            and isinstance(row.get("conditional_diagnostic_facility_annual_ir_low_high"), Mapping)
            and bool(row.get("conditional_diagnostic_facility_annual_ir_low_high"))
            and isinstance(row.get("conditional_diagnostic_facility_expected_death_fn_low_high"), list)
            and len(row.get("conditional_diagnostic_facility_expected_death_fn_low_high")) == 2
            and isinstance(row.get("asset_rank_by_known_expected_fatalities_low_high"), list)
            and len(row.get("asset_rank_by_known_expected_fatalities_low_high")) == 2
        ] if isinstance(scenarios, list) else []
        diagnostic_frequency_valid = (
            isinstance(scenarios, list)
            and len(valid_scenarios) == len(scenarios)
            and len(scenarios) > 0
            and uncertainty.get("conditional_diagnostic_facility_risk")
            and uncertainty.get("facility_credible_interval") is False
            and uncertainty.get("physical_validation_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_frequency_uncertainty_evidence",
                "status": "PASS" if diagnostic_frequency_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "scenario_count": len(scenarios) if isinstance(scenarios, list) else 0,
                    "valid_scenario_count": len(valid_scenarios),
                    "facility_credible_interval": uncertainty.get("facility_credible_interval"),
                    "fresh_physics_executed": uncertainty.get("fresh_physics_executed"),
                    "correlation_comparison_present": uncertainty.get(
                        "correlation_comparison_present"
                    ),
                    "conditional_diagnostic_facility_risk": uncertainty.get(
                        "conditional_diagnostic_facility_risk"
                    ),
                },
                "interpretation": (
                    "Published frequency scenarios are re-applied to saved diagnostic risk atoms "
                    "and asset rankings; this does not create a complete-facility confidence interval "
                    "or claim fresh-physics validation."
                ),
            }
        )
    if vertical_handoff_result is not None:
        vertical = vertical_handoff_result
        # ``vertical_handoff_chain_audit`` is the canonical current schema.
        # Older diagnostic records used generated/executed/provider flags;
        # normalize both shapes without inventing a provider packet.
        vertical_event_count = vertical.get("generated_events")
        if not isinstance(vertical_event_count, int):
            vertical_event_count = vertical.get("vertical_event_count")
        vertical_case_count = vertical.get("executed_cases")
        if not isinstance(vertical_case_count, int):
            vertical_case_count = vertical.get("vertical_case_count")
        vertical_handoff_consumed = vertical.get("provider_vertical_handoff_consumed")
        if not isinstance(vertical_handoff_consumed, bool):
            vertical_handoff_consumed = (
                isinstance(vertical.get("vertical_handoff_state_history_event_count"), int)
                and vertical.get("vertical_event_count") == vertical.get(
                    "vertical_handoff_state_history_event_count"
                )
                and vertical.get("vertical_event_count", 0) > 0
            )
        vertical_operator_limited = vertical.get("operator_limited")
        if not isinstance(vertical_operator_limited, bool):
            vertical_operator_limited = (
                vertical.get("status") == "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED"
                and vertical.get("qualified_provider_packet_count") == 0
                and vertical.get("provider_packet_qualification_claim") is False
            )
        vertical_facility_withheld = vertical.get("facility_total_risk_withheld")
        if not isinstance(vertical_facility_withheld, bool):
            vertical_facility_withheld = (
                vertical.get("facility_qra_claim") is False
                and vertical.get("facility_total_risk_available") is not True
            )
        vertical_valid = (
            isinstance(vertical.get("status"), str)
            and (
                vertical.get("status", "").startswith("PARTIAL_DECLARED_SCOPE")
                or vertical.get("status") == "VERTICAL_OPERATOR_LIMITED_CHAIN_CLOSED"
            )
            and vertical_event_count == 5
            and isinstance(vertical_case_count, int)
            and vertical_case_count > 0
            and vertical_handoff_consumed is True
            and vertical_operator_limited is True
            and vertical_facility_withheld is True
            and vertical.get("physical_validation_claim") is False
        )
        scope_rows = scope_matrix.get("rows", [])
        merged_vertical_handoff = (
            any(
                isinstance(row, Mapping)
                and row.get("family") == "vertical_handoff"
                and int(row.get("generated_event_count", 0) or 0) > 0
                for row in scope_rows
            )
            if isinstance(scope_rows, list)
            else False
        )
        vertical_interpretation = (
            "The vertical-to-horizontal provider handoff diagnostic consumed a declared "
            "handoff boundary and is represented in the merged facility scope matrix; it "
            "remains synthetic/operator-limited and is not promoted to a qualified vertical "
            "accident family."
            if merged_vertical_handoff
            else
            "A separate vertical-to-horizontal provider handoff diagnostic consumed a "
            "declared handoff boundary; it is not merged into the generic facility scope "
            "or promoted to a qualified vertical accident family."
        )
        checks.append(
            {
                "name": "diagnostic_vertical_handoff_evidence",
                "status": "PASS" if vertical_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": vertical.get("_record_path"),
                    "status": vertical.get("status"),
                    "generated_events": vertical_event_count,
                    "executed_cases": vertical_case_count,
                    "provider_vertical_handoff_consumed": vertical_handoff_consumed,
                    "operator_limited": vertical_operator_limited,
                    "facility_total_risk_withheld": vertical_facility_withheld,
                    "physical_validation_claim": vertical.get("physical_validation_claim"),
                },
                "interpretation": vertical_interpretation,
            }
        )
    if combined_chain_closure is not None:
        combined = combined_chain_closure
        mismatch_ids = combined.get("mismatch_event_ids")
        combined_valid = (
            combined.get("schema_version")
            == "prism.facility_combined_chain_closure_audit.v1"
            and combined.get("status")
            == "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED"
            and isinstance(combined.get("declared_event_count"), int)
            and combined.get("declared_event_count", 0) > 0
            and combined.get("combined_diagnostic_closed_event_count")
            == combined.get("declared_event_count")
            and combined.get("packet_subset_closed_event_count", 0)
            + combined.get("vertical_handoff_closed_event_count", 0)
            == combined.get("combined_diagnostic_closed_event_count")
            and combined.get("event_count_matches_declared_scope") is True
            and isinstance(mismatch_ids, list)
            and not mismatch_ids
            and combined.get("facility_ir_aggregate_closed") is True
            and combined.get("facility_fn_aggregate_closed") is True
            and combined.get("qualified_provider_packet_count") == 0
            and combined.get("frequency_from_provider_packet") is False
            and combined.get("physical_validation_claim") is False
            and combined.get("facility_total_risk_available") is False
            and combined.get("complete_facility_qra_claim") is False
            and combined.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_combined_chain_closure",
                "status": "PASS" if combined_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": combined.get("_record_path"),
                    "schema_version": combined.get("schema_version"),
                    "status": combined.get("status"),
                    "declared_event_count": combined.get("declared_event_count"),
                    "packet_subset_closed_event_count": combined.get(
                        "packet_subset_closed_event_count"
                    ),
                    "vertical_handoff_closed_event_count": combined.get(
                        "vertical_handoff_closed_event_count"
                    ),
                    "combined_diagnostic_closed_event_count": combined.get(
                        "combined_diagnostic_closed_event_count"
                    ),
                    "event_count_matches_declared_scope": combined.get(
                        "event_count_matches_declared_scope"
                    ),
                    "mismatch_event_ids": mismatch_ids,
                    "facility_ir_aggregate_closed": combined.get(
                        "facility_ir_aggregate_closed"
                    ),
                    "facility_fn_aggregate_closed": combined.get(
                        "facility_fn_aggregate_closed"
                    ),
                    "qualified_provider_packet_count": combined.get(
                        "qualified_provider_packet_count"
                    ),
                    "facility_qra_claim": combined.get("facility_qra_claim"),
                },
                "interpretation": (
                    "The packet-subset and operator-limited vertical audits are consumed directly "
                    "by the IJHE completion report. Their 29-event diagnostic closure is recorded "
                    "without converting synthetic/operator-limited events into qualified packets, "
                    "frequencies, physical validation, or facility QRA."
                ),
            }
        )
    if risk_atom_chain_audit is not None:
        atom_chain = risk_atom_chain_audit
        required_stages = {
            "source",
            "pool",
            "near_field_and_dispersion",
            "cloud_observation",
            "fire_explosion_damage_risk",
        }
        stage_counts = atom_chain.get("stage_complete_case_counts")
        atom_chain_valid = (
            atom_chain.get("schema_version") == "prism.risk_atom_chain_audit.v1"
            and atom_chain.get("status") == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
            and isinstance(atom_chain.get("case_count"), int)
            and atom_chain.get("case_count", 0) > 0
            and atom_chain.get("complete_case_count") == atom_chain.get("case_count")
            and atom_chain.get("incomplete_case_count") == 0
            and isinstance(atom_chain.get("risk_atom_count"), int)
            and atom_chain.get("risk_atom_count", 0) > 0
            and atom_chain.get("blocking_reasons") == []
            and isinstance(atom_chain.get("required_stage_names"), list)
            and set(atom_chain.get("required_stage_names", [])) == required_stages
            and isinstance(stage_counts, Mapping)
            and all(stage_counts.get(stage) == atom_chain.get("case_count") for stage in required_stages)
            and atom_chain.get("diagnostic_only") is True
            and atom_chain.get("provider_packet_promoted") is False
            and atom_chain.get("physical_validation_claim") is False
            and atom_chain.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_risk_atom_chain_closure",
                "status": "PASS" if atom_chain_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if atom_chain_valid
                    else "one or more executed cases do not retain a complete release-to-final-damage risk-atom chain"
                ),
                "evidence": {
                    "record": atom_chain.get("_record_path"),
                    "schema_version": atom_chain.get("schema_version"),
                    "status": atom_chain.get("status"),
                    "case_count": atom_chain.get("case_count"),
                    "complete_case_count": atom_chain.get("complete_case_count"),
                    "risk_atom_count": atom_chain.get("risk_atom_count"),
                    "incomplete_case_count": atom_chain.get("incomplete_case_count"),
                    "operator_limited_case_count": atom_chain.get("operator_limited_case_count"),
                    "required_stage_names": atom_chain.get("required_stage_names"),
                    "stage_complete_case_counts": stage_counts,
                    "blocking_reason_count": len(atom_chain.get("blocking_reasons", []))
                    if isinstance(atom_chain.get("blocking_reasons"), list)
                    else None,
                    "facility_qra_claim": atom_chain.get("facility_qra_claim"),
                },
                "interpretation": (
                    "Every numerical case reaches a recorded release boundary, mass ledger, "
                    "dispersion/pool, cloud, ignition-damage stage and four branch-specific "
                    "risk atoms. Operator-limited cases remain diagnostic and do not qualify "
                    "the provider or facility QRA."
                ),
            }
        )
    if equipment_state_release_audit is not None:
        equipment_chain = equipment_state_release_audit
        equipment_chain_valid = (
            equipment_chain.get("schema_version")
            == "prism.equipment_state_release_audit.v1"
            and equipment_chain.get("status")
            == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
            and isinstance(equipment_chain.get("case_count"), int)
            and equipment_chain.get("case_count", 0) > 0
            and equipment_chain.get("complete_case_count")
            == equipment_chain.get("case_count")
            and equipment_chain.get("incomplete_case_count") == 0
            and equipment_chain.get("blocking_reasons") == []
            and isinstance(equipment_chain.get("component_count"), int)
            and equipment_chain.get("component_count", 0) > 0
            and isinstance(equipment_chain.get("component_ids"), list)
            and len(equipment_chain.get("component_ids", []))
            == equipment_chain.get("component_count")
            and equipment_chain.get("diagnostic_only") is True
            and equipment_chain.get("provider_packet_promoted") is False
            and equipment_chain.get("physical_validation_claim") is False
            and equipment_chain.get("facility_qra_claim") is False
        )
        checks.append(
            {
                "name": "diagnostic_equipment_state_release_chain",
                "status": "PASS" if equipment_chain_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if equipment_chain_valid
                    else "one or more facility cases do not retain an exact equipment-state to release-packet identity chain"
                ),
                "evidence": {
                    "record": equipment_chain.get("_record_path"),
                    "schema_version": equipment_chain.get("schema_version"),
                    "status": equipment_chain.get("status"),
                    "case_count": equipment_chain.get("case_count"),
                    "complete_case_count": equipment_chain.get("complete_case_count"),
                    "component_count": equipment_chain.get("component_count"),
                    "component_ids": equipment_chain.get("component_ids"),
                    "incomplete_case_count": equipment_chain.get("incomplete_case_count"),
                    "operator_limited_case_count": equipment_chain.get(
                        "operator_limited_case_count"
                    ),
                    "blocking_reason_count": len(equipment_chain.get("blocking_reasons", []))
                    if isinstance(equipment_chain.get("blocking_reasons"), list)
                    else None,
                    "facility_qra_claim": equipment_chain.get("facility_qra_claim"),
                },
                "interpretation": (
                    "Each numerical facility case retains the equipment state, provider packet, "
                    "release termination and digest identity. Operator-limited cases remain "
                    "diagnostic and do not qualify provider evidence or facility QRA."
                ),
            }
        )
    if facility_aggregate_closure_audit is not None:
        aggregate = facility_aggregate_closure_audit
        aggregate_valid = (
            aggregate.get("schema_version")
            == "prism.facility_aggregate_closure_audit.v1"
            and aggregate.get("status")
            == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
            and isinstance(aggregate.get("risk_atom_count"), int)
            and aggregate.get("risk_atom_count", 0) > 0
            and aggregate.get("ir_mismatch_count") == 0
            and aggregate.get("fn_mismatch_count") == 0
            and aggregate.get("blocking_reasons") == []
            and aggregate.get("diagnostic_only") is True
            and aggregate.get("qualified_provider_packet") is False
            and aggregate.get("physical_validation_claim") is False
            and aggregate.get("facility_qra_claim") is False
        )
    if facility_component_contribution_audit is not None:
        component_audit = facility_component_contribution_audit
        component_audit_valid = (
            component_audit.get("schema_version")
            == "prism.facility_component_contribution_audit.v1"
            and component_audit.get("status")
            == "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
            and isinstance(component_audit.get("risk_atom_count"), int)
            and component_audit.get("risk_atom_count", 0) > 0
            and isinstance(component_audit.get("component_count"), int)
            and component_audit.get("component_count", 0) > 0
            and component_audit.get("mismatch_count") == 0
            and component_audit.get("blocking_reasons") == []
            and component_audit.get("diagnostic_only") is True
            and component_audit.get("frequency_reallocation_performed") is False
            and component_audit.get("facility_ir_fn_promotion") is False
            and component_audit.get("qualified_provider_packet") is False
            and component_audit.get("physical_validation_claim") is False
            and component_audit.get("facility_qra_claim") is False
        )
    if facility_frequency_uncertainty_audit is not None:
        frequency_audit = facility_frequency_uncertainty_audit
        frequency_audit_valid = (
            frequency_audit.get("schema_version")
            == "prism.facility_frequency_uncertainty_audit.v1"
            and frequency_audit.get("status")
            == "FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC"
            and isinstance(frequency_audit.get("scenario_count"), int)
            and frequency_audit.get("scenario_count", 0) > 0
            and isinstance(frequency_audit.get("risk_atom_count"), int)
            and frequency_audit.get("risk_atom_count", 0) > 0
            and frequency_audit.get("mismatch_count") == 0
            and frequency_audit.get("blocking_reasons") == []
            and frequency_audit.get("frequency_inference_performed") is False
            and frequency_audit.get("facility_credible_interval") is False
            and frequency_audit.get("statistical_confidence_interval") is False
            and frequency_audit.get("fresh_physics_executed") is False
            and frequency_audit.get("provider_packet_promoted") is False
            and frequency_audit.get("physical_validation_claim") is False
            and frequency_audit.get("facility_qra_claim") is False
            and frequency_audit.get("diagnostic_only") is True
        )
        checks.append(
            {
                "name": "diagnostic_facility_frequency_uncertainty_closure",
                "status": "PASS" if frequency_audit_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if frequency_audit_valid
                    else "stored literature-frequency sensitivity does not match independent risk-atom reweighting"
                ),
                "evidence": {
                    "record": frequency_audit.get("_record_path"),
                    "schema_version": frequency_audit.get("schema_version"),
                    "status": frequency_audit.get("status"),
                    "scenario_count": frequency_audit.get("scenario_count"),
                    "risk_atom_count": frequency_audit.get("risk_atom_count"),
                    "mismatch_count": frequency_audit.get("mismatch_count"),
                    "blocking_reason_count": len(frequency_audit.get("blocking_reasons", []))
                    if isinstance(frequency_audit.get("blocking_reasons"), list)
                    else None,
                    "frequency_inference_performed": frequency_audit.get(
                        "frequency_inference_performed"
                    ),
                    "facility_credible_interval": frequency_audit.get(
                        "facility_credible_interval"
                    ),
                    "fresh_physics_executed": frequency_audit.get(
                        "fresh_physics_executed"
                    ),
                    "facility_qra_claim": frequency_audit.get("facility_qra_claim"),
                },
                "interpretation": (
                    "Literature p05/p95 and fixed-rate scenarios reproduce the saved conditional "
                    "IR/F-N sensitivity. No missing frequency is inferred and no fresh physics is run."
                ),
            }
        )
        checks.append(
            {
                "name": "diagnostic_facility_component_contribution_closure",
                "status": "PASS" if component_audit_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if component_audit_valid
                    else "stored equipment contributions or ranking do not match independent risk-atom recomputation"
                ),
                "evidence": {
                    "record": component_audit.get("_record_path"),
                    "schema_version": component_audit.get("schema_version"),
                    "status": component_audit.get("status"),
                    "risk_atom_count": component_audit.get("risk_atom_count"),
                    "component_count": component_audit.get("component_count"),
                    "mismatch_count": component_audit.get("mismatch_count"),
                    "blocking_reason_count": len(component_audit.get("blocking_reasons", []))
                    if isinstance(component_audit.get("blocking_reasons"), list)
                    else None,
                    "facility_ir_fn_promotion": component_audit.get("facility_ir_fn_promotion"),
                    "facility_qra_claim": component_audit.get("facility_qra_claim"),
                },
                "interpretation": (
                    "Equipment-level IR/F-N contributions and the diagnostic ranking are independently "
                    "reproduced from risk atoms; missing equipment cases and provider evidence remain gates."
                ),
            }
        )
        checks.append(
            {
                "name": "diagnostic_facility_ir_fn_aggregate_closure",
                "status": "PASS" if aggregate_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if aggregate_valid
                    else "stored facility IR/F-N does not match an independent risk-atom aggregation"
                ),
                "evidence": {
                    "record": aggregate.get("_record_path"),
                    "schema_version": aggregate.get("schema_version"),
                    "status": aggregate.get("status"),
                    "risk_atom_count": aggregate.get("risk_atom_count"),
                    "ir_mismatch_count": aggregate.get("ir_mismatch_count"),
                    "fn_mismatch_count": aggregate.get("fn_mismatch_count"),
                    "blocking_reason_count": len(aggregate.get("blocking_reasons", []))
                    if isinstance(aggregate.get("blocking_reasons"), list)
                    else None,
                    "facility_total_risk_available": aggregate.get(
                        "facility_total_risk_available"
                    ),
                    "facility_qra_claim": aggregate.get("facility_qra_claim"),
                },
                "interpretation": (
                    "The conditional facility IR and F/N values are independently reproduced "
                    "from all saved risk atoms. This is a numerical aggregation check; it "
                    "does not qualify provider evidence or open the facility-QRA gate."
                ),
            }
        )
    if isolation_union_extension_verification is not None:
        extension = isolation_union_extension_verification
        base_counts = extension.get("base_counts")
        isolation_counts = extension.get("isolation_counts")
        merged_counts = extension.get("merged_counts")
        extension_policy = extension.get("policy")
        extension_valid = (
            extension.get("schema") == "prism.isolation_union_extension_verification.v1"
            and extension.get("status") == "ISOLATION_UNION_EXTENSION_DIAGNOSTIC"
            and isinstance(base_counts, Mapping)
            and isinstance(isolation_counts, Mapping)
            and isinstance(merged_counts, Mapping)
            and merged_counts.get("events") == base_counts.get("events", 0) + isolation_counts.get("events", 0)
            and merged_counts.get("cases") == base_counts.get("cases", 0) + isolation_counts.get("cases", 0)
            and merged_counts.get("risk_atoms") == base_counts.get("risk_atoms", 0) + isolation_counts.get("risk_atoms", 0)
            and isolation_counts.get("success_cases") == isolation_counts.get("failure_cases")
            and isolation_counts.get("provider_response_consumed") is True
            and isolation_counts.get("state_snapshot_bound_cases") == isolation_counts.get("cases")
            and extension.get("risk_atom_chain_status") == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
            and extension.get("equipment_state_release_status") == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
            and extension.get("equipment_state_release_complete_cases") == merged_counts.get("cases")
            and extension.get("equipment_state_release_incomplete_cases") == 0
            and extension.get("facility_aggregate_closure_status") == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
            and extension.get("facility_component_contribution_status") == "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
            and extension.get("qualified_provider_packet_case_count") == 0
            and extension.get("facility_total_risk_available") is False
            and extension.get("complete_facility_qra_claim") is False
            and extension.get("provider_packet_collection_manifest_status")
            == "OPEN_PROVIDER_PACKET_COLLECTION"
            and extension.get("provider_packet_collection_request_count")
            == isolation_counts.get("cases")
            and extension.get("provider_packet_collection_open_request_count")
            == isolation_counts.get("cases")
            and extension.get("provider_packet_collection_qualified_packet_count") == 0
            and isinstance(extension_policy, Mapping)
            and extension_policy.get("diagnostic_only") is True
            and extension_policy.get("frequency_inference_performed") is False
            and extension_policy.get("physical_validation_claim") is False
            and extension_policy.get("facility_ir_fn_promotion") is False
        )
        checks.append(
            {
                "name": "diagnostic_isolation_union_extension",
                "status": "PASS" if extension_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": (
                    None
                    if extension_valid
                    else "isolation union extension is missing a closed diagnostic chain or has an unsafe promotion flag"
                ),
                "evidence": {
                    "record": extension.get("_record_path"),
                    "schema": extension.get("schema"),
                    "status": extension.get("status"),
                    "base_counts": base_counts,
                    "isolation_counts": isolation_counts,
                    "merged_counts": merged_counts,
                    "risk_atom_chain_status": extension.get("risk_atom_chain_status"),
                    "equipment_state_release_status": extension.get(
                        "equipment_state_release_status"
                    ),
                    "equipment_state_release_complete_cases": extension.get(
                        "equipment_state_release_complete_cases"
                    ),
                    "equipment_state_release_incomplete_cases": extension.get(
                        "equipment_state_release_incomplete_cases"
                    ),
                    "facility_aggregate_closure_status": extension.get(
                        "facility_aggregate_closure_status"
                    ),
                    "facility_component_contribution_status": extension.get(
                        "facility_component_contribution_status"
                    ),
                    "qualified_provider_packet_case_count": extension.get(
                        "qualified_provider_packet_case_count"
                    ),
                    "facility_total_risk_available": extension.get(
                        "facility_total_risk_available"
                    ),
                    "complete_facility_qra_claim": extension.get(
                        "complete_facility_qra_claim"
                    ),
                    "provider_packet_collection_manifest_status": extension.get(
                        "provider_packet_collection_manifest_status"
                    ),
                    "provider_packet_collection_request_count": extension.get(
                        "provider_packet_collection_request_count"
                    ),
                    "provider_packet_collection_open_request_count": extension.get(
                        "provider_packet_collection_open_request_count"
                    ),
                    "provider_packet_collection_qualified_packet_count": extension.get(
                        "provider_packet_collection_qualified_packet_count"
                    ),
                    "policy": extension_policy,
                },
                "interpretation": (
                    "The namespaced isolation success/failure extension is consumed by the IJHE audit. "
                    "Its state, release, consequence and conditional facility aggregation are diagnostic; "
                    "qualified evidence, frequency inference, physical validation and facility QRA remain gated."
                ),
            }
        )
    if slabx_validation_evidence is not None:
        slabx = slabx_validation_evidence
        slabx_checks = slabx.get("checks")
        slabx_valid = (
            slabx.get("schema_version") == "prism.slabx_lh2_validation_audit.v1"
            and slabx.get("status") == "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
            and isinstance(slabx_checks, list)
            and bool(slabx_checks)
            and all(
                isinstance(row, Mapping) and row.get("status") == "PASS"
                for row in slabx_checks
            )
            and slabx.get("physical_validation_claim") is False
            and slabx.get("full_chain_validation_claim") is False
            and slabx.get("facility_qra_claim") is False
            and slabx.get("frequency_inference_performed") is False
        )
        checks.append(
            {
                "name": "diagnostic_slabx_lh2_validation_evidence",
                "status": "PASS" if slabx_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": slabx.get("_record_path"),
                    "schema_version": slabx.get("schema_version"),
                    "status": slabx.get("status"),
                    "model": slabx.get("model"),
                    "check_count": len(slabx_checks) if isinstance(slabx_checks, list) else None,
                    "metrics": slabx.get("metrics"),
                    "physical_validation_claim": slabx.get("physical_validation_claim"),
                    "facility_qra_claim": slabx.get("facility_qra_claim"),
                },
                "interpretation": (
                    "SLABx-LH2 cryogenic-dispersion and pool evidence is consumed as a "
                    "restricted consequence-component record. It does not qualify the "
                    "equipment release, initiating frequency, ignition model, or facility QRA."
                ),
            }
        )
    if realtime_cache_benchmark is not None:
        benchmark = realtime_cache_benchmark
        cache_values = benchmark.get("cache_elapsed_ms_values")
        persistent = benchmark.get("persistent_fresh_physics")
        persistent_values = (
            persistent.get("service_elapsed_ms_values")
            if isinstance(persistent, dict)
            else None
        )
        persistent_steady_values = (
            persistent.get("steady_elapsed_ms_values")
            if isinstance(persistent, dict)
            else None
        )
        persistent_valid = persistent is None or (
            isinstance(persistent, dict)
            and persistent.get("persistent_worker") is True
            and isinstance(persistent.get("request_count"), int)
            and persistent.get("request_count", 0) > 0
            and isinstance(persistent_values, list)
            and len(persistent_values) == persistent.get("request_count")
            and all(isinstance(value, (int, float)) and value > 0 for value in persistent_values)
            and isinstance(persistent_steady_values, list)
            and bool(persistent_steady_values)
            and all(
                isinstance(value, (int, float)) and value > 0
                for value in persistent_steady_values
            )
            and persistent.get("realtime_fresh_physics_claim") is False
            and persistent.get("steady_fresh_physics_meets_one_hz") is False
            and isinstance(persistent.get("steady_p50_ms"), (int, float))
            and isinstance(persistent.get("steady_p95_ms"), (int, float))
            and isinstance(persistent.get("steady_p99_ms"), (int, float))
            and persistent.get("steady_p50_ms", 0) <= persistent.get("steady_p95_ms", 0)
            and persistent.get("steady_p95_ms", 0) <= persistent.get("steady_p99_ms", 0)
        )
        benchmark_valid = (
            benchmark.get("schema_version") == "prism.realtime_cache_benchmark.v1"
            and isinstance(benchmark.get("fresh_physics_elapsed_ms"), (int, float))
            and benchmark.get("fresh_physics_elapsed_ms", 0) > 0
            and isinstance(cache_values, list)
            and bool(cache_values)
            and all(isinstance(value, (int, float)) and value >= 0 for value in cache_values)
            and isinstance(benchmark.get("cache_hits"), int)
            and benchmark.get("cache_hits") == len(cache_values)
            and isinstance(benchmark.get("cache_median_ms"), (int, float))
            and isinstance(benchmark.get("cache_p95_ms"), (int, float))
            and benchmark.get("cache_median_ms", float("inf")) <= 1000
            and benchmark.get("cache_p95_ms", float("inf")) <= 1000
            and benchmark.get("one_hz_deadline_s") == 1.0
            and benchmark.get("fresh_physics_meets_one_hz") is False
            and benchmark.get("cache_meets_one_hz_all_samples") is True
            and benchmark.get("realtime_fresh_physics_claim") is False
            and persistent_valid
        )
        checks.append(
            {
                "name": "diagnostic_realtime_cache_benchmark",
                "status": "PASS" if benchmark_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": benchmark.get("_record_path"),
                    "schema_version": benchmark.get("schema_version"),
                    "facility_id": benchmark.get("facility_id"),
                    "request_event_id": benchmark.get("request_event_id"),
                    "fresh_physics_elapsed_ms": benchmark.get("fresh_physics_elapsed_ms"),
                    "cache_hits": benchmark.get("cache_hits"),
                    "cache_sample_count": len(cache_values) if isinstance(cache_values, list) else None,
                    "cache_median_ms": benchmark.get("cache_median_ms"),
                    "cache_p95_ms": benchmark.get("cache_p95_ms"),
                    "one_hz_deadline_s": benchmark.get("one_hz_deadline_s"),
                    "fresh_physics_meets_one_hz": benchmark.get("fresh_physics_meets_one_hz"),
                    "cache_meets_one_hz_all_samples": benchmark.get(
                        "cache_meets_one_hz_all_samples"
                    ),
                    "realtime_fresh_physics_claim": benchmark.get(
                        "realtime_fresh_physics_claim"
                    ),
                    "persistent_fresh_physics": persistent,
                },
                "interpretation": (
                    "Repeated exact-cache lookups meet the declared 1 Hz diagnostic deadline in "
                    "this benchmark. The separately measured cold and warm fresh-physics runs "
                    "remain diagnostic timing evidence; no fresh-physics 1 Hz service claim is "
                    "made."
                ),
            }
        )
    if domain_recovery_audit is not None:
        recovery = domain_recovery_audit
        persistent = recovery.get("persistent_domain_incomplete_event_ids")
        recovery_valid = (
            recovery.get("schema") == "prism.domain_recovery_audit.v1"
            and recovery.get("status") == "DOMAIN_RECOVERY_REVIEWED"
            and isinstance(recovery.get("event_count"), int)
            and recovery.get("event_count", 0) > 0
            and isinstance(persistent, list)
            and recovery.get("facility_ir_fn_promotion") is False
            and recovery.get("qualified_provider_packet_promotion") is False
        )
        checks.append(
            {
                "name": "diagnostic_domain_recovery_audit",
                "status": "PASS" if recovery_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": recovery.get("_record_path"),
                    "schema": recovery.get("schema"),
                    "status": recovery.get("status"),
                    "event_count": recovery.get("event_count"),
                    "baseline_domain_incomplete_event_count": recovery.get(
                        "baseline_domain_incomplete_event_count"
                    ),
                    "recovery_domain_incomplete_event_count": recovery.get(
                        "recovery_domain_incomplete_event_count"
                    ),
                    "persistent_domain_incomplete_event_ids": persistent,
                    "recovered_event_ids": recovery.get("recovered_event_ids"),
                    "recovery_flammability_proven_event_count": recovery.get(
                        "recovery_flammability_proven_event_count"
                    ),
                    "recovery_flammability_proven_event_ids": recovery.get(
                        "recovery_flammability_proven_event_ids"
                    ),
                    "facility_ir_fn_promotion": recovery.get("facility_ir_fn_promotion"),
                },
                "interpretation": (
                    (
                        "An explicit larger-domain sensitivity run was compared event by event. "
                        "The conservative outside-LFL proof closes the fire/explosion domain "
                        "gate for the recovered events, while provider qualification and "
                        "facility IR/F-N remain withheld."
                    )
                    if recovery.get("recovery_domain_incomplete_event_count") == 0
                    else (
                        "An explicit larger-domain sensitivity run was compared event by event. "
                        "Persistent domain blockers remain visible and the comparison cannot "
                        "promote provider qualification or facility IR/F-N."
                    )
                ),
            }
        )
    restricted_physical_status = current_status.get("physical_validation_evidence_status")
    restricted_physical_record = current_status.get("physical_validation_evidence_record")
    restricted_physical_component = current_status.get("physical_validation_evidence_component")
    restricted_physical_evidence = (
        isinstance(restricted_physical_status, str)
        and restricted_physical_status.startswith("RESTRICTED_COMPONENT_EVIDENCE")
        and isinstance(restricted_physical_record, str)
        and bool(restricted_physical_record.strip())
        and isinstance(restricted_physical_component, str)
        and bool(restricted_physical_component.strip())
    )
    conditional_frequency_uncertainty = False
    if uncertainty is not None and isinstance(uncertainty.get("scenarios"), list):
        scenario_rows = uncertainty.get("scenarios", [])
        conditional_frequency_uncertainty = bool(scenario_rows) and all(
            isinstance(row, Mapping)
            and (
                isinstance(row.get("conditional_diagnostic_facility_annual_ir_low_high"), Mapping)
                or isinstance(row.get("conditional_diagnostic_facility_expected_death_fn_low_high"), list)
                or isinstance(row.get("conditional_diagnostic_facility_risk_available"), bool)
            )
            for row in scenario_rows
        )
    conditional_scope_fields_present = (
        "conditional_chain_complete" in scope_matrix
        or any(
            isinstance(row, Mapping) and "conditional_status" in row
            for row in scope_matrix.get("rows", [])
        )
    )
    conditional_scope_valid = (
        isinstance(scope_matrix.get("conditional_chain_complete"), bool)
        and isinstance(scope_matrix.get("conditional_chain_blocking_reasons"), list)
        and isinstance(scope_matrix.get("rows"), list)
        and all(
            isinstance(row, Mapping)
            and isinstance(row.get("conditional_status"), str)
            and isinstance(row.get("conditional_executed_case_count"), int)
            and isinstance(row.get("conditional_uncomputed_case_count"), int)
            for row in scope_matrix["rows"]
        )
    )
    scope_gap_summary = scope_matrix.get("gap_summary")
    scope_numerical_gap_families = (
        scope_gap_summary.get("families_with_numerical_case_gap", [])
        if isinstance(scope_gap_summary, Mapping)
        else []
    )
    scope_qualification_gap_families = (
        scope_gap_summary.get("families_with_qualification_gap", [])
        if isinstance(scope_gap_summary, Mapping)
        else []
    )
    if scope_numerical_gap_families or scope_matrix.get("conditional_uncomputed_case_count", 0):
        scope_blocking_reason = (
            "one or more declared accident families still have numerical case gaps or "
            "uncomputed cases"
        )
    elif scope_qualification_gap_families:
        scope_blocking_reason = (
            "declared accident families have numerical diagnostic outputs, but provider "
            "qualification or independent physical-validation evidence remains open"
        )
    else:
        scope_blocking_reason = "one or more declared accident families are missing, partial, or uncomputed"
    checks.extend([
        _check(
            "equipment_model_binding_to_accident_release",
            current_status.get("equipment_model_binding_status")
            in {"ACCIDENT_RELEASE_INTERFACE_BOUND", "STATE_ONLY_BOUND"}
            and isinstance(current_status.get("equipment_model_binding_component_count"), int)
            and current_status.get("equipment_model_binding_component_count") > 0
            and isinstance(current_status.get("equipment_model_binding_accident_release_supported_component_count"), int)
            and current_status.get("equipment_model_binding_accident_release_supported_component_count") > 0
            and current_status.get("equipment_model_binding_accident_release_supported_component_count")
            <= current_status.get("equipment_model_binding_component_count")
            and (
                current_status.get("equipment_model_binding_diagnostic_release_adapter_component_count") is None
                or (
                    isinstance(current_status.get("equipment_model_binding_diagnostic_release_adapter_component_count"), int)
                    and current_status.get("equipment_model_binding_diagnostic_release_adapter_component_count")
                    >= current_status.get("equipment_model_binding_accident_release_supported_component_count")
                )
            )
            and (
                external_equipment_model_contract_audit is None
                or (
                    external_equipment_model_contract_audit.get("schema_version")
                    == "prism.external_model_contract_audit.v1"
                    and external_equipment_model_contract_audit.get("status")
                    == "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND"
                    and isinstance(
                        external_equipment_model_contract_audit.get(
                            "native_accident_export_component_count"
                        ),
                        int,
                    )
                    and external_equipment_model_contract_audit.get(
                        "native_accident_export_component_count"
                    )
                    > 0
                    and not external_equipment_model_contract_audit.get(
                        "native_accident_export_missing_components"
                    )
                )
            ),
            {
                "model_binding_status": current_status.get("equipment_model_binding_status"),
                "component_count": current_status.get("equipment_model_binding_component_count"),
                "state_supported_component_count": current_status.get(
                    "equipment_model_binding_state_supported_component_count"
                ),
                "accident_release_supported_component_count": current_status.get(
                    "equipment_model_binding_accident_release_supported_component_count"
                ),
                "diagnostic_release_adapter_component_count": current_status.get(
                    "equipment_model_binding_diagnostic_release_adapter_component_count"
                ),
                "record": current_status.get("equipment_model_binding_record"),
                **(
                    {
                        "external_model_contract_status": external_equipment_model_contract_audit.get(
                            "status"
                        ),
                        "external_model_contract_native_accident_export_component_count": external_equipment_model_contract_audit.get(
                            "native_accident_export_component_count"
                        ),
                        "external_model_contract_native_accident_export_missing_components": external_equipment_model_contract_audit.get(
                            "native_accident_export_missing_components"
                        ),
                        "external_model_contract_record": external_equipment_model_contract_audit.get(
                            "_record_path"
                        ),
                    }
                    if external_equipment_model_contract_audit is not None
                    else {}
                ),
            },
            (
                "the external equipment model source does not expose a native accident-release export"
                if external_equipment_model_contract_audit is not None
                and external_equipment_model_contract_audit.get("status")
                != "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND"
                else "one or more equipment models lacks an accident-release interface and provider termination ledger"
            ),
        ),
        _check(
            "actual_provider_release_packet",
            actual_packet_available is True,
            {
                "actual_facility_packet_available": actual_packet_available,
                "release_inventory_status": release_inventory_status,
                "qualified_packet_count": current_status.get(
                    "external_provider_evidence_accident_release_qualified_files"
                ),
                **(
                    {
                        "qualification_coverage_status": qualification_status,
                        "qualification_coverage_qualified_packet_count": qualified_provider_packet_count,
                    }
                    if provider_qualification_coverage is not None
                    else {}
                ),
            },
            "only synthetic or screening provider releases are available for this campaign",
        ),
        _check(
            "provider_worklist_coverage",
            worklist_complete or structural_worklist_coverage,
            {
                "source": "provider_worklist" if provider_worklist is not None else "current_status",
                "status": worklist_status,
                "frequency_event_count": worklist_event_count,
                "provider_packet_count": worklist_packet_count,
                "uncomputed_provider_packet_count": worklist_uncomputed_count,
                "diagnostic_release_adapter_component_count": worklist_diagnostic_adapter_count,
                "structural_diagnostic_coverage": structural_worklist_coverage,
                "native_scope_catalog_structural_coverage": native_catalog_structural_coverage,
                "native_scope_catalog_evidence": native_catalog_evidence,
                "qualified_provider_packet_count": (
                    diagnostic_worklist_evidence.get("qualified_provider_packet_count")
                    if isinstance(diagnostic_worklist_evidence, Mapping)
                    else None
                ),
                "qualification_readiness": (
                    diagnostic_worklist_evidence.get("qualification_readiness")
                    if isinstance(diagnostic_worklist_evidence, Mapping)
                    else None
                ),
                **(
                    {
                        "qualification_coverage_status": qualification_status,
                        "qualification_coverage_qualified_packet_count": qualified_provider_packet_count,
                        "qualification_coverage_complete": qualified_worklist_coverage,
                    }
                    if provider_qualification_coverage is not None
                    else {}
                ),
            },
            "the provider-release worklist still contains events without exact provider packets or a complete structural diagnostic catalog",
        ),
        _check(
            "release_duration_isolation_inventory_ledger",
            bool(executed_cases)
            and len(ledger_cases) == len(executed_cases)
            and release_ledger_valid,
            {
                "executed_case_count": len(executed_cases),
                "cases_with_termination_and_mass_ledger": len(ledger_cases),
                "release_ledger_schema": (
                    release_ledger.get("schema_version")
                    if isinstance(release_ledger, Mapping)
                    else None
                ),
                "release_ledger_row_count": len(release_ledger_rows)
                if release_ledger_rows is not None
                else None,
                "release_ledger_summary": release_ledger_summary,
                "max_end_to_end_residual_kg": max(
                    (
                        abs(float(row["mass_ledger"]["end_to_end_residual_kg"]))
                        for row in ledger_cases
                    ),
                    default=None,
                ),
            },
            "one or more executed cases lacks a finite release termination time or mass/inventory ledger",
        ),
        _check(
            "declared_major_accident_scope",
            scope_matrix.get("matrix_complete") is True,
            {
                "matrix_status": scope_matrix.get("matrix_complete"),
                "blocking_reasons": scope_matrix.get("blocking_reasons", []),
                "required_family_count": len(scope_matrix.get("required_families", [])),
                "families_with_numerical_case_gap": scope_numerical_gap_families,
                "families_with_qualification_gap": scope_qualification_gap_families,
            },
            scope_blocking_reason,
        ),
        {
            "name": "conditional_accident_scope_accounting",
            "status": (
                "PASS"
                if conditional_scope_valid or not conditional_scope_fields_present
                else "BLOCKED"
            ),
            "diagnostic_only": True,
            "evidence": {
                "conditional_chain_complete": scope_matrix.get("conditional_chain_complete"),
                "conditional_chain_blocking_reasons": scope_matrix.get(
                    "conditional_chain_blocking_reasons", []
                ),
                "strict_matrix_complete": scope_matrix.get("matrix_complete"),
                "strict_blocking_reasons": scope_matrix.get("blocking_reasons", []),
            },
            "blocking_reason": (
                None
                if conditional_scope_valid or not conditional_scope_fields_present
                else "conditional accident-scope accounting is missing or malformed"
            ),
            "interpretation": (
                "Conditional execution status counts numerical consequence-chain outputs, "
                "including operator-limited cases, while strict matrix_complete remains the "
                "facility qualification gate."
            ),
        },
        _check(
            "facility_ir_fn_available",
            campaign_result.get("total_facility_annual_ir_low_high") is not None
            and campaign_result.get("total_facility_expected_death_fn_low_high") is not None,
            {
                "total_facility_annual_ir_low_high": campaign_result.get("total_facility_annual_ir_low_high"),
                "total_facility_expected_death_fn_low_high": campaign_result.get("total_facility_expected_death_fn_low_high"),
            },
            "facility IR/F-N is withheld because the declared facility scope is incomplete or synthetic",
        ),
        _check(
            "physical_validation_evidence",
            current_status.get("physical_validation_claim") is True
            or restricted_physical_evidence,
            {
                "physical_validation_claim": current_status.get("physical_validation_claim"),
                "evidence_status": restricted_physical_status,
                "evidence_record": restricted_physical_record,
                "evidence_component": restricted_physical_component,
                "restricted_component_evidence": restricted_physical_evidence,
            },
            "independent end-to-end physical validation or an auditable restricted component evidence record is missing",
        ),
        _check(
            "frequency_uncertainty_reported",
            uncertainty is not None
            and bool(uncertainty.get("scenarios"))
            and (
                uncertainty.get("facility_credible_interval") is True
                or conditional_frequency_uncertainty
            ),
            {
                "uncertainty_result_present": uncertainty is not None,
                "scenario_count": len(uncertainty.get("scenarios", [])) if uncertainty else 0,
                "facility_credible_interval": uncertainty.get("facility_credible_interval") if uncertainty else None,
                "conditional_frequency_uncertainty": conditional_frequency_uncertainty,
            },
            "literature frequency uncertainty is missing for both the complete facility and an auditable conditional known-atom view",
        ),
        _check(
            "processing_time_evidence",
            _finite(timing.get("campaign_elapsed_ms"))
            and isinstance(fresh_physics_cases, int)
            and fresh_physics_cases > 0,
            {
                "fresh_physics_cases": fresh_physics_cases,
                "campaign_elapsed_ms": timing.get("campaign_elapsed_ms"),
                "case_p95_ms": timing.get("case_p95_ms"),
                "case_p99_ms": timing.get("case_p99_ms"),
                "timing_distribution": timing.get("distribution"),
                "one_hz_fresh_physics_demonstrated": current_status.get("one_hz_fresh_physics_demonstrated"),
            },
            "fresh-case timing evidence is missing",
        ),
        _check(
            "realtime_monitor_contract",
            current_status.get("realtime_monitor_implemented") is True,
            {
                "implemented": current_status.get("realtime_monitor_implemented"),
                "module": current_status.get("realtime_monitor_module"),
                "test_status": current_status.get("realtime_monitor_test_status"),
                "one_hz_fresh_physics_demonstrated": current_status.get(
                    "realtime_monitor_one_hz_claim",
                    current_status.get("one_hz_fresh_physics_demonstrated"),
                ),
            },
            "sensor-conditioned realtime monitor contract is missing",
        ),
    ])
    # A strict scope matrix also includes qualification readiness. Preserve
    # that blocker, but expose a separate diagnostic result when every
    # declared family has a numerical case and the remaining gaps are only
    # provider/qualification evidence.
    if isinstance(scope_gap_summary, Mapping) or "numerically_executed_case_count" in scope_matrix:
        numerical_gap_families = (
            scope_gap_summary.get("families_with_numerical_case_gap", [])
            if isinstance(scope_gap_summary, Mapping)
            else None
        )
        qualification_gap_families = (
            scope_gap_summary.get("families_with_qualification_gap", [])
            if isinstance(scope_gap_summary, Mapping)
            else None
        )
        numerical_scope_valid = (
            isinstance(scope_matrix.get("required_families"), list)
            and bool(scope_matrix.get("required_families"))
            and isinstance(scope_matrix.get("rows"), list)
            and len(scope_matrix.get("rows", []))
            == len(scope_matrix.get("required_families", []))
            and isinstance(numerical_gap_families, list)
            and not numerical_gap_families
            and scope_matrix.get("not_numerically_executed_case_count") == 0
            and scope_matrix.get("conditional_uncomputed_case_count") == 0
            and isinstance(scope_matrix.get("numerically_executed_case_count"), int)
            and scope_matrix.get("numerically_executed_case_count", 0) > 0
        )
        checks.append(
            {
                "name": "diagnostic_numerical_scope_coverage",
                "status": "PASS" if numerical_scope_valid else "BLOCKED",
                "diagnostic_only": True,
                "blocking_reason": None,
                "evidence": {
                    "record": scope_matrix.get("_record_path"),
                    "required_family_count": (
                        len(scope_matrix.get("required_families", []))
                        if isinstance(scope_matrix.get("required_families"), list)
                        else None
                    ),
                    "scope_row_count": (
                        len(scope_matrix.get("rows", []))
                        if isinstance(scope_matrix.get("rows"), list)
                        else None
                    ),
                    "numerically_executed_case_count": scope_matrix.get(
                        "numerically_executed_case_count"
                    ),
                    "conditional_uncomputed_case_count": scope_matrix.get(
                        "conditional_uncomputed_case_count"
                    ),
                    "not_numerically_executed_case_count": scope_matrix.get(
                        "not_numerically_executed_case_count"
                    ),
                    "families_with_numerical_case_gap": numerical_gap_families,
                    "families_with_qualification_gap": qualification_gap_families,
                    "matrix_complete": scope_matrix.get("matrix_complete"),
                    "facility_qra_claim": False,
                },
                "interpretation": (
                    "Every declared accident family has a numerical diagnostic case in the "
                    "scope matrix; any remaining family gap is an evidence/qualification gap. "
                    "This does not make operator-limited or synthetic cases qualified and does "
                    "not promote facility IR/F-N."
                ),
            }
        )
    if validation_evidence_matrix is not None:
        matrix_status = validation_evidence_matrix.get("status")
        matrix_claims_closed = all(
            validation_evidence_matrix.get(field) is False
            for field in (
                "physical_validation_claim",
                "full_chain_validation_claim",
                "accident_release_validation_claim",
                "facility_qra_claim",
                "frequency_inference_performed",
            )
        )
        matrix_check = _check(
            "validation_evidence_matrix",
            matrix_status == "RESTRICTED_EVIDENCE_MATRIX" and matrix_claims_closed,
            {
                "status": matrix_status,
                "decision": validation_evidence_matrix.get("decision"),
                "domain_count": len(validation_evidence_matrix.get("evidence_domains", []))
                if isinstance(validation_evidence_matrix.get("evidence_domains"), list)
                else None,
                "blocking_reason_count": len(validation_evidence_matrix.get("blocking_reasons", []))
                if isinstance(validation_evidence_matrix.get("blocking_reasons"), list)
                else None,
                "claims_closed": matrix_claims_closed,
                "record": validation_evidence_matrix.get("_record_path"),
            },
            "validation evidence matrix is missing, inconsistent, or contains an unsafe promotion claim",
        )
        matrix_check["diagnostic_only"] = True
        matrix_check["interpretation"] = (
            "The matrix keeps component, observation, interface and conditional evidence separate; "
            "it documents the facility-QRA gate and does not open it."
        )
        checks.append(matrix_check)
    if scope_ledger_consistency is not None:
        consistency_status = scope_ledger_consistency.get("status")
        consistency_check = _check(
            "scope_ledger_consistency",
            consistency_status == "CONSISTENT_SCOPE_LEDGER"
            and scope_ledger_consistency.get("facility_qra_claim") is False,
            {
                "status": consistency_status,
                "scope_event_count": scope_ledger_consistency.get("scope_matrix_event_count"),
                "ledger_event_count": scope_ledger_consistency.get("facility_ledger_event_count"),
                "scope_conditional_uncomputed_case_count": scope_ledger_consistency.get(
                    "scope_matrix_conditional_uncomputed_case_count"
                ),
                "ledger_conditional_uncomputed_case_count": scope_ledger_consistency.get(
                    "facility_ledger_conditional_uncomputed_case_count"
                ),
                "blocking_reason_count": len(scope_ledger_consistency.get("blocking_reasons", []))
                if isinstance(scope_ledger_consistency.get("blocking_reasons"), list)
                else None,
                "record": scope_ledger_consistency.get("_record_path"),
            },
            "scope matrix and merged facility ledger do not describe the same event/case accounting",
        )
        consistency_check["diagnostic_only"] = False
        consistency_check["interpretation"] = (
            "A merged facility result cannot be promoted while its declared scope "
            "matrix and facility ledger use different event or case accounting."
        )
        checks.append(consistency_check)
    if facility_case_packet_coverage is not None:
        case_coverage = facility_case_packet_coverage
        case_promotion_policy = case_coverage.get("promotion_policy")
        if not isinstance(case_promotion_policy, Mapping):
            case_promotion_policy = {}
        requested_case_count = case_coverage.get("case_request_count")
        qualified_case_count = case_coverage.get("qualified_provider_case_count")
        qualified_event_count = case_coverage.get("qualified_provider_event_count")
        case_coverage_valid = (
            case_coverage.get("schema") == "prism.facility_case_provider_coverage.v1"
            and case_coverage.get("status") == "QUALIFIED_FULL_CASE_COVERAGE"
            and isinstance(requested_case_count, int)
            and requested_case_count > 0
            and qualified_case_count == requested_case_count
            and isinstance(qualified_event_count, int)
            and qualified_event_count > 0
            and case_promotion_policy.get("frequency_is_not_assigned") is True
            and case_promotion_policy.get("physical_validation_claim") is False
            and case_promotion_policy.get("facility_ir_fn_promotion")
            == "requires this full case gate plus independent scope and validation gates"
        )
        checks.append(
            {
                "name": "facility_case_provider_packet_coverage",
                "status": "PASS" if case_coverage_valid else "BLOCKED",
                "diagnostic_only": False,
                "blocking_reason": (
                    None
                    if case_coverage_valid
                    else "facility cases do not all have exact qualified provider packet evidence"
                ),
                "evidence": {
                    "record": case_coverage.get("_record_path"),
                    "schema": case_coverage.get("schema"),
                    "status": case_coverage.get("status"),
                    "case_request_count": requested_case_count,
                    "qualified_provider_event_count": qualified_event_count,
                    "qualified_provider_case_count": qualified_case_count,
                    "provider_evidence_row_count": case_coverage.get("provider_evidence_row_count"),
                    "status_counts": case_coverage.get("status_counts"),
                    "blocking_reasons": case_coverage.get("blocking_reasons", []),
                    "promotion_policy": case_promotion_policy,
                },
                "interpretation": (
                    "Every merged facility weather/release case must resolve to an exact qualified "
                    "provider packet before the facility chain can be presented as complete. A packet "
                    "may be reused across weather cases, but missing case identity remains a blocker; "
                    "this check never infers frequency or physical validation."
                ),
            }
        )
    if hazop_forecast_scan is not None:
        forecast_policy = hazop_forecast_scan.get("policy")
        if not isinstance(forecast_policy, Mapping):
            forecast_policy = {}
        steps = hazop_forecast_scan.get("steps")
        scenario_entries = hazop_forecast_scan.get("scenario_entries")
        trigger_count = hazop_forecast_scan.get("trigger_count")
        evaluated_count = hazop_forecast_scan.get("evaluated_count")
        withheld_count = hazop_forecast_scan.get("withheld_count")
        forecast_timing = hazop_forecast_scan.get("timing")
        mode_trace_valid = True
        if isinstance(scenario_entries, list):
            for entry in scenario_entries:
                if not isinstance(entry, Mapping):
                    mode_trace_valid = False
                    break
                if entry.get("trigger_type") in {
                    "RISK_CONDITION_REACHED",
                    "ACTIVE_CONDITION_RECHECK",
                    "RISK_CONDITION_CLEARED",
                }:
                    mode = entry.get("operating_mode")
                    if not isinstance(mode, str) or not mode.strip():
                        mode_trace_valid = False
                        break
        if mode_trace_valid and isinstance(steps, list):
            for step in steps:
                if not isinstance(step, Mapping):
                    mode_trace_valid = False
                    break
                for component in step.get("components", ()):
                    if not isinstance(component, Mapping):
                        mode_trace_valid = False
                        break
                    for scenario_row in component.get("scenarios", ()):
                        if not isinstance(scenario_row, Mapping):
                            mode_trace_valid = False
                            break
                        scenario = scenario_row.get("scenario")
                        if isinstance(scenario, Mapping):
                            if scenario_row.get("operating_mode") != scenario.get("operating_mode"):
                                mode_trace_valid = False
                                break
                    if not mode_trace_valid:
                        break
                if not mode_trace_valid:
                    break
        timing_valid = (
            isinstance(forecast_timing, Mapping)
            and _finite(forecast_timing.get("wall_elapsed_ms"))
            and float(forecast_timing.get("wall_elapsed_ms")) >= 0.0
            and _finite(forecast_timing.get("quantitative_evaluation_elapsed_ms"))
            and float(forecast_timing.get("quantitative_evaluation_elapsed_ms")) >= 0.0
            and forecast_timing.get("fresh_physics_claim") is False
        )
        forecast_valid = (
            hazop_forecast_scan.get("schema_version") == "prism.hazop_forecast_risk_scan.v1"
            and hazop_forecast_scan.get("status") == "FORECAST_RISK_SCAN_COMPLETE"
            and hazop_forecast_scan.get("forecast_origin") == "model_prediction"
            and isinstance(steps, list)
            and bool(steps)
            and isinstance(scenario_entries, list)
            and isinstance(trigger_count, int)
            and trigger_count >= 0
            and isinstance(evaluated_count, int)
            and evaluated_count >= 0
            and isinstance(withheld_count, int)
            and withheld_count >= 0
            and trigger_count == evaluated_count + withheld_count
            and forecast_policy.get("operating_mode_taken_from_forecast_input") is True
            and forecast_policy.get("operating_mode_trace_recorded") is True
            and forecast_policy.get("frequency_inference_performed") is False
            and forecast_policy.get("sensor_frequency_learning_used") is False
            and forecast_policy.get("facility_qra_promotion") is False
            and forecast_policy.get("diagnostic_only") is True
            and mode_trace_valid
            and timing_valid
        )
        forecast_check = _check(
            "diagnostic_hazop_forecast_risk_scan",
            forecast_valid,
            {
                "record": hazop_forecast_scan.get("_record_path"),
                "status": hazop_forecast_scan.get("status"),
                "schema_version": hazop_forecast_scan.get("schema_version"),
                "forecast_origin": hazop_forecast_scan.get("forecast_origin"),
                "step_count": len(steps) if isinstance(steps, list) else None,
                "scenario_entry_count": len(scenario_entries) if isinstance(scenario_entries, list) else None,
                "trigger_count": trigger_count,
                "evaluated_count": evaluated_count,
                "withheld_count": withheld_count,
                "timing": dict(forecast_timing) if isinstance(forecast_timing, Mapping) else None,
                "operating_mode_trace_valid": mode_trace_valid,
                "policy": dict(forecast_policy),
            },
            "forecast HAZOP scan is missing a valid state-origin, trigger accounting, processing timing, or fail-closed policy",
        )
        forecast_check["diagnostic_only"] = True
        forecast_check["interpretation"] = (
            "Predicted operating-mode frames are checked as a diagnostic trigger path. "
            "A withheld quantitative evaluator is preserved as withheld evidence; this check "
            "never infers frequency or promotes facility QRA."
        )
        checks.append(forecast_check)
    if hazop_integrated_risk is not None:
        integrated = hazop_integrated_risk
        policy = integrated.get("policy")
        policy = policy if isinstance(policy, Mapping) else {}
        current = integrated.get("current")
        current = current if isinstance(current, Mapping) else {}
        forecast = integrated.get("forecast")
        forecast = forecast if isinstance(forecast, Mapping) else {}
        linkage = integrated.get("linkage")
        linkage = linkage if isinstance(linkage, Mapping) else {}
        current_component_ids = linkage.get("current_component_ids")
        forecast_component_ids = linkage.get("forecast_component_ids")
        scoped_keys = linkage.get("shared_component_scenario_keys")
        scoped_keys_valid = (
            isinstance(scoped_keys, list)
            and all(
                isinstance(row, Mapping)
                and isinstance(row.get("component_id"), str)
                and bool(row.get("component_id"))
                and isinstance(row.get("scenario_id"), str)
                and bool(row.get("scenario_id"))
                for row in scoped_keys
            )
        )
        current_valid = (
            current.get("schema_version") == "prism.hazop_facility_runtime.v1"
            and current.get("status") in {
                "FACILITY_HAZOP_RUNTIME_EVALUATED",
                "FACILITY_HAZOP_RUNTIME_PARTIAL",
            }
            and isinstance(current.get("components"), Mapping)
            and isinstance(current.get("policy"), Mapping)
            and current["policy"].get("facility_annual_qra_promotion") is False
            and current["policy"].get("frequency_inference_performed") is False
        )
        forecast_not_requested = forecast.get("status") == "FORECAST_NOT_REQUESTED"
        forecast_valid = forecast_not_requested or (
            forecast.get("schema_version") == "prism.hazop_forecast_risk_scan.v1"
            and forecast.get("status") == "FORECAST_RISK_SCAN_COMPLETE"
            and forecast.get("forecast_origin") == "model_prediction"
            and isinstance(forecast.get("policy"), Mapping)
            and forecast["policy"].get("facility_qra_promotion") is False
            and forecast["policy"].get("frequency_inference_performed") is False
        )
        facility_campaign = integrated.get("facility_campaign")
        if facility_campaign is None:
            facility_campaign_valid = True
            facility_campaign_status = "LEGACY_NOT_REPORTED"
            facility_campaign_policy: Mapping[str, Any] = {}
        elif isinstance(facility_campaign, Mapping):
            facility_campaign_status = str(facility_campaign.get("status", ""))
            facility_campaign_policy = facility_campaign.get("policy")
            facility_campaign_policy = (
                facility_campaign_policy
                if isinstance(facility_campaign_policy, Mapping)
                else {}
            )
            facility_campaign_valid = (
                facility_campaign_status in {
                    "FACILITY_CAMPAIGN_NOT_REQUESTED",
                    "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
                    "FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
                }
                or facility_campaign_status.startswith("WITHHELD_")
            ) and (
                facility_campaign_policy.get("facility_qra_promotion") is False
                and facility_campaign_policy.get("frequency_inference_performed") is False
                and facility_campaign_policy.get("physical_validation_claim") is False
                and facility_campaign.get("complete_facility_qra_claim") is not True
            )
        else:
            facility_campaign_status = "INVALID"
            facility_campaign_policy = {}
            facility_campaign_valid = False
        integrated_timing = integrated.get("timing")
        integrated_timing_valid = (
            isinstance(integrated_timing, Mapping)
            and _finite(integrated_timing.get("wall_elapsed_ms"))
            and float(integrated_timing.get("wall_elapsed_ms")) >= 0.0
            and isinstance(integrated_timing.get("interpretation"), str)
            and "1 Hz" in integrated_timing.get("interpretation", "")
        )
        forecast_facility_campaign = integrated.get("forecast_facility_campaign")
        if forecast_facility_campaign is None:
            forecast_facility_campaign_valid = True
            forecast_facility_campaign_status = "LEGACY_NOT_REPORTED"
        elif isinstance(forecast_facility_campaign, Mapping):
            forecast_facility_campaign_status = str(
                forecast_facility_campaign.get("status", "")
            )
            forecast_facility_campaign_policy = forecast_facility_campaign.get("policy")
            forecast_facility_campaign_policy = (
                forecast_facility_campaign_policy
                if isinstance(forecast_facility_campaign_policy, Mapping)
                else {}
            )
            forecast_facility_campaign_valid = (
                forecast_facility_campaign_status in {
                    "FORECAST_FACILITY_CAMPAIGN_NOT_REQUESTED",
                    "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
                }
                or forecast_facility_campaign_status.startswith("WITHHELD_")
            ) and (
                forecast_facility_campaign_policy.get("facility_qra_promotion") is False
                and forecast_facility_campaign_policy.get("frequency_inference_performed") is False
                and forecast_facility_campaign_policy.get("physical_validation_claim") is False
                and forecast_facility_campaign.get("complete_facility_qra_claim") is not True
            )
        else:
            forecast_facility_campaign_status = "INVALID"
            forecast_facility_campaign_valid = False
        integrated_valid = (
            integrated.get("schema_version") == "prism.hazop_integrated_risk.v1"
            and integrated.get("status") in {
                "INTEGRATED_DIAGNOSTIC_COMPLETE",
                "INTEGRATED_DIAGNOSTIC_PARTIAL",
            }
            and isinstance(current_component_ids, list)
            and bool(current_component_ids)
            and isinstance(forecast_component_ids, list)
            and current_valid
            and forecast_valid
            and facility_campaign_valid
            and forecast_facility_campaign_valid
            and integrated_timing_valid
            and linkage.get("mode_and_scenario_identity_preserved") is True
            and scoped_keys_valid
            and policy.get("operating_mode_taken_from_input") is True
            and policy.get("frequency_inference_performed") is False
            and policy.get("sensor_frequency_learning_used") is False
            and policy.get("provider_release_created_by_integration") is False
            and policy.get("facility_qra_promotion") is False
            and policy.get("diagnostic_only") is True
        )
        integrated_check = _check(
            "diagnostic_hazop_integrated_risk",
            integrated_valid,
            {
                "record": integrated.get("_record_path"),
                "schema_version": integrated.get("schema_version"),
                "status": integrated.get("status"),
                "current_status": current.get("status"),
                "forecast_status": forecast.get("status"),
                "facility_campaign_status": facility_campaign_status,
                "forecast_facility_campaign_status": forecast_facility_campaign_status,
                "timing": dict(integrated_timing) if isinstance(integrated_timing, Mapping) else None,
                "integrated_timing_valid": integrated_timing_valid,
                "current_component_count": len(current_component_ids)
                if isinstance(current_component_ids, list)
                else None,
                "forecast_component_count": len(forecast_component_ids)
                if isinstance(forecast_component_ids, list)
                else None,
                "shared_component_scenario_key_count": len(scoped_keys)
                if isinstance(scoped_keys, list)
                else None,
                "policy": dict(policy),
            },
            "integrated current/forecast HAZOP ledger is missing scoped identity, timing-path policy, or fail-closed promotion controls",
        )
        integrated_check["diagnostic_only"] = True
        integrated_check["interpretation"] = (
            "The integrated ledger proves that measured and predicted HAZOP paths can be joined by "
            "equipment-scoped identity. It does not qualify provider releases, infer frequency, "
            "validate physics, or promote facility IR/F-N."
        )
        checks.append(integrated_check)
    if realtime_hazop_mode_trace is not None:
        trace = realtime_hazop_mode_trace
        policy = trace.get("policy")
        policy = policy if isinstance(policy, Mapping) else {}
        rows = trace.get("rows")
        trace_valid = (
            trace.get("schema_version") == "prism.realtime_hazop_mode_trace_audit.v1"
            and trace.get("status") == "REALTIME_HAZOP_MODE_TRACE_VERIFIED"
            and trace.get("diagnostic_only") is True
            and isinstance(rows, list)
            and bool(rows)
            and all(
                isinstance(row, Mapping)
                and isinstance(row.get("component_id"), str)
                and isinstance(row.get("operating_mode"), str)
                and bool(row.get("operating_mode"))
                and row.get("mode_match") is True
                for row in rows
            )
            and policy.get("mode_is_identity_metadata") is True
            and policy.get("frequency_inference_performed") is False
            and policy.get("sensor_frequency_learning_used") is False
            and policy.get("release_inference_performed") is False
            and policy.get("physical_validation_claim") is False
            and policy.get("facility_qra_claim") is False
            and policy.get("diagnostic_only") is True
            and not trace.get("blocking_reasons")
        )
        trace_check = _check(
            "diagnostic_realtime_hazop_mode_trace",
            trace_valid,
            {
                "record": realtime_hazop_mode_trace.get("_record_path"),
                "schema_version": realtime_hazop_mode_trace.get("schema_version"),
                "status": realtime_hazop_mode_trace.get("status"),
                "row_count": len(rows) if isinstance(rows, list) else None,
                "operating_mode_counts": realtime_hazop_mode_trace.get("operating_mode_counts"),
                "blocking_reasons": realtime_hazop_mode_trace.get("blocking_reasons"),
                "policy": dict(policy),
            },
            "realtime HAZOP operating-mode trace is missing, inconsistent, or carries an unsafe promotion claim",
        )
        trace_check["diagnostic_only"] = True
        trace_check["interpretation"] = (
            "The selected HAZOP mode is checked at the realtime result boundary and in the "
            "facility batch ledger. This diagnostic check never infers a release or frequency "
            "and never promotes facility QRA."
        )
        checks.append(trace_check)
    if external_document_evidence is not None:
        document_evidence = external_document_evidence
        policy = document_evidence.get("promotion_policy")
        policy = policy if isinstance(policy, Mapping) else {}
        document_count = document_evidence.get("document_count")
        document_check_valid = (
            document_evidence.get("schema_version") == "prism.external_document_evidence_audit.v1"
            and document_evidence.get("status") == "CANDIDATE_EQUIPMENT_PHYSICAL_EVIDENCE_NO_PROMOTION"
            and document_evidence.get("diagnostic_only") is True
            and isinstance(document_count, int)
            and document_count > 0
            and document_evidence.get("physical_validation_claim") is False
            and document_evidence.get("provider_release_packet_claim") is False
            and document_evidence.get("frequency_inference_performed") is False
            and document_evidence.get("facility_qra_claim") is False
            and policy.get("document_is_not_provider_release_packet") is True
            and policy.get("document_is_not_frequency_evidence") is True
            and policy.get("comparison_required_before_physical_validation") is True
            and policy.get("comparison_must_be_independent_and_holdout_scored") is True
            and policy.get("facility_qra_requires_complete_case_coverage") is True
        )
        document_check = _check(
            "diagnostic_external_document_evidence",
            document_check_valid,
            {
                "record": document_evidence.get("_record_path"),
                "schema_version": document_evidence.get("schema_version"),
                "status": document_evidence.get("status"),
                "document_count": document_count,
                "physical_validation_claim": document_evidence.get("physical_validation_claim"),
                "provider_release_packet_claim": document_evidence.get("provider_release_packet_claim"),
                "frequency_inference_performed": document_evidence.get("frequency_inference_performed"),
                "facility_qra_claim": document_evidence.get("facility_qra_claim"),
                "policy": dict(policy),
            },
            "external document evidence is missing or carries an unsafe promotion claim",
        )
        document_check["diagnostic_only"] = True
        document_check["interpretation"] = (
            "External pump documents are tracked as candidate model-comparison sources. "
            "The audit does not create a release packet, frequency, physical-validation "
            "claim, or facility QRA result."
        )
        checks.append(document_check)
    if external_release_artifact_intake is not None:
        intake = external_release_artifact_intake
        policy = intake.get("promotion_policy")
        policy = policy if isinstance(policy, Mapping) else {}
        artifact_file_count = intake.get("artifact_file_count")
        release_row_count = intake.get("release_row_count")
        qualified_sidecar_row_count = intake.get("qualified_sidecar_row_count")
        closure_ready_row_count = intake.get("closure_ready_row_count")
        actual_origin_row_count = intake.get("actual_origin_row_count")
        synthetic_or_model_prediction_row_count = intake.get(
            "synthetic_or_model_prediction_row_count"
        )
        intake_check_valid = (
            intake.get("schema_version") == "prism.external_release_artifact_intake.v1"
            and intake.get("status") == "EXTERNAL_RELEASE_ARTIFACTS_REQUIRE_QUALIFICATION"
            and intake.get("diagnostic_only") is True
            and isinstance(artifact_file_count, int)
            and artifact_file_count > 0
            and isinstance(release_row_count, int)
            and release_row_count > 0
            and isinstance(qualified_sidecar_row_count, int)
            and 0 <= qualified_sidecar_row_count <= release_row_count
            and isinstance(closure_ready_row_count, int)
            and 0 <= closure_ready_row_count <= release_row_count
            and isinstance(actual_origin_row_count, int)
            and 0 <= actual_origin_row_count <= release_row_count
            and isinstance(synthetic_or_model_prediction_row_count, int)
            and 0 <= synthetic_or_model_prediction_row_count <= release_row_count
            and intake.get("error_count") == 0
            and isinstance(intake.get("artifacts"), list)
            and all(
                isinstance(row, Mapping)
                and row.get("diagnostic_only") is True
                for row in intake.get("artifacts", [])
                if row.get("release_count", 1) > 0
            )
            and policy.get("frequency_assigned") is False
            and policy.get("provider_release_packet_promoted") is False
            and policy.get("physical_validation_promoted") is False
            and policy.get("facility_qra_promoted") is False
            and policy.get("qualification_requires_exact_digest_bound_sidecar") is True
            and policy.get("provider_ports_never_substituted_for_frequency_ports") is True
        )
        intake_check = _check(
            "diagnostic_external_release_artifact_intake",
            intake_check_valid,
            {
                "record": intake.get("_record_path"),
                "schema_version": intake.get("schema_version"),
                "status": intake.get("status"),
                "artifact_file_count": artifact_file_count,
                "release_row_count": release_row_count,
                "qualification_file_count": intake.get("qualification_file_count"),
                "qualified_sidecar_row_count": qualified_sidecar_row_count,
                "closure_ready_row_count": closure_ready_row_count,
                "closure_status_counts": intake.get("closure_status_counts"),
                "actual_origin_row_count": actual_origin_row_count,
                "synthetic_or_model_prediction_row_count": synthetic_or_model_prediction_row_count,
                "error_count": intake.get("error_count"),
                "policy": dict(policy),
            },
            "external release artifact intake is missing, malformed, or carries an unsafe promotion claim",
        )
        intake_check["diagnostic_only"] = True
        intake_check["interpretation"] = (
            "External release-shaped JSON is inventoried with exact file digests and equipment/port "
            "identity. Synthetic or model-prediction rows remain diagnostic until a separate exact "
            "provider qualification sidecar is present; no frequency or facility QRA is inferred."
        )
        checks.append(intake_check)
    if facility_evidence_request is not None:
        request = facility_evidence_request
        current = request.get("current_assessment")
        current = current if isinstance(current, Mapping) else {}
        promotion_gate = request.get("promotion_gate")
        promotion_gate = promotion_gate if isinstance(promotion_gate, Mapping) else {}
        frequency_policy = request.get("frequency_policy")
        frequency_policy = frequency_policy if isinstance(frequency_policy, Mapping) else {}
        case_requests = request.get("case_requests")
        family_requests = request.get("family_requests")
        component_requests = request.get("component_requests")
        required_case_count = request.get("case_request_count")
        assessment_case_count = current.get("case_count")
        case_identity_complete = (
            isinstance(case_requests, list)
            and all(
                isinstance(row, Mapping)
                and isinstance(row.get("request_id"), str)
                and isinstance(row.get("event_id"), str)
                and isinstance(row.get("component_id"), str)
                and isinstance(row.get("current_status"), str)
                and (
                    (
                        isinstance(row.get("promotion_allowed_now"), bool)
                        and row.get("promotion_allowed_now") is False
                    )
                    or row.get("qualification_required") is True
                )
                for row in case_requests
            )
        )
        evidence_request_valid = (
            request.get("schema_version") == "prism.facility_evidence_request.v1"
            and request.get("status") == "OPEN_EVIDENCE_REQUEST"
            and request.get("scope") == "outdoor_major_accidents"
            and request.get("provider_export_schema_required") == "prism.external_accident_history.v1"
            and isinstance(required_case_count, int)
            and required_case_count > 0
            and isinstance(case_requests, list)
            and len(case_requests) == required_case_count
            and case_identity_complete
            and isinstance(family_requests, list)
            and bool(family_requests)
            and isinstance(component_requests, list)
            and bool(component_requests)
            and isinstance(request.get("blocking_reasons"), list)
            and bool(request.get("blocking_reasons"))
            and isinstance(assessment_case_count, int)
            and assessment_case_count == required_case_count
            and current.get("facility_total_risk_available") is False
            and current.get("complete_facility_qra_claim") is False
            and promotion_gate.get("qualified_provider_packet_required") is True
            and promotion_gate.get("exact_event_component_port_and_digest_match_required") is True
            and promotion_gate.get("independent_physical_validation_required") is True
            and promotion_gate.get("complete_declared_scope_required") is True
            and promotion_gate.get("facility_ir_fn_remains_withheld_until_all_true") is True
            and frequency_policy.get("infer_frequency_from_provider_or_sensor") is False
            and frequency_policy.get("reallocate_frequency_between_families") is False
        )
        request_check = _check(
            "diagnostic_facility_evidence_request_coverage",
            evidence_request_valid,
            {
                "record": request.get("_record_path"),
                "schema_version": request.get("schema_version"),
                "status": request.get("status"),
                "case_request_count": required_case_count,
                "assessment_case_count": assessment_case_count,
                "family_request_count": len(family_requests) if isinstance(family_requests, list) else None,
                "component_request_count": len(component_requests) if isinstance(component_requests, list) else None,
                "blocking_reason_count": len(request.get("blocking_reasons", []))
                if isinstance(request.get("blocking_reasons"), list)
                else None,
                "case_identity_complete": case_identity_complete,
                "facility_total_risk_available": current.get("facility_total_risk_available"),
                "complete_facility_qra_claim": current.get("complete_facility_qra_claim"),
                "promotion_gate": dict(promotion_gate),
                "frequency_policy": dict(frequency_policy),
            },
            "facility evidence request catalog is missing exact case coverage or carries an unsafe promotion policy",
        )
        request_check["diagnostic_only"] = True
        request_check["interpretation"] = (
            "The evidence-request catalog makes each missing facility case actionable and preserves its "
            "promotion gate. It requests provider evidence but never invents termination, inventory, "
            "frequency or facility IR/F-N."
        )
        checks.append(request_check)
    blocking = [check["blocking_reason"] for check in checks if check["blocking_reason"]]
    complete = not blocking
    return {
        "schema_version": "prism.ijhe_completion_audit.v1",
        "status": "READY_FOR_IJHE_SCOPE" if complete else "INCOMPLETE_EVIDENCE",
        "checks": checks,
        "blocking_reasons": blocking,
        "physical_validation_claim": False if not complete else True,
        "complete_facility_qra_claim": complete,
        "interpretation": "Readiness evidence gate; a blocked check is not treated as zero risk or as an implicit accident substitution.",
    }
