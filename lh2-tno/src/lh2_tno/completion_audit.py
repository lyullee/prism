"""Fail-closed IJHE readiness audit for one PRISM campaign.

This module does not certify a QRA.  It collects the existing evidence ledgers
and states whether the declared scope can be presented as complete.  Missing
physical validation, missing accident families, or withheld facility risk are
blocking evidence rather than a zero-valued result.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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
                or packet_ledger.get("exact_worklist_event_count") == expected_worklist_packets
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
        )
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
                },
                "interpretation": (
                    "Saved external-model packets cover only the exact-matched worklist subset; "
                    "this diagnostic evidence does not close the missing events or qualify the "
                    "provider packets."
                ),
            }
        )
    if diagnostic_campaign_binding is not None:
        binding = diagnostic_campaign_binding
        packet_count = binding.get("packet_event_count")
        event_match_count = binding.get("packet_event_to_campaign_event_match_count")
        case_match_count = binding.get("packet_event_to_campaign_case_match_count")
        atom_match_count = binding.get("packet_event_to_campaign_risk_atom_match_count")
        campaign_binding_valid = (
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
                    "packet_identity_consumed": binding.get("packet_identity_consumed"),
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
                    "The campaign may preserve provider packet identity metadata, but equality with the "
                    "packet-evidence files must still be proven; packet time histories remain unconsumed "
                    "evidence and the result stays diagnostic-only."
                ),
            }
        )
    if facility_assessment is not None:
        assessment = facility_assessment
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
        vertical_valid = (
            isinstance(vertical.get("status"), str)
            and vertical.get("status", "").startswith("PARTIAL_DECLARED_SCOPE")
            and vertical.get("generated_events") == 5
            and isinstance(vertical.get("executed_cases"), int)
            and vertical.get("executed_cases") > 0
            and vertical.get("provider_vertical_handoff_consumed") is True
            and vertical.get("operator_limited") is True
            and vertical.get("facility_total_risk_withheld") is True
            and vertical.get("physical_validation_claim") is False
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
                    "generated_events": vertical.get("generated_events"),
                    "executed_cases": vertical.get("executed_cases"),
                    "provider_vertical_handoff_consumed": vertical.get(
                        "provider_vertical_handoff_consumed"
                    ),
                    "operator_limited": vertical.get("operator_limited"),
                    "facility_total_risk_withheld": vertical.get(
                        "facility_total_risk_withheld"
                    ),
                    "physical_validation_claim": vertical.get("physical_validation_claim"),
                },
                "interpretation": (
                    "A separate vertical-to-horizontal provider handoff diagnostic consumed a "
                    "declared handoff boundary; it is not merged into the generic facility scope "
                    "or promoted to a qualified vertical accident family."
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
    checks.extend([
        _check(
            "equipment_model_binding_to_accident_release",
            current_status.get("equipment_model_binding_status") == "ACCIDENT_RELEASE_INTERFACE_BOUND"
            and isinstance(current_status.get("equipment_model_binding_component_count"), int)
            and current_status.get("equipment_model_binding_component_count") > 0
            and current_status.get("equipment_model_binding_accident_release_supported_component_count")
            == current_status.get("equipment_model_binding_component_count"),
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
            },
            "one or more equipment models lacks an accident-release interface and provider termination ledger",
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
                "qualified_provider_packet_count": (
                    diagnostic_worklist_evidence.get("qualified_provider_packet_count")
                    if isinstance(diagnostic_worklist_evidence, Mapping)
                    else None
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
            },
            "one or more declared accident families are missing, partial, or uncomputed",
        ),
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
