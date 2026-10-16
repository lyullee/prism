"""Map the IJHE development objective to explicit PRISM evidence gates.

The regular completion audit is deliberately fail-closed for a qualified
facility QRA.  This module adds a second, explanatory ledger: it distinguishes
the conditional diagnostic chain that has actually executed from evidence
that is still required before the same result may be called a qualified,
site-specific facility QRA.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _record_path(value: Mapping[str, Any] | None, fallback: str | None) -> str | None:
    if isinstance(value, Mapping) and isinstance(value.get("_record_path"), str):
        return value["_record_path"]
    return fallback


def _row(
    requirement_id: str,
    requirement: str,
    status: str,
    *,
    evidence_paths: Sequence[str | None] = (),
    observed: Mapping[str, Any] | None = None,
    blocking_reason: str | None = None,
    interpretation: str = "",
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "requirement": requirement,
        "status": status,
        "evidence_paths": [str(path) for path in evidence_paths if path],
        "observed": dict(observed or {}),
        "blocking_reason": blocking_reason,
        "interpretation": interpretation,
    }


def build_ijhe_objective_coverage_audit(
    *,
    union_verification: Mapping[str, Any],
    completion_audit: Mapping[str, Any],
    scope_matrix: Mapping[str, Any],
    facility_assessment: Mapping[str, Any],
    native_catalog_verification: Mapping[str, Any],
    state_snapshot_audit: Mapping[str, Any],
    native_packet_evidence: Mapping[str, Any],
    native_packet_campaign_ledger: Mapping[str, Any],
    slabx_validation_evidence: Mapping[str, Any] | None = None,
    validation_evidence_matrix: Mapping[str, Any] | None = None,
    realtime_cache_benchmark: Mapping[str, Any] | None = None,
    native_state_snapshot_campaign_ledger: Mapping[str, Any] | None = None,
    extension_state_snapshot_coverage: Mapping[str, Any] | None = None,
    observed_state_replay_audit: Mapping[str, Any] | None = None,
    observed_state_runtime_frames: Mapping[str, Any] | None = None,
    observed_state_model_binding_audit: Mapping[str, Any] | None = None,
    inspection_center_source_inventory: Mapping[str, Any] | None = None,
    external_field_evidence: Mapping[str, Any] | None = None,
    external_field_model_comparison: Mapping[str, Any] | None = None,
    validation_intake_audit: Mapping[str, Any] | None = None,
    external_equipment_model_audit: Mapping[str, Any] | None = None,
    equipment_scenario_coverage_audit: Mapping[str, Any] | None = None,
    equipment_frequency_binding_audit: Mapping[str, Any] | None = None,
    generic_equipment_scenario_coverage_audit: Mapping[str, Any] | None = None,
    generic_equipment_frequency_binding_audit: Mapping[str, Any] | None = None,
    generic_provider_closure_audit: Mapping[str, Any] | None = None,
    generic_provider_evidence_requests: Mapping[str, Any] | None = None,
    generic_provider_evidence_audit: Mapping[str, Any] | None = None,
    release_closure_worklist: Mapping[str, Any] | None = None,
    external_release_artifact_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an objective-by-objective, fail-closed evidence ledger.

    ``CONDITIONALLY_COMPLETE`` means that the numerical diagnostic path is
    closed for the declared synthetic/outdoor scope, while one or more
    qualification gates remain open.  It never changes the status of the
    regular IJHE completion audit and never promotes a provider packet.
    """
    union_path = _record_path(union_verification, None)
    completion_path = _record_path(completion_audit, None)
    scope_path = _record_path(scope_matrix, None)
    facility_path = _record_path(facility_assessment, None)
    catalog_path = _record_path(native_catalog_verification, None)
    snapshot_path = _record_path(state_snapshot_audit, None)
    packet_path = _record_path(native_packet_evidence, None)
    campaign_path = _record_path(native_packet_campaign_ledger, None)
    union_state_campaign_path = _record_path(native_state_snapshot_campaign_ledger, None)
    slabx_path = _record_path(slabx_validation_evidence, None)
    validation_path = _record_path(validation_evidence_matrix, None)
    benchmark_path = _record_path(realtime_cache_benchmark, None)
    extension_state_path = _record_path(extension_state_snapshot_coverage, None)
    observed_replay_path = _record_path(observed_state_replay_audit, None)
    observed_runtime_path = _record_path(observed_state_runtime_frames, None)
    observed_model_binding_path = _record_path(observed_state_model_binding_audit, None)
    inspection_center_source_inventory_path = _record_path(
        inspection_center_source_inventory, None
    )
    external_field_path = _record_path(external_field_evidence, None)
    external_field_comparison_path = _record_path(external_field_model_comparison, None)
    validation_intake_path = _record_path(validation_intake_audit, None)
    external_equipment_model_path = _record_path(external_equipment_model_audit, None)
    equipment_scenario_coverage_path = _record_path(equipment_scenario_coverage_audit, None)
    equipment_frequency_binding_path = _record_path(equipment_frequency_binding_audit, None)
    generic_equipment_scenario_coverage_path = _record_path(
        generic_equipment_scenario_coverage_audit, None
    )
    generic_equipment_frequency_binding_path = _record_path(
        generic_equipment_frequency_binding_audit, None
    )
    generic_provider_evidence_requests_path = _record_path(
        generic_provider_evidence_requests, None
    )
    generic_provider_closure_path = _record_path(
        generic_provider_closure_audit, None
    )
    generic_provider_evidence_audit_path = _record_path(
        generic_provider_evidence_audit, None
    )
    release_closure_worklist_path = _record_path(release_closure_worklist, None)
    external_release_artifact_intake_path = _record_path(
        external_release_artifact_intake, None
    )
    union_event_count = _int(union_verification.get("merged_event_count"))
    union_state_campaign_reconciliation = (
        native_state_snapshot_campaign_ledger.get("state_snapshot_campaign_reconciliation", {})
        if isinstance(native_state_snapshot_campaign_ledger, Mapping)
        else {}
    )
    if not isinstance(union_state_campaign_reconciliation, Mapping):
        union_state_campaign_reconciliation = {}
    union_state_campaign_event_count = _int(
        native_state_snapshot_campaign_ledger.get("event_count")
        if isinstance(native_state_snapshot_campaign_ledger, Mapping)
        else None
    )
    union_state_campaign_bound_count = _int(
        union_state_campaign_reconciliation.get("bound_event_count")
    )
    extension_state_event_count = _int(
        extension_state_snapshot_coverage.get("event_count")
        if isinstance(extension_state_snapshot_coverage, Mapping)
        else None
    )
    extension_state_bound_count = _int(
        extension_state_snapshot_coverage.get("bound_event_count")
        if isinstance(extension_state_snapshot_coverage, Mapping)
        else None
    )
    extension_state_unbound_count = _int(
        extension_state_snapshot_coverage.get("unbound_event_count")
        if isinstance(extension_state_snapshot_coverage, Mapping)
        else None
    )

    catalog_events = _int(native_catalog_verification.get("frequency_event_count"))
    exact_packets = _int(native_catalog_verification.get("exact_native_packet_count"))
    catalog_uncomputed = _int(native_catalog_verification.get("uncomputed_event_count"))
    snapshot_records = _int(state_snapshot_audit.get("record_count"))
    snapshot_bound = _int(state_snapshot_audit.get("bound_count"))
    snapshot_unbound = _int(state_snapshot_audit.get("unbound_count"))
    packet_events = _int(native_packet_evidence.get("event_count"))
    packet_exact = _int(native_packet_evidence.get("exact_event_count"))
    campaign_events = _int(native_packet_campaign_ledger.get("event_count"))
    campaign_cases = _int(native_packet_campaign_ledger.get("case_count"))
    campaign_executed = _int(native_packet_campaign_ledger.get("chain_executed_case_count"))
    campaign_uncomputed = _int(native_packet_campaign_ledger.get("uncomputed_case_count"))
    facility_coverage = facility_assessment.get("conditional_diagnostic_facility_coverage")
    if not isinstance(facility_coverage, Mapping):
        facility_coverage = {}
    risk_atoms = _int(facility_coverage.get("risk_atom_count"))
    conditional_risk = facility_assessment.get("conditional_diagnostic_facility_risk_available") is True
    fn_curve = facility_assessment.get("conditional_diagnostic_facility_expected_death_fn_low_high")
    population = facility_assessment.get("population_accounting")
    scenario = facility_assessment.get("scenario_branch_accounting")
    uncertainty = facility_assessment.get("frequency_uncertainty")
    uncertainty_scenarios = (
        len(uncertainty.get("scenarios", []))
        if isinstance(uncertainty, Mapping) and isinstance(uncertainty.get("scenarios"), list)
        else 0
    )
    # The facility ledger calls this ``cross_product_count``.  Accept the
    # explanatory alias used by older hand-authored evidence fixtures, but
    # require a positive count and zero missing-dimension atoms before the
    # weather/ignition/population requirement can be marked complete.
    scenario_cross_product_count = (
        _int(scenario.get("scenario_cross_product_count"))
        if isinstance(scenario, Mapping)
        else None
    )
    if scenario_cross_product_count is None and isinstance(scenario, Mapping):
        scenario_cross_product_count = _int(scenario.get("cross_product_count"))
    scenario_missing_dimension_atom_count = (
        _int(scenario.get("missing_dimension_atom_count"))
        if isinstance(scenario, Mapping)
        else None
    )
    scope_rows = scope_matrix.get("rows", [])
    if not isinstance(scope_rows, list):
        scope_rows = []
    scope_not_numerically_executed = sum(
        int(row.get("not_numerically_executed_case_count", 0) or 0)
        for row in scope_rows
        if isinstance(row, Mapping)
    )
    scope_qualified_evidence_withheld = sum(
        int(row.get("qualified_evidence_withheld_case_count", 0) or 0)
        for row in scope_rows
        if isinstance(row, Mapping)
    )
    scope_numerically_executed = sum(
        int(row.get("numerically_executed_case_count", row.get("conditional_executed_case_count", 0)) or 0)
        for row in scope_rows
        if isinstance(row, Mapping)
    )

    rows: list[dict[str, Any]] = []

    state_ok = (
        catalog_events is not None
        and exact_packets == catalog_events
        and catalog_uncomputed == 0
        and state_snapshot_audit.get("status") == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
        and snapshot_records == catalog_events
        and snapshot_bound == catalog_events
        and snapshot_unbound == 0
    )
    rows.append(_row(
        "equipment_state_to_native_release",
        "설비 상태 원문이 각 native 방출 packet에 전달되고 provider echo로 확인되어야 한다",
        "PASS" if state_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(catalog_path, snapshot_path),
        observed={
            "catalog_event_count": catalog_events,
            "exact_native_packet_count": exact_packets,
            "catalog_uncomputed_event_count": catalog_uncomputed,
            "state_snapshot_record_count": snapshot_records,
            "state_snapshot_bound_count": snapshot_bound,
            "state_snapshot_unbound_count": snapshot_unbound,
            "state_snapshot_status": state_snapshot_audit.get("status"),
        },
        blocking_reason=None if state_ok else "native packet 또는 상태 snapshot echo가 전체 사건에 대해 닫히지 않았다",
        interpretation="24개 일반 LH2 사건에서 canonical state snapshot digest와 provider echo를 대조한다.",
    ))

    chain_ok = (
        native_packet_evidence.get("status") == "EXACT_NATIVE_SCOPE_PACKET_EVIDENCE"
        and packet_events is not None
        and packet_exact == packet_events
        and campaign_events == packet_events
        and campaign_cases == packet_events
        and campaign_executed == packet_events
        and campaign_uncomputed == 0
        and native_packet_campaign_ledger.get("packet_identity_consumed") is True
        and native_packet_campaign_ledger.get("state_snapshot_campaign_reconciliation", {}).get("status")
        == "STATE_SNAPSHOT_CAMPAIGN_RECONCILED"
    )
    rows.append(_row(
        "native_release_to_consequence_chain",
        "native 방출이 지속시간·재고/차단 경계를 거쳐 SLABx-LH2와 최종 피해 계산까지 도달해야 한다",
        "CONDITIONALLY_COMPLETE" if chain_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(packet_path, campaign_path, union_path),
        observed={
            "packet_event_count": packet_events,
            "packet_exact_event_count": packet_exact,
            "campaign_event_count": campaign_events,
            "campaign_case_count": campaign_cases,
            "campaign_chain_executed_case_count": campaign_executed,
            "campaign_uncomputed_case_count": campaign_uncomputed,
            "campaign_status": native_packet_campaign_ledger.get("status"),
            "risk_atom_count": risk_atoms,
        },
        blocking_reason=None if chain_ok else "native packet, campaign case, snapshot reconciliation 중 하나가 전체 사건에 대해 일치하지 않는다",
        interpretation="수치 chain은 닫혔지만 19개 case가 operator-limited이고 packet은 qualified provider 증거가 아니다.",
    ))

    damage_ok = conditional_risk and isinstance(fn_curve, list) and isinstance(risk_atoms, int) and risk_atoms > 0
    rows.append(_row(
        "release_to_final_damage",
        "방출에서 확산·점화·화재/폭발·수용점 피해와 IR/F-N 진단까지 이어져야 한다",
        "CONDITIONALLY_COMPLETE" if damage_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(facility_path, union_path),
        observed={
            "conditional_facility_risk_available": conditional_risk,
            "conditional_fn_curve_available": isinstance(fn_curve, list),
            "conditional_risk_atom_count": risk_atoms,
            "facility_total_risk_available": facility_assessment.get("facility_total_risk_available"),
        },
        blocking_reason=None if damage_ok else "조건부 시설 피해 결과가 없거나 risk atom/F-N 진단이 없다",
        interpretation="worker-01 수용점의 조건부 IR/F-N은 계산되지만 시설 전체 QRA 승격은 별도 gate다.",
    ))

    slabx_checks = slabx_validation_evidence.get("checks") if isinstance(slabx_validation_evidence, Mapping) else None
    slabx_ok = (
        isinstance(slabx_validation_evidence, Mapping)
        and slabx_validation_evidence.get("schema_version") == "prism.slabx_lh2_validation_audit.v1"
        and slabx_validation_evidence.get("status") == "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE"
        and isinstance(slabx_checks, list)
        and bool(slabx_checks)
        and all(isinstance(row, Mapping) and row.get("status") == "PASS" for row in slabx_checks)
        and slabx_validation_evidence.get("physical_validation_claim") is False
        and slabx_validation_evidence.get("full_chain_validation_claim") is False
        and slabx_validation_evidence.get("facility_qra_claim") is False
        and slabx_validation_evidence.get("frequency_inference_performed") is False
    )
    slabx_metrics = slabx_validation_evidence.get("metrics") if isinstance(slabx_validation_evidence, Mapping) else None
    if not isinstance(slabx_metrics, Mapping):
        slabx_metrics = {}
    rows.append(_row(
        "slabx_lh2_component_consequence_validation",
        "SLABx-LH2의 극저온 풀·옥외 확산 구성요소 근거를 추적하되 전체 chain 검증과 분리해야 한다",
        "CONDITIONALLY_COMPLETE" if slabx_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(slabx_path,),
        observed={
            "slabx_status": slabx_validation_evidence.get("status") if isinstance(slabx_validation_evidence, Mapping) else None,
            "check_count": len(slabx_checks) if isinstance(slabx_checks, list) else None,
            "ffi_case_count": slabx_metrics.get("ffi_case_count"),
            "flacs_comparison_row_count": slabx_metrics.get("flacs_comparison_row_count"),
            "pool_radius_median_ratio": slabx_metrics.get("pool_radius_median_ratio"),
            "max_scenario_mass_residual_kg": slabx_metrics.get("max_scenario_mass_residual_kg"),
            "runtime_repeat_inventory_difference_kg": slabx_metrics.get("runtime_repeat_inventory_difference_kg"),
            "physical_validation_claim": slabx_validation_evidence.get("physical_validation_claim") if isinstance(slabx_validation_evidence, Mapping) else None,
        },
        blocking_reason=None if slabx_ok else "SLABx-LH2 구성요소 검증 장부가 없거나 restricted claim 경계를 만족하지 않는다",
        interpretation="구성요소 비교·재현성 근거는 피해영향 모델의 제한된 근거로 사용하지만 방출·점화·IR/F-N 전체 물리검증으로 승격하지 않는다.",
    ))

    frequency_ok = uncertainty_scenarios > 0 and facility_assessment.get("physical_validation_claim") is False
    frequency_uncertainty = facility_assessment.get("frequency_uncertainty")
    if not isinstance(frequency_uncertainty, Mapping):
        frequency_uncertainty = {}
    rows.append(_row(
        "literature_frequency_uncertainty",
        "문헌 빈도를 그대로 입력하되 여러 빈도 시나리오의 불확실성을 계산해야 한다",
        "CONDITIONALLY_COMPLETE" if frequency_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(facility_path, union_path),
        observed={
            "frequency_scenario_count": uncertainty_scenarios,
            "correlation_comparison_present": frequency_uncertainty.get(
                "correlation_comparison_present"
            ),
            "asset_rank_top_id_consistent": (
                frequency_uncertainty.get("asset_rank_stability", {}).get("top_id_consistent")
                if isinstance(frequency_uncertainty.get("asset_rank_stability"), Mapping)
                else None
            ),
            "scenario_family_rank_top_id_consistent": (
                frequency_uncertainty.get("scenario_family_rank_stability", {}).get("top_id_consistent")
                if isinstance(frequency_uncertainty.get("scenario_family_rank_stability"), Mapping)
                else None
            ),
            "frequency_inference_performed": union_verification.get("frequency_inference_performed", False),
            "physical_validation_claim": facility_assessment.get("physical_validation_claim"),
        },
        blocking_reason=None if frequency_ok else "문헌 빈도 시나리오가 없거나 물리검증과 빈도 추론 경계가 불명확하다",
        interpretation="현장 빈도 학습은 하지 않고 문헌 p05/중앙/p95 계열을 저장된 risk atom에 재가중한다.",
    ))

    population_ok = (
        isinstance(population, Mapping)
        and population.get("missing_condition_ids") == []
        and population.get("missing_population_condition_ids") == []
        and population.get("mismatched_receptor_ids") == {}
        and isinstance(scenario, Mapping)
        and scenario.get("status") == "EXPLICIT_BRANCH_ACCOUNTING"
        and scenario_cross_product_count is not None
        and scenario_cross_product_count > 0
        and scenario_missing_dimension_atom_count == 0
    )
    rows.append(_row(
        "weather_ignition_population",
        "기상·점화·인구 분기를 명시적으로 곱해 최종 피해를 계산해야 한다",
        "CONDITIONALLY_COMPLETE" if population_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(facility_path, union_path),
        observed={
            "population_accounting_status": population.get("status") if isinstance(population, Mapping) else None,
            "population_mismatch_count": len(population.get("mismatched_receptor_ids", {})) if isinstance(population, Mapping) else None,
            "annual_condition_count": population.get("annual_condition_count") if isinstance(population, Mapping) else None,
            "scenario_branch_status": scenario.get("status") if isinstance(scenario, Mapping) else None,
            "scenario_cross_product_count": scenario_cross_product_count,
            "scenario_missing_dimension_atom_count": scenario_missing_dimension_atom_count,
        },
        blocking_reason=None if population_ok else "연간조건·수용점·점화 branch accounting에 누락 또는 불일치가 있다",
        interpretation="현재 조건과 인구는 synthetic diagnostic이며 site weather/population qualification은 남아 있다.",
    ))

    scope_ok = scope_matrix.get("conditional_chain_complete") is True
    scope_gap_rows = scope_matrix.get("rows", [])
    if not isinstance(scope_gap_rows, list):
        scope_gap_rows = []
    scope_gap_rows = [
        {
            "family": row.get("family"),
            "gap_class": row.get("gap_class"),
            "case_status_counts": row.get("case_status_counts", {}),
            "gap_reasons": row.get("gap_reasons", []),
            "closure_requirements": row.get("closure_requirements", []),
        }
        for row in scope_gap_rows
        if isinstance(row, Mapping)
    ]
    rows.append(_row(
        "generic_lh2_scope",
        "탱크·배관·밸브·펌프·벤트·기화기·재액화기 등 일반 LH2 설비 사고 범위를 명시해야 한다",
        "CONDITIONALLY_COMPLETE" if scope_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(scope_path, union_path),
        observed={
            "required_family_count": len(scope_matrix.get("required_families", [])) if isinstance(scope_matrix.get("required_families"), list) else None,
            "scope_matrix_complete": scope_matrix.get("matrix_complete"),
            "conditional_chain_complete": scope_matrix.get("conditional_chain_complete"),
            "strict_partial_or_blocked_family_count": len(scope_matrix.get("blocking_reasons", [])) if isinstance(scope_matrix.get("blocking_reasons"), list) else None,
            "scope_not_numerically_executed_case_count": scope_not_numerically_executed,
            "scope_qualified_evidence_withheld_case_count": scope_qualified_evidence_withheld,
            "scope_numerically_executed_case_count": scope_numerically_executed,
            "facility_not_numerically_executed_case_count": facility_coverage.get(
                "not_numerically_executed_case_count"
            ),
            "facility_qualified_evidence_withheld_case_count": facility_coverage.get(
                "qualified_evidence_withheld_case_count"
            ),
            "facility_numerically_executed_case_count": facility_coverage.get(
                "numerically_executed_case_count"
            ),
            "scope_gap_summary": scope_matrix.get("gap_summary", {}),
            "scope_gap_rows": scope_gap_rows,
        },
        blocking_reason=None if scope_ok else "조건부 scope chain이 닫히지 않았다",
        interpretation="조건부 실행 범위는 닫혔지만 operator-limited family를 엄격한 complete facility scope로 승격하지 않는다.",
    ))

    realtime_mode_contract = (
        realtime_cache_benchmark.get("mode_contract")
        if isinstance(realtime_cache_benchmark, Mapping)
        else None
    )
    observed_modes = (
        realtime_mode_contract.get("observed_evaluation_modes")
        if isinstance(realtime_mode_contract, Mapping)
        else None
    )
    realtime_mode_contract_ok = (
        isinstance(realtime_mode_contract, Mapping)
        and realtime_mode_contract.get("schema") == "prism.realtime_mode_contract.v1"
        and isinstance(observed_modes, list)
        and set(observed_modes) == {
            "cached_diagnostic_1hz",
            "fresh_physics_background",
        }
        and realtime_mode_contract.get("fresh_physics_1hz_claim") is False
        and realtime_mode_contract.get("stale_fallback_used") is False
        and realtime_mode_contract.get("frequency_learning") is False
        and realtime_mode_contract.get("release_inference") is False
    )
    realtime_ok = (
        isinstance(realtime_cache_benchmark, Mapping)
        and realtime_cache_benchmark.get("cache_meets_one_hz_all_samples") is True
        and realtime_cache_benchmark.get("fresh_physics_meets_one_hz") is False
        and realtime_mode_contract_ok
    )
    rows.append(_row(
        "realtime_processing",
        "디지털 트윈 모니터링 입력에서 빠른 결과를 내고 신규 물리 계산의 시간을 별도로 보여줘야 한다",
        "CONDITIONALLY_COMPLETE" if realtime_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(benchmark_path, facility_path),
        observed={
            "cache_p95_ms": realtime_cache_benchmark.get("cache_p95_ms") if isinstance(realtime_cache_benchmark, Mapping) else None,
            "cache_meets_one_hz_all_samples": realtime_cache_benchmark.get("cache_meets_one_hz_all_samples") if isinstance(realtime_cache_benchmark, Mapping) else None,
            "fresh_physics_elapsed_ms": realtime_cache_benchmark.get("fresh_physics_elapsed_ms") if isinstance(realtime_cache_benchmark, Mapping) else None,
            "fresh_physics_meets_one_hz": realtime_cache_benchmark.get("fresh_physics_meets_one_hz") if isinstance(realtime_cache_benchmark, Mapping) else None,
            "persistent_fresh_physics": realtime_cache_benchmark.get("persistent_fresh_physics") if isinstance(realtime_cache_benchmark, Mapping) else None,
            "mode_contract_schema": realtime_mode_contract.get("schema") if isinstance(realtime_mode_contract, Mapping) else None,
            "mode_contract_observed_evaluation_modes": observed_modes,
            "mode_contract_valid": realtime_mode_contract_ok,
            "stale_fallback_used": realtime_mode_contract.get("stale_fallback_used") if isinstance(realtime_mode_contract, Mapping) else None,
            "frequency_learning": realtime_mode_contract.get("frequency_learning") if isinstance(realtime_mode_contract, Mapping) else None,
            "release_inference": realtime_mode_contract.get("release_inference") if isinstance(realtime_mode_contract, Mapping) else None,
        },
        blocking_reason=None if realtime_ok else "cache/fresh-physics 처리시간 또는 realtime mode contract가 유효하지 않다",
        interpretation="캐시 응답은 1 Hz 기준을 만족하지만 매 입력마다 새 SLABx 물리를 1 Hz로 계산한다는 뜻은 아니다. warm worker는 반복 시작 비용을 줄이는 진단 경로이며, 측정된 fresh physics 시간을 별도로 보존한다.",
    ))

    physical_ok = (
        isinstance(validation_evidence_matrix, Mapping)
        and validation_evidence_matrix.get("physical_validation_claim") is True
    )
    rows.append(_row(
        "independent_physical_validation",
        "실증 또는 독립 실험으로 방출·확산·피해 계산을 검증해야 한다",
        "PASS" if physical_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(validation_path,),
        observed={
            "validation_matrix_status": validation_evidence_matrix.get("status") if isinstance(validation_evidence_matrix, Mapping) else None,
            "physical_validation_claim": validation_evidence_matrix.get("physical_validation_claim") if isinstance(validation_evidence_matrix, Mapping) else None,
            "facility_qra_claim": validation_evidence_matrix.get("facility_qra_claim") if isinstance(validation_evidence_matrix, Mapping) else None,
        },
        blocking_reason=None if physical_ok else "현재 evidence matrix는 제한 근거이며 독립 물리검증 claim을 열지 않았다",
        interpretation="액화수소검사지원센터 자료와 실험 자료는 후보 근거로 보존되지만 사고 방출 검증으로 자동 승격하지 않는다.",
    ))

    qualified_count = native_packet_campaign_ledger.get("qualified_provider_packet_count")
    qualified_ok = (
        isinstance(qualified_count, int)
        and not isinstance(qualified_count, bool)
        and qualified_count > 0
        and native_packet_campaign_ledger.get("provider_packet_promoted") is True
    )
    rows.append(_row(
        "qualified_provider_evidence",
        "각 facility case에 exact qualified provider packet이 있어야 한다",
        "PASS" if qualified_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(campaign_path, packet_path, completion_path),
        observed={
            "provider_packet_case_count": native_packet_campaign_ledger.get("provider_packet_case_count"),
            "qualified_provider_packet_case_count": native_packet_campaign_ledger.get("qualified_provider_packet_case_count"),
            "provider_packet_promoted": native_packet_campaign_ledger.get("provider_packet_promoted"),
        },
        blocking_reason=None if qualified_ok else "현재 packet은 native diagnostic packet이며 qualified provider packet은 0건이다",
        interpretation="이 gate가 닫히기 전까지 결과는 조건부 진단 결과로만 표시한다.",
    ))

    strict_scope_ok = scope_matrix.get("matrix_complete") is True
    rows.append(_row(
        "strict_facility_scope",
        "선언한 주요사고 범위가 모든 설비·사고 family에 대해 엄격히 complete여야 한다",
        "PASS" if strict_scope_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(scope_path, completion_path),
        observed={
            "scope_matrix_complete": scope_matrix.get("matrix_complete"),
            "blocking_reasons": scope_matrix.get("blocking_reasons", []),
            "conditional_chain_complete": scope_matrix.get("conditional_chain_complete"),
        },
        blocking_reason=None if strict_scope_ok else "strict scope matrix에 PARTIAL family가 남아 있어 조건부 chain만 계산한다",
        interpretation="PARTIAL은 수치 실행 실패가 아니라 operator-limited/qualification 근거가 부족하다는 표지다.",
    ))

    strict_qra_ok = (
        facility_assessment.get("facility_total_risk_available") is True
        and facility_assessment.get("complete_facility_qra_claim") is True
    )
    rows.append(_row(
        "strict_facility_qra",
        "시설 전체 IR/F-N을 qualified QRA 결과로 승격해야 한다",
        "PASS" if strict_qra_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(facility_path, completion_path),
        observed={
            "facility_total_risk_available": facility_assessment.get("facility_total_risk_available"),
            "complete_facility_qra_claim": facility_assessment.get("complete_facility_qra_claim"),
            "conditional_diagnostic_facility_risk_available": conditional_risk,
        },
        blocking_reason=None if strict_qra_ok else "qualified provider·strict scope·독립검증 gate가 닫히지 않아 facility IR/F-N을 보류한다",
        interpretation="조건부 IR/F-N 값은 존재하지만 시설 전체 QRA라는 표현은 사용하지 않는다.",
    ))

    extension_state_ok = (
        isinstance(extension_state_snapshot_coverage, Mapping)
        and extension_state_snapshot_coverage.get("status")
        == "EXTENSION_STATE_SNAPSHOT_COVERAGE_COMPLETE"
        and extension_state_event_count is not None
        and extension_state_bound_count == extension_state_event_count
        and extension_state_unbound_count == 0
    )
    union_state_ok = (
        isinstance(native_state_snapshot_campaign_ledger, Mapping)
        and native_state_snapshot_campaign_ledger.get("status")
        == "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED"
        and union_state_campaign_reconciliation.get("status")
        == "STATE_SNAPSHOT_CAMPAIGN_RECONCILED"
        and union_event_count is not None
        and (
            (
                isinstance(extension_state_snapshot_coverage, Mapping)
                and extension_state_event_count is not None
                and union_state_campaign_event_count is not None
                and union_state_campaign_bound_count is not None
                and union_state_campaign_event_count + extension_state_event_count
                == union_event_count
                and union_state_campaign_bound_count + (extension_state_bound_count or 0)
                == union_event_count
            )
            or (
                not isinstance(extension_state_snapshot_coverage, Mapping)
                and union_state_campaign_event_count == union_event_count
                and union_state_campaign_bound_count == union_event_count
            )
        )
        and (
            extension_state_ok
            if isinstance(extension_state_snapshot_coverage, Mapping)
            else True
        )
    )
    rows.append(_row(
        "strict_facility_state_snapshot_coverage",
        "시설 전체 사건이 설비 상태 snapshot과 native 방출 결과 digest까지 일대일로 이어져야 한다",
        "PASS" if union_state_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(union_state_campaign_path, extension_state_path, union_path),
        observed={
            "union_event_count": union_event_count,
            "state_snapshot_campaign_status": (
                native_state_snapshot_campaign_ledger.get("status")
                if isinstance(native_state_snapshot_campaign_ledger, Mapping)
                else None
            ),
            "state_snapshot_campaign_event_count": union_state_campaign_event_count,
            "state_snapshot_campaign_bound_event_count": union_state_campaign_bound_count,
            "provider_result_digest_mismatch_event_ids": union_state_campaign_reconciliation.get(
                "provider_result_digest_mismatch_event_ids", []
            ),
            "extension_state_snapshot_coverage_status": (
                extension_state_snapshot_coverage.get("status")
                if isinstance(extension_state_snapshot_coverage, Mapping)
                else None
            ),
            "extension_state_snapshot_event_count": extension_state_event_count,
            "extension_state_snapshot_bound_event_count": extension_state_bound_count,
            "extension_state_snapshot_unbound_event_count": extension_state_unbound_count,
            "extension_state_snapshot_missing_event_ids": (
                extension_state_snapshot_coverage.get("missing_event_ids", [])
                if isinstance(extension_state_snapshot_coverage, Mapping)
                else []
            ),
        },
        blocking_reason=None if union_state_ok else (
            "base native campaign의 상태 snapshot은 확인되지만 vertical-handoff와 inventory-depletion "
            "확장 사건까지 시설 전체 상태 연결이 닫히지 않았다; 확장 사건별 canonical state snapshot이 필요하다"
        ),
        interpretation=(
            "시설 전체 gate는 확장 사건별 상태 snapshot와 provider result digest까지 확인될 때만 통과한다. "
            "부분 연결을 전체 연결로 승격하지 않는다."
        ),
    ))

    observed_replay_ok = (
        isinstance(observed_state_replay_audit, Mapping)
        and observed_state_replay_audit.get("schema_version")
        == "prism.observed_state_source_replay_audit.v1"
        and observed_state_replay_audit.get("status") == "SOURCE_REPLAY_MATCHED"
        and isinstance(observed_state_replay_audit.get("source_count"), int)
        and observed_state_replay_audit.get("source_count", 0) > 0
        and observed_state_replay_audit.get("matched_source_count")
        == observed_state_replay_audit.get("source_count")
        and observed_state_replay_audit.get("evidence_policy_valid") is True
        and (
            observed_state_replay_audit.get("regeneration", {}).get(
                "canonical_digest_match"
            )
            in {True, None}
        )
    )
    rows.append(_row(
        "diagnostic_observed_state_source_replay",
        "실증 상태자료의 원문 해시와 상태 장부 재생성이 일치해야 한다",
        "PASS" if observed_replay_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(observed_replay_path,),
        observed={
            "source_count": (
                observed_state_replay_audit.get("source_count")
                if isinstance(observed_state_replay_audit, Mapping)
                else None
            ),
            "matched_source_count": (
                observed_state_replay_audit.get("matched_source_count")
                if isinstance(observed_state_replay_audit, Mapping)
                else None
            ),
            "evidence_policy_valid": (
                observed_state_replay_audit.get("evidence_policy_valid")
                if isinstance(observed_state_replay_audit, Mapping)
                else None
            ),
            "regeneration": (
                observed_state_replay_audit.get("regeneration")
                if isinstance(observed_state_replay_audit, Mapping)
                else None
            ),
        },
        blocking_reason=None if observed_replay_ok else (
            "관측 상태 원문 해시 또는 상태 장부 재생성이 일치하지 않거나 "
            "state-only 정책이 확인되지 않았다"
        ),
        interpretation=(
            "원문 재생성 일치는 입력 무결성 근거다. 사고 방출·빈도·독립 물리검증·"
            "시설 IR/F-N으로 승격하지 않는다."
        ),
    ))

    runtime_policy = (
        observed_state_runtime_frames.get("policy", {})
        if isinstance(observed_state_runtime_frames, Mapping)
        else {}
    )
    runtime_frames = (
        observed_state_runtime_frames.get("frames", [])
        if isinstance(observed_state_runtime_frames, Mapping)
        else []
    )
    runtime_handoff_contract = (
        observed_state_runtime_frames.get("runtime_handoff_contract", {})
        if isinstance(observed_state_runtime_frames, Mapping)
        else {}
    )
    runtime_frames_ok = (
        isinstance(observed_state_runtime_frames, Mapping)
        and observed_state_runtime_frames.get("schema_version")
        == "prism.observed_state_runtime_frames.v1"
        and observed_state_runtime_frames.get("status") == "STATE_RUNTIME_FRAMES_READY"
        and isinstance(observed_state_runtime_frames.get("source_count"), int)
        and observed_state_runtime_frames.get("source_count", 0) > 0
        and observed_state_runtime_frames.get("frame_count")
        == observed_state_runtime_frames.get("source_count")
        and isinstance(runtime_frames, list)
        and len(runtime_frames) == observed_state_runtime_frames.get("frame_count")
        and isinstance(observed_state_runtime_frames.get("evidence_sample_count"), int)
        and observed_state_runtime_frames.get("evidence_sample_count", 0) > 0
        and all(
            isinstance(frame, Mapping)
            and isinstance(frame.get("component_id"), str)
            and isinstance(frame.get("frame_digest"), str)
            and isinstance(frame.get("state_snapshot_digest"), str)
            and isinstance(frame.get("values"), Mapping)
            and isinstance(frame.get("state_snapshot"), Mapping)
            for frame in runtime_frames
        )
        and runtime_handoff_contract.get("schema")
        == "prism.equipment_process_state.v1"
        and runtime_handoff_contract.get("state_adapter")
        == "service_state_from_runtime_frame"
        and runtime_handoff_contract.get("resolver_adapter")
        == "request_from_observed_state_runtime_frame"
        and runtime_handoff_contract.get("monitor_method")
        == "RealtimeConsequenceMonitor.update_from_runtime_frame"
        and runtime_handoff_contract.get("facility_monitor_method")
        == "FacilityRealtimeConsequenceMonitor.update_from_runtime_frames"
        and runtime_handoff_contract.get("runtime_clock")
        == "caller_supplied_now_s"
        and runtime_handoff_contract.get("provider_release_required_for_consequence") is True
        and runtime_handoff_contract.get("frequency_assignment")
        == "rejected_by_request_from_equipment_resolver"
        and runtime_policy.get("state_only") is True
        and runtime_policy.get("release_scenario_generated") is False
        and runtime_policy.get("frequency_inference_performed") is False
        and runtime_policy.get("sensor_frequency_learning_used") is False
        and runtime_policy.get("provider_packet_promoted") is False
        and runtime_policy.get("physical_validation_claim") is False
        and runtime_policy.get("facility_qra_claim") is False
        and runtime_policy.get("provider_release_required_for_consequence") is True
    )
    rows.append(_row(
        "diagnostic_observed_state_runtime_frames",
        "관측 상태를 실시간 정상상태 모델/provider resolver 입력으로 내보내되 사고 방출·빈도·QRA로 자동 승격하지 않아야 한다",
        "PASS" if runtime_frames_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(observed_runtime_path, observed_replay_path),
        observed={
            "source_count": (
                observed_state_runtime_frames.get("source_count")
                if isinstance(observed_state_runtime_frames, Mapping)
                else None
            ),
            "frame_count": (
                observed_state_runtime_frames.get("frame_count")
                if isinstance(observed_state_runtime_frames, Mapping)
                else None
            ),
            "evidence_sample_count": (
                observed_state_runtime_frames.get("evidence_sample_count")
                if isinstance(observed_state_runtime_frames, Mapping)
                else None
            ),
            "policy": runtime_policy,
            "runtime_handoff_contract": runtime_handoff_contract,
        },
        blocking_reason=None if runtime_frames_ok else (
            "실시간 상태 frame artifact가 없거나 source/frame 수·digest·state-only·시설 monitor "
            "계약이 검증되지 않았다"
        ),
        interpretation=(
            "상태 frame은 정상상태 모델과 provider resolver에 넘길 수 있는 실행 입력이다. "
            "provider가 방출 경계와 종료 조건을 반환하기 전에는 피해·빈도·시설 QRA를 계산하지 않는다."
        ),
    ))

    observed_model_binding_policy = (
        observed_state_model_binding_audit.get("policy", {})
        if isinstance(observed_state_model_binding_audit, Mapping)
        else {}
    )
    if not isinstance(observed_model_binding_policy, Mapping):
        observed_model_binding_policy = {}
    observed_model_binding_rows = (
        observed_state_model_binding_audit.get("rows", [])
        if isinstance(observed_state_model_binding_audit, Mapping)
        else []
    )
    if not isinstance(observed_model_binding_rows, list):
        observed_model_binding_rows = []
    observed_model_binding_ok = (
        isinstance(observed_state_model_binding_audit, Mapping)
        and observed_state_model_binding_audit.get("schema")
        == "prism.observed_state_model_binding_audit.v1"
        and observed_state_model_binding_audit.get("status")
        == "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY"
        and isinstance(observed_state_model_binding_audit.get("observed_component_count"), int)
        and observed_state_model_binding_audit.get("observed_component_count", 0) > 0
        and observed_state_model_binding_audit.get("state_model_bound_component_count")
        == observed_state_model_binding_audit.get("observed_component_count")
        and observed_state_model_binding_audit.get("diagnostic_release_adapter_component_count", 0)
        <= observed_state_model_binding_audit.get("state_model_bound_component_count", 0)
        and observed_state_model_binding_audit.get("facility_component_identity_resolved_count")
        == 0
        and observed_state_model_binding_audit.get("qualified_provider_packet_count") == 0
        and observed_model_binding_policy.get("normal_state_model_is_not_accident_release") is True
        and observed_model_binding_policy.get("diagnostic_adapter_is_not_qualified_provider") is True
        and observed_model_binding_policy.get("facility_component_identity_is_not_resolved") is True
        and observed_model_binding_policy.get("facility_identity_required_for_accident_binding") is True
        and observed_model_binding_policy.get("release_event_binding_is_not_created") is True
        and observed_model_binding_policy.get("frequency_is_not_assigned") is True
        and observed_model_binding_policy.get("facility_ir_fn_promotion") is False
        and observed_model_binding_policy.get("diagnostic_only") is True
        and len(observed_model_binding_rows)
        == observed_state_model_binding_audit.get("observed_component_count", 0)
        and all(
            isinstance(row, Mapping)
            and row.get("status") == "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"
            for row in observed_model_binding_rows
        )
    )
    if observed_state_model_binding_audit is not None:
        rows.append(_row(
            "diagnostic_observed_state_model_binding",
            "관측 정상상태 신호를 일반 액화수소 설비 모델에 연결하되 시설 identity·사고 방출·빈도와 분리해야 한다",
            "PASS" if observed_model_binding_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(observed_model_binding_path,),
            observed={
                "schema": (
                    observed_state_model_binding_audit.get("schema")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "status": (
                    observed_state_model_binding_audit.get("status")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "observed_component_count": (
                    observed_state_model_binding_audit.get("observed_component_count")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "state_model_bound_component_count": (
                    observed_state_model_binding_audit.get("state_model_bound_component_count")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "diagnostic_release_adapter_component_count": (
                    observed_state_model_binding_audit.get("diagnostic_release_adapter_component_count")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "facility_component_identity_resolved_count": (
                    observed_state_model_binding_audit.get("facility_component_identity_resolved_count")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "qualified_provider_packet_count": (
                    observed_state_model_binding_audit.get("qualified_provider_packet_count")
                    if isinstance(observed_state_model_binding_audit, Mapping)
                    else None
                ),
                "row_count": len(observed_model_binding_rows),
                "policy": dict(observed_model_binding_policy),
            },
            blocking_reason=None if observed_model_binding_ok else (
                "정상상태 모델 binding이 전체 관측 component에 닫히지 않았거나 "
                "사고 방출·빈도 승격 차단 정책이 확인되지 않았다"
            ),
            interpretation=(
                "센터 정상 운전 신호는 storage tank·vent·vaporizer 모델 입력 후보로만 연결한다. "
                "시설 P&ID identity와 provider accident history가 확인되기 전에는 방출·빈도·IR/F-N을 만들지 않는다."
            ),
        ))

    source_inventory_inventory = (
        inspection_center_source_inventory.get("inventory", {})
        if isinstance(inspection_center_source_inventory, Mapping)
        else {}
    )
    source_inventory_suitability = (
        inspection_center_source_inventory.get("evidence_suitability", {})
        if isinstance(inspection_center_source_inventory, Mapping)
        else {}
    )
    source_inventory_gates = (
        inspection_center_source_inventory.get("promotion_gates", {})
        if isinstance(inspection_center_source_inventory, Mapping)
        else {}
    )
    if not isinstance(source_inventory_inventory, Mapping):
        source_inventory_inventory = {}
    if not isinstance(source_inventory_suitability, Mapping):
        source_inventory_suitability = {}
    if not isinstance(source_inventory_gates, Mapping):
        source_inventory_gates = {}
    source_inventory_release = (
        source_inventory_suitability.get("accident_release_boundary", {})
        if isinstance(source_inventory_suitability, Mapping)
        else {}
    )
    source_inventory_frequency = (
        source_inventory_suitability.get("failure_frequency", {})
        if isinstance(source_inventory_suitability, Mapping)
        else {}
    )
    if not isinstance(source_inventory_release, Mapping):
        source_inventory_release = {}
    if not isinstance(source_inventory_frequency, Mapping):
        source_inventory_frequency = {}
    source_inventory_ok = (
        isinstance(inspection_center_source_inventory, Mapping)
        and inspection_center_source_inventory.get("schema_version")
        == "prism.inspection_center_source_inventory_suitability.v1"
        and inspection_center_source_inventory.get("status")
        == "NORMAL_OPERATION_SOURCE_SCREENED_DIAGNOSTIC_ONLY"
        and isinstance(source_inventory_inventory, Mapping)
        and source_inventory_inventory.get("workbook_count", 0) > 0
        and source_inventory_inventory.get("sheet_count", 0) > 0
        and isinstance(source_inventory_suitability, Mapping)
        and source_inventory_release.get("available") is False
        and source_inventory_frequency.get("available") is False
        and isinstance(source_inventory_gates, Mapping)
        and source_inventory_gates.get("frequency_applied") is False
        and source_inventory_gates.get("sensor_frequency_learning_used") is False
        and source_inventory_gates.get("provider_packet_qualified") is False
        and source_inventory_gates.get("facility_qra_claim") is False
        and source_inventory_gates.get("physical_validation_claim") is False
    )
    if inspection_center_source_inventory is not None:
        rows.append(_row(
            "diagnostic_inspection_center_source_suitability",
            "검사센터 시계열 자료를 상태·HAZOP 진단 입력으로만 사용하고 방출·빈도·물리검증·시설 QRA로 승격하지 않아야 한다",
            "PASS" if source_inventory_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(inspection_center_source_inventory_path,),
            observed={
                "schema_version": (
                    inspection_center_source_inventory.get("schema_version")
                    if isinstance(inspection_center_source_inventory, Mapping)
                    else None
                ),
                "status": (
                    inspection_center_source_inventory.get("status")
                    if isinstance(inspection_center_source_inventory, Mapping)
                    else None
                ),
                "workbook_count": source_inventory_inventory.get("workbook_count"),
                "sheet_count": source_inventory_inventory.get("sheet_count"),
                "accident_release_available": source_inventory_release.get("available"),
                "failure_frequency_available": source_inventory_frequency.get("available"),
                "promotion_gates": dict(source_inventory_gates)
                if isinstance(source_inventory_gates, Mapping)
                else {},
            },
            blocking_reason=None if source_inventory_ok else (
                "검사센터 source suitability record가 없거나 schema/status가 맞지 않거나 "
                "정상운전 자료의 사고 방출·빈도·시설 승격 차단이 확인되지 않았다"
            ),
            interpretation=(
                "검사센터 자료의 시간·상태 신호는 명시적 운전모드와 HAZOP 진단을 점검하는 데 사용한다. "
                "자료 자체로 누출량, 지속시간, 사고빈도 또는 시설 IR/F-N을 추정하지 않는다."
            ),
        ))

    # Keep this observation row outside the core and strict qualification
    # gates.  A field bundle is useful input for a later matched
    # model-to-measurement comparison, but it is not a provider release,
    # accident frequency, or facility-QRA qualification packet.
    external_status = (
        external_field_evidence.get("status")
        if isinstance(external_field_evidence, Mapping)
        else None
    )
    external_promotion_policy = (
        external_field_evidence.get("promotion_policy", {})
        if isinstance(external_field_evidence, Mapping)
        else {}
    )
    if not isinstance(external_promotion_policy, Mapping):
        external_promotion_policy = {}
    external_field_ok = (
        isinstance(external_field_evidence, Mapping)
        and external_field_evidence.get("schema_version") == "prism.external_field_evidence.v1"
        and external_status in {
            "RESTRICTED_EXTERNAL_FIELD_EVIDENCE",
            "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT",
        }
        and external_field_evidence.get("scope") == "lh2_free_field"
        and external_field_evidence.get("model_comparison_ready") is False
        and external_field_evidence.get("physical_validation_claim") is False
        and external_field_evidence.get("full_chain_validation_claim") is False
        and external_field_evidence.get("accident_release_validation_claim") is False
        and external_field_evidence.get("frequency_inference_performed") is False
        and external_field_evidence.get("facility_qra_claim") is False
        and external_promotion_policy.get("observed_source_is_not_provider_release") is True
        and external_promotion_policy.get("observed_data_is_not_frequency") is True
        and external_promotion_policy.get("matched_model_prediction_required_for_validation") is True
        and external_promotion_policy.get("component_evidence_does_not_validate_facility_qra") is True
    )
    source_summary = (
        external_field_evidence.get("source_boundary", {})
        if isinstance(external_field_evidence, Mapping)
        else {}
    )
    weather_summary = (
        external_field_evidence.get("weather", {})
        if isinstance(external_field_evidence, Mapping)
        else {}
    )
    receptor_summary = (
        external_field_evidence.get("receptor_observations", {})
        if isinstance(external_field_evidence, Mapping)
        else {}
    )
    hash_drift_channels = (
        external_field_evidence.get("hash_drift_channels", [])
        if isinstance(external_field_evidence, Mapping)
        else []
    )
    rows.append(_row(
        "diagnostic_external_outdoor_field_evidence",
        "외부 옥외 LH2 관측자료를 해시·사건시계·범위 정책과 함께 감사 장부에 기록해야 한다",
        "PASS" if external_field_ok else "BLOCKED_EVIDENCE",
        evidence_paths=(external_field_path,),
        observed={
            "status": external_status,
            "event_id": (
                external_field_evidence.get("event_id")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "dataset_id": (
                external_field_evidence.get("dataset_id")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "scope": (
                external_field_evidence.get("scope")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "source_row_count": source_summary.get("row_count") if isinstance(source_summary, Mapping) else None,
            "weather_row_count": weather_summary.get("row_count") if isinstance(weather_summary, Mapping) else None,
            "receptor_row_count": receptor_summary.get("row_count") if isinstance(receptor_summary, Mapping) else None,
            "hash_verification_enforced": (
                external_field_evidence.get("hash_verification_enforced")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "hash_drift_channels": list(hash_drift_channels) if isinstance(hash_drift_channels, list) else hash_drift_channels,
            "model_comparison_ready": (
                external_field_evidence.get("model_comparison_ready")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "physical_validation_claim": (
                external_field_evidence.get("physical_validation_claim")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "facility_qra_claim": (
                external_field_evidence.get("facility_qra_claim")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
            "frequency_inference_performed": (
                external_field_evidence.get("frequency_inference_performed")
                if isinstance(external_field_evidence, Mapping)
                else None
            ),
        },
        blocking_reason=None if external_field_ok else (
            "외부 관측자료의 schema·범위·해시 정책 또는 승격 금지 조건이 확인되지 않았다"
        ),
        interpretation=(
            "관측자료 입력 무결성과 제한 정책만 확인한다. 해시 drift는 진단에 표시하지만 "
            "물리검증·방출 packet·빈도·시설 QRA를 열지 않는다."
        ),
    ))

    comparison_status = (
        external_field_model_comparison.get("status")
        if isinstance(external_field_model_comparison, Mapping)
        else None
    )
    comparison_policy = (
        external_field_model_comparison.get("promotion_policy", {})
        if isinstance(external_field_model_comparison, Mapping)
        else {}
    )
    if not isinstance(comparison_policy, Mapping):
        comparison_policy = {}
    comparison_ok = (
        isinstance(external_field_model_comparison, Mapping)
        and external_field_model_comparison.get("schema_version")
        == "prism.external_field_model_comparison.v1"
        and comparison_status in {
            "RESTRICTED_FIELD_MODEL_COMPARISON",
            "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT",
        }
        and external_field_model_comparison.get("physical_validation_claim") is False
        and external_field_model_comparison.get("full_chain_validation_claim") is False
        and external_field_model_comparison.get("accident_release_validation_claim") is False
        and external_field_model_comparison.get("frequency_inference_performed") is False
        and external_field_model_comparison.get("facility_qra_claim") is False
        and comparison_policy.get("measured_source_replay_is_not_independent_validation") is True
        and comparison_policy.get("transport_delay_is_declared_not_fitted") is True
        and comparison_policy.get("no_extrapolation_outside_prediction_horizon") is True
        and comparison_policy.get("physical_validation_requires_external_review") is True
        and comparison_policy.get("component_comparison_does_not_validate_facility_qra") is True
    )
    if external_field_model_comparison is not None:
        comparison_matching = (
            external_field_model_comparison.get("matching", {})
            if isinstance(external_field_model_comparison, Mapping)
            else {}
        )
        comparison_metrics = (
            external_field_model_comparison.get("metrics", {})
            if isinstance(external_field_model_comparison, Mapping)
            else {}
        )
        rows.append(_row(
            "diagnostic_external_field_model_comparison",
            "외부 옥외 LH2 관측과 모델 농도를 동일 센서·공통시계·운반지연으로 비교하되 독립 물리검증으로 자동 승격하지 않아야 한다",
            "PASS" if comparison_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(external_field_comparison_path,),
            observed={
                "status": comparison_status,
                "event_id": (
                    external_field_model_comparison.get("event_id")
                    if isinstance(external_field_model_comparison, Mapping)
                    else None
                ),
                "matched_row_count": (
                    comparison_matching.get("matched_row_count")
                    if isinstance(comparison_matching, Mapping)
                    else None
                ),
                "matched_fraction": (
                    comparison_matching.get("matched_fraction")
                    if isinstance(comparison_matching, Mapping)
                    else None
                ),
                "rmse_vol_pct": (
                    comparison_metrics.get("rmse_vol_pct")
                    if isinstance(comparison_metrics, Mapping)
                    else None
                ),
                "source_boundary_mode": (
                    external_field_model_comparison.get("source_boundary_binding", {}).get("mode")
                    if isinstance(external_field_model_comparison, Mapping)
                    and isinstance(external_field_model_comparison.get("source_boundary_binding"), Mapping)
                    else None
                ),
                "independent_physical_validation_review_eligible": (
                    external_field_model_comparison.get("independent_physical_validation_review_eligible")
                    if isinstance(external_field_model_comparison, Mapping)
                    else None
                ),
            },
            blocking_reason=None if comparison_ok else (
                "외부 모델-관측 비교 장부의 schema·시간·기하·승격 금지 정책이 확인되지 않았다"
            ),
            interpretation=(
                "비교 오차와 시간·기하 결합만 기록한다. measured_source_replay 또는 hash drift는 "
                "독립 물리검증으로 승격하지 않으며, frequency·시설 QRA도 열지 않는다."
            ),
        ))

    validation_intake_ok = (
        isinstance(validation_intake_audit, Mapping)
        and validation_intake_audit.get("schema_version")
        == "prism.validation_intake_audit.v1"
        and validation_intake_audit.get("status") == "SCREENED_NO_PROMOTION"
        and validation_intake_audit.get("physical_validation_claim") is False
        and validation_intake_audit.get("accident_release_validation_claim") is False
        and validation_intake_audit.get("facility_qra_claim") is False
        and validation_intake_audit.get("frequency_inference_performed") is False
        and isinstance(validation_intake_audit.get("promotion_gates"), Mapping)
        and validation_intake_audit["promotion_gates"].get("promotion_allowed") is False
    )
    if validation_intake_audit is not None:
        intake_inputs = (
            validation_intake_audit.get("inputs", {})
            if isinstance(validation_intake_audit, Mapping)
            else {}
        )
        intake_inspection = (
            intake_inputs.get("inspection_timeseries", {})
            if isinstance(intake_inputs, Mapping)
            else {}
        )
        intake_aggregate = (
            intake_inspection.get("aggregate", {})
            if isinstance(intake_inspection, Mapping)
            else {}
        )
        rows.append(_row(
            "diagnostic_validation_intake_readiness",
            "검사센터 시계열과 외부 검증 장부를 입력 준비도만으로 기록하고 사고 방출·빈도·시설 QRA로 승격하지 않아야 한다",
            "PASS" if validation_intake_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(validation_intake_path,),
            observed={
                "intake_status": (
                    validation_intake_audit.get("status")
                    if isinstance(validation_intake_audit, Mapping)
                    else None
                ),
                "source_file_count": (
                    intake_inspection.get("source_file_count")
                    if isinstance(intake_inspection, Mapping)
                    else None
                ),
                "workbook_count": (
                    intake_aggregate.get("workbook_count")
                    if isinstance(intake_aggregate, Mapping)
                    else None
                ),
                "sheet_count": (
                    intake_aggregate.get("sheet_count")
                    if isinstance(intake_aggregate, Mapping)
                    else None
                ),
                "numeric_signal_unit_status_count": (
                    intake_aggregate.get("numeric_signal_unit_status_count")
                    if isinstance(intake_aggregate, Mapping)
                    else None
                ),
                "promotion_allowed": (
                    validation_intake_audit.get("promotion_gates", {}).get("promotion_allowed")
                    if isinstance(validation_intake_audit, Mapping)
                    and isinstance(validation_intake_audit.get("promotion_gates"), Mapping)
                    else None
                ),
                "frequency_inference_performed": (
                    validation_intake_audit.get("frequency_inference_performed")
                    if isinstance(validation_intake_audit, Mapping)
                    else None
                ),
            },
            blocking_reason=None if validation_intake_ok else (
                "검증 입력 장부의 schema·승격 차단 정책·정상 운전자료 경계가 확인되지 않았다"
            ),
            interpretation=(
                "검사센터 시계열은 공정 상태 후보 증거로만 보존한다. 단위·자산 crosswalk·"
                "provider 방출 packet·독립 holdout 근거가 없으면 물리검증, 빈도, 시설 QRA를 열지 않는다."
            ),
        ))

    equipment_model_gates = (
        external_equipment_model_audit.get("promotion_gates", {})
        if isinstance(external_equipment_model_audit, Mapping)
        else {}
    )
    if not isinstance(equipment_model_gates, Mapping):
        equipment_model_gates = {}
    external_equipment_model_ok = (
        isinstance(external_equipment_model_audit, Mapping)
        and external_equipment_model_audit.get("schema_version")
        == "prism.external_equipment_model_audit.v1"
        and external_equipment_model_audit.get("status")
        == "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED"
        and isinstance(external_equipment_model_audit.get("state_model_ready_asset_count"), int)
        and external_equipment_model_audit.get("state_model_ready_asset_count", 0) > 0
        and equipment_model_gates.get("state_model_input_allowed") is True
        and equipment_model_gates.get("accident_release_packet_allowed") is False
        and equipment_model_gates.get("provider_qualification_allowed") is False
        and equipment_model_gates.get("frequency_inference_allowed") is False
        and equipment_model_gates.get("facility_qra_allowed") is False
        and equipment_model_gates.get("promotion_allowed") is False
        and external_equipment_model_audit.get("physical_validation_claim") is False
        and external_equipment_model_audit.get("full_chain_validation_claim") is False
        and external_equipment_model_audit.get("accident_release_validation_claim") is False
        and external_equipment_model_audit.get("frequency_inference_performed") is False
        and external_equipment_model_audit.get("facility_qra_claim") is False
    )
    if external_equipment_model_audit is not None:
        equipment_event_register = (
            external_equipment_model_audit.get("event_register", {})
            if isinstance(external_equipment_model_audit, Mapping)
            else {}
        )
        equipment_observation = (
            external_equipment_model_audit.get("observation_provenance", {})
            if isinstance(external_equipment_model_audit, Mapping)
            else {}
        )
        equipment_pid_identity = (
            external_equipment_model_audit.get("pid_identity_evidence", {})
            if isinstance(external_equipment_model_audit, Mapping)
            else {}
        )
        if not isinstance(equipment_pid_identity, Mapping):
            equipment_pid_identity = {}
        equipment_pid_ports = (
            external_equipment_model_audit.get("pid_port_evidence", {})
            if isinstance(external_equipment_model_audit, Mapping)
            else {}
        )
        if not isinstance(equipment_pid_ports, Mapping):
            equipment_pid_ports = {}
        equipment_component_bindings = (
            external_equipment_model_audit.get("component_binding_evidence", {})
            if isinstance(external_equipment_model_audit, Mapping)
            else {}
        )
        if not isinstance(equipment_component_bindings, Mapping):
            equipment_component_bindings = {}
        equipment_flow_crosswalk = (
            external_equipment_model_audit.get("flow_crosswalk_evidence", {})
            if isinstance(external_equipment_model_audit, Mapping)
            else {}
        )
        if not isinstance(equipment_flow_crosswalk, Mapping):
            equipment_flow_crosswalk = {}
        rows.append(_row(
            "diagnostic_external_equipment_model_readiness",
            "외부 액화수소 설비 모델의 상태 입력 준비도와 사고 방출 경계를 분리하여 기록해야 한다",
            "PASS" if external_equipment_model_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(external_equipment_model_path,),
            observed={
                "status": (
                    external_equipment_model_audit.get("status")
                    if isinstance(external_equipment_model_audit, Mapping)
                    else None
                ),
                "asset_count": (
                    external_equipment_model_audit.get("asset_count")
                    if isinstance(external_equipment_model_audit, Mapping)
                    else None
                ),
                "state_model_ready_asset_count": (
                    external_equipment_model_audit.get("state_model_ready_asset_count")
                    if isinstance(external_equipment_model_audit, Mapping)
                    else None
                ),
                "physical_time_status": (
                    equipment_event_register.get("physical_time_status")
                    if isinstance(equipment_event_register, Mapping)
                    else None
                ),
                "valve_event_count": (
                    equipment_event_register.get("valve_event_count")
                    if isinstance(equipment_event_register, Mapping)
                    else None
                ),
                "physical_time_assigned_event_count": (
                    equipment_event_register.get("physical_time_assigned_event_count")
                    if isinstance(equipment_event_register, Mapping)
                    else None
                ),
                "verified_raw_historian_session_count": (
                    equipment_observation.get("verified_raw_historian_session_count")
                    if isinstance(equipment_observation, Mapping)
                    else None
                ),
                "pid_exact_asset_id_overlap_count": equipment_pid_identity.get(
                    "exact_asset_id_overlap_count"
                ),
                "pid_source_backed_overlap_count": equipment_pid_identity.get(
                    "source_backed_overlap_count"
                ),
                "pid_unmatched_external_asset_count": len(
                    equipment_pid_identity.get("unmatched_external_asset_ids", [])
                    if isinstance(
                        equipment_pid_identity.get("unmatched_external_asset_ids", []),
                        list,
                    )
                    else []
                ),
                "pid_confirmed_port_mapping_count": equipment_pid_ports.get(
                    "confirmed_port_mapping_count"
                ),
                "pid_candidate_port_mapping_count": equipment_pid_ports.get(
                    "candidate_port_mapping_count"
                ),
                "component_binding_enabled_edge_count": equipment_component_bindings.get(
                    "enabled_edge_count"
                ),
                "component_binding_unresolved_edge_count": equipment_component_bindings.get(
                    "unresolved_edge_count"
                ),
                "flow_candidate_pairing_count": equipment_flow_crosswalk.get(
                    "candidate_pairing_count"
                ),
                "flow_unresolved_tag_count": equipment_flow_crosswalk.get(
                    "unresolved_flow_tag_count"
                ),
                "general_facility_identity_resolved": equipment_pid_identity.get(
                    "identity_is_general_facility_resolved"
                ),
                "accident_release_packet_allowed": equipment_model_gates.get(
                    "accident_release_packet_allowed"
                ),
                "frequency_inference_allowed": equipment_model_gates.get(
                    "frequency_inference_allowed"
                ),
            },
            blocking_reason=None if external_equipment_model_ok else (
                "외부 설비 모델의 상태 입력 준비도 또는 사고 방출 승격 차단 정책이 확인되지 않았다"
            ),
            interpretation=(
                "TK-1101/TK-1102 같은 상태 모델 입력 준비 자산은 기록하되, 절차 의도·재구성 자료만으로 "
                "사고 방출 시각·차단·재고 소진·빈도·시설 QRA를 열지 않는다."
            ),
        ))

    scenario_coverage_gates = (
        equipment_scenario_coverage_audit.get("promotion_gates", {})
        if isinstance(equipment_scenario_coverage_audit, Mapping)
        else {}
    )
    if not isinstance(scenario_coverage_gates, Mapping):
        scenario_coverage_gates = {}
    scenario_coverage_policy = (
        equipment_scenario_coverage_audit.get("policy", {})
        if isinstance(equipment_scenario_coverage_audit, Mapping)
        else {}
    )
    if not isinstance(scenario_coverage_policy, Mapping):
        scenario_coverage_policy = {}
    scenario_coverage_ok = (
        isinstance(equipment_scenario_coverage_audit, Mapping)
        and equipment_scenario_coverage_audit.get("schema_version")
        == "prism.equipment_scenario_coverage_audit.v1"
        and equipment_scenario_coverage_audit.get("scenario_catalog_schema")
        == "prism.accident_scenario_catalog.v1"
        and equipment_scenario_coverage_audit.get("status") in {
            "CROSSWALK_REQUIRED",
            "PARTIAL_CROSSWALK_RELEASE_BOUNDARY_UNVERIFIED",
            "SCENARIO_CATALOG_BOUND_RELEASE_BOUNDARY_UNVERIFIED",
        }
        and scenario_coverage_gates.get("accident_release_packet_allowed") is False
        and scenario_coverage_gates.get("frequency_inference_allowed") is False
        and scenario_coverage_gates.get("facility_qra_allowed") is False
        and scenario_coverage_gates.get("promotion_allowed") is False
        and equipment_scenario_coverage_audit.get("physical_validation_claim") is False
        and equipment_scenario_coverage_audit.get("accident_release_validation_claim") is False
        and equipment_scenario_coverage_audit.get("frequency_inference_performed") is False
        and equipment_scenario_coverage_audit.get("facility_qra_claim") is False
        and scenario_coverage_policy.get("component_kind_is_never_inferred_from_tag") is True
        and scenario_coverage_policy.get("candidate_identity_is_not_resolved_identity") is True
        and scenario_coverage_policy.get("scenario_catalog_does_not_create_release") is True
        and scenario_coverage_policy.get("scenario_mapping_is_not_frequency") is True
        and scenario_coverage_policy.get("no_automatic_facility_qra_promotion") is True
    )
    if equipment_scenario_coverage_audit is not None:
        rows.append(_row(
            "diagnostic_equipment_scenario_coverage",
            "설비 ID·P&ID component kind·사고 family를 명시적으로 연결하되 시나리오 목록이 방출·빈도·시설 QRA를 만들지 않아야 한다",
            "PASS" if scenario_coverage_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(equipment_scenario_coverage_path,),
            observed={
                "status": (
                    equipment_scenario_coverage_audit.get("status")
                    if isinstance(equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "asset_count": (
                    equipment_scenario_coverage_audit.get("asset_count")
                    if isinstance(equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "mapped_asset_count": (
                    equipment_scenario_coverage_audit.get("mapped_asset_count")
                    if isinstance(equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "resolved_asset_count": (
                    equipment_scenario_coverage_audit.get("resolved_asset_count")
                    if isinstance(equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "scenario_family_count": (
                    equipment_scenario_coverage_audit.get("scenario_family_count")
                    if isinstance(equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "accident_release_packet_allowed": scenario_coverage_gates.get(
                    "accident_release_packet_allowed"
                ),
                "frequency_inference_allowed": scenario_coverage_gates.get(
                    "frequency_inference_allowed"
                ),
            },
            blocking_reason=None if scenario_coverage_ok else (
                "설비-사고 family 감사의 schema·crosswalk 정책 또는 승격 차단 조건이 확인되지 않았다"
            ),
            interpretation=(
                "일반 액화수소 시설에서 설비별 주요 사고 목록과 필요한 provider 연산자를 보여준다. "
                "P&ID crosswalk와 provider 방출 packet이 없으면 해당 family는 계산하지 않는다."
            ),
        ))

    frequency_binding_gates = (
        equipment_frequency_binding_audit.get("promotion_gates", {})
        if isinstance(equipment_frequency_binding_audit, Mapping)
        else {}
    )
    if not isinstance(frequency_binding_gates, Mapping):
        frequency_binding_gates = {}
    frequency_binding_policy = (
        equipment_frequency_binding_audit.get("policy", {})
        if isinstance(equipment_frequency_binding_audit, Mapping)
        else {}
    )
    if not isinstance(frequency_binding_policy, Mapping):
        frequency_binding_policy = {}
    frequency_binding_ok = (
        isinstance(equipment_frequency_binding_audit, Mapping)
        and equipment_frequency_binding_audit.get("schema_version")
        == "prism.equipment_frequency_binding_audit.v1"
        and equipment_frequency_binding_audit.get("status") in {
            "FREQUENCY_BINDING_WITHHELD",
            "PARTIAL_FREQUENCY_BINDING",
            "LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED",
        }
        and frequency_binding_gates.get("provider_release_required") is True
        and frequency_binding_gates.get("frequency_inference_allowed") is False
        and frequency_binding_gates.get("facility_qra_allowed") is False
        and frequency_binding_gates.get("promotion_allowed") is False
        and equipment_frequency_binding_audit.get("physical_validation_claim") is False
        and equipment_frequency_binding_audit.get("accident_release_validation_claim") is False
        and equipment_frequency_binding_audit.get("frequency_inference_performed") is False
        and equipment_frequency_binding_audit.get("facility_qra_claim") is False
        and equipment_frequency_binding_audit.get("provider_packet_promoted") is False
        and frequency_binding_policy.get("literature_frequency_is_not_field_validated") is True
        and frequency_binding_policy.get("sensor_frequency_learning_used") is False
        and frequency_binding_policy.get("normal_state_observations_do_not_create_frequency") is True
        and frequency_binding_policy.get("unresolved_assets_do_not_receive_zero_frequency") is True
        and frequency_binding_policy.get("unmapped_families_remain_uncomputed") is True
        and frequency_binding_policy.get("frequency_does_not_create_provider_release") is True
        and frequency_binding_policy.get("provider_release_required_before_consequence") is True
        and frequency_binding_policy.get("facility_qra_requires_complete_family_and_packet_coverage") is True
    )
    if equipment_frequency_binding_audit is not None:
        rows.append(_row(
            "diagnostic_equipment_frequency_binding",
            "문헌 빈도를 확정 설비·사고 family에만 연결하고 미계산 family와 provider 방출 요구를 보존해야 한다",
            "PASS" if frequency_binding_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(equipment_frequency_binding_path,),
            observed={
                "status": (
                    equipment_frequency_binding_audit.get("status")
                    if isinstance(equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "resolved_asset_count": (
                    equipment_frequency_binding_audit.get("resolved_asset_count")
                    if isinstance(equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "frequency_event_count": (
                    equipment_frequency_binding_audit.get("frequency_event_count")
                    if isinstance(equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "valid_frequency_event_count": (
                    equipment_frequency_binding_audit.get("valid_frequency_event_count")
                    if isinstance(equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "uncomputed_family_count": (
                    equipment_frequency_binding_audit.get("uncomputed_family_count")
                    if isinstance(equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "provider_release_required": frequency_binding_gates.get(
                    "provider_release_required"
                ),
                "facility_qra_allowed": frequency_binding_gates.get("facility_qra_allowed"),
            },
            blocking_reason=None if frequency_binding_ok else (
                "설비-빈도 연결의 문헌 provenance·미계산 family·방출 요구 정책이 확인되지 않았다"
            ),
            interpretation=(
                "문헌 빈도는 설비 사고 시작의 연간 빈도로만 사용한다. 실제 피해 계산은 provider가 "
                "지속시간·차단·재고·질량수지를 가진 방출 packet을 제출한 뒤에만 수행한다."
            ),
        ))

    generic_scenario_gates = (
        generic_equipment_scenario_coverage_audit.get("promotion_gates", {})
        if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
        else {}
    )
    if not isinstance(generic_scenario_gates, Mapping):
        generic_scenario_gates = {}
    generic_scenario_policy = (
        generic_equipment_scenario_coverage_audit.get("policy", {})
        if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
        else {}
    )
    if not isinstance(generic_scenario_policy, Mapping):
        generic_scenario_policy = {}
    generic_scenario_ok = (
        isinstance(generic_equipment_scenario_coverage_audit, Mapping)
        and generic_equipment_scenario_coverage_audit.get("schema_version")
        == "prism.equipment_scenario_coverage_audit.v1"
        and generic_equipment_scenario_coverage_audit.get("scenario_catalog_schema")
        == "prism.accident_scenario_catalog.v1"
        and generic_equipment_scenario_coverage_audit.get("status")
        in {
            "CROSSWALK_REQUIRED",
            "PARTIAL_CROSSWALK_RELEASE_BOUNDARY_UNVERIFIED",
            "SCENARIO_CATALOG_BOUND_RELEASE_BOUNDARY_UNVERIFIED",
        }
        and isinstance(generic_equipment_scenario_coverage_audit.get("asset_count"), int)
        and generic_equipment_scenario_coverage_audit.get("asset_count", 0) > 0
        and generic_equipment_scenario_coverage_audit.get("mapped_asset_count")
        == generic_equipment_scenario_coverage_audit.get("asset_count")
        and generic_equipment_scenario_coverage_audit.get("resolved_asset_count")
        == generic_equipment_scenario_coverage_audit.get("mapped_asset_count")
        and isinstance(
            generic_equipment_scenario_coverage_audit.get("scenario_family_count"), int
        )
        and generic_equipment_scenario_coverage_audit.get("scenario_family_count", 0) > 0
        and generic_scenario_gates.get("scenario_mapping_allowed") is True
        and generic_scenario_gates.get("accident_release_packet_allowed") is False
        and generic_scenario_gates.get("frequency_inference_allowed") is False
        and generic_scenario_gates.get("facility_qra_allowed") is False
        and generic_scenario_gates.get("promotion_allowed") is False
        and generic_equipment_scenario_coverage_audit.get("physical_validation_claim") is False
        and generic_equipment_scenario_coverage_audit.get("accident_release_validation_claim") is False
        and generic_equipment_scenario_coverage_audit.get("frequency_inference_performed") is False
        and generic_equipment_scenario_coverage_audit.get("facility_qra_claim") is False
        and generic_scenario_policy.get("component_kind_is_never_inferred_from_tag") is True
        and generic_scenario_policy.get("candidate_identity_is_not_resolved_identity") is True
        and generic_scenario_policy.get("scenario_catalog_does_not_create_release") is True
        and generic_scenario_policy.get("scenario_mapping_is_not_frequency") is True
        and generic_scenario_policy.get("no_automatic_facility_qra_promotion") is True
    )
    if generic_equipment_scenario_coverage_audit is not None:
        rows.append(_row(
            "diagnostic_generic_equipment_scenario_coverage",
            "일반 옥외 액화수소시설의 설비·사고군 crosswalk를 objective 원장에 연결하되 방출·빈도·QRA 승격은 차단해야 한다",
            "PASS" if generic_scenario_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(generic_equipment_scenario_coverage_path,),
            observed={
                "status": (
                    generic_equipment_scenario_coverage_audit.get("status")
                    if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "asset_count": (
                    generic_equipment_scenario_coverage_audit.get("asset_count")
                    if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "mapped_asset_count": (
                    generic_equipment_scenario_coverage_audit.get("mapped_asset_count")
                    if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "resolved_asset_count": (
                    generic_equipment_scenario_coverage_audit.get("resolved_asset_count")
                    if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "state_model_ready_mapped_asset_count": (
                    generic_equipment_scenario_coverage_audit.get(
                        "state_model_ready_mapped_asset_count"
                    )
                    if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "scenario_family_count": (
                    generic_equipment_scenario_coverage_audit.get("scenario_family_count")
                    if isinstance(generic_equipment_scenario_coverage_audit, Mapping)
                    else None
                ),
                "accident_release_packet_allowed": generic_scenario_gates.get(
                    "accident_release_packet_allowed"
                ),
                "facility_qra_allowed": generic_scenario_gates.get("facility_qra_allowed"),
            },
            blocking_reason=None if generic_scenario_ok else (
                "일반 시설 설비-사고군 감사의 schema·crosswalk·승격 차단 정책이 확인되지 않았다"
            ),
            interpretation=(
                "일반 시설 manifest는 7개 설비와 12개 사고군의 적용 후보를 명시한다. "
                "이 목록은 provider의 방출 지속시간·차단·재고·질량수지를 대신하지 않는다."
            ),
        ))

    generic_frequency_gates = (
        generic_equipment_frequency_binding_audit.get("promotion_gates", {})
        if isinstance(generic_equipment_frequency_binding_audit, Mapping)
        else {}
    )
    if not isinstance(generic_frequency_gates, Mapping):
        generic_frequency_gates = {}
    generic_frequency_policy = (
        generic_equipment_frequency_binding_audit.get("policy", {})
        if isinstance(generic_equipment_frequency_binding_audit, Mapping)
        else {}
    )
    if not isinstance(generic_frequency_policy, Mapping):
        generic_frequency_policy = {}
    generic_frequency_ok = (
        isinstance(generic_equipment_frequency_binding_audit, Mapping)
        and generic_equipment_frequency_binding_audit.get("schema_version")
        == "prism.equipment_frequency_binding_audit.v1"
        and generic_equipment_frequency_binding_audit.get("status")
        in {
            "FREQUENCY_BINDING_WITHHELD",
            "PARTIAL_FREQUENCY_BINDING",
            "LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED",
        }
        and isinstance(generic_equipment_frequency_binding_audit.get("resolved_asset_count"), int)
        and generic_equipment_frequency_binding_audit.get("resolved_asset_count", 0) > 0
        and isinstance(generic_equipment_frequency_binding_audit.get("frequency_event_count"), int)
        and generic_equipment_frequency_binding_audit.get("frequency_event_count", 0) > 0
        and generic_equipment_frequency_binding_audit.get("valid_frequency_event_count")
        == generic_equipment_frequency_binding_audit.get("frequency_event_count")
        and isinstance(generic_equipment_frequency_binding_audit.get("uncomputed_family_count"), int)
        and generic_equipment_frequency_binding_audit.get("uncomputed_family_count", 0) >= 0
        and generic_frequency_gates.get("literature_frequency_binding_allowed") is True
        and generic_frequency_gates.get("provider_release_required") is True
        and generic_frequency_gates.get("consequence_binding_allowed") is False
        and generic_frequency_gates.get("frequency_inference_allowed") is False
        and generic_frequency_gates.get("facility_qra_allowed") is False
        and generic_frequency_gates.get("promotion_allowed") is False
        and generic_equipment_frequency_binding_audit.get("physical_validation_claim") is False
        and generic_equipment_frequency_binding_audit.get("accident_release_validation_claim") is False
        and generic_equipment_frequency_binding_audit.get("frequency_inference_performed") is False
        and generic_equipment_frequency_binding_audit.get("facility_qra_claim") is False
        and generic_equipment_frequency_binding_audit.get("provider_packet_promoted") is False
        and generic_frequency_policy.get("literature_frequency_is_not_field_validated") is True
        and generic_frequency_policy.get("sensor_frequency_learning_used") is False
        and generic_frequency_policy.get("normal_state_observations_do_not_create_frequency") is True
        and generic_frequency_policy.get("unresolved_assets_do_not_receive_zero_frequency") is True
        and generic_frequency_policy.get("unmapped_families_remain_uncomputed") is True
        and generic_frequency_policy.get("frequency_does_not_create_provider_release") is True
        and generic_frequency_policy.get("provider_release_required_before_consequence") is True
        and generic_frequency_policy.get("facility_qra_requires_complete_family_and_packet_coverage") is True
    )
    if generic_equipment_frequency_binding_audit is not None:
        rows.append(_row(
            "diagnostic_generic_equipment_frequency_binding",
            "일반 시설 설비 사고군에 문헌 빈도를 연결하되 현장 학습·provider 방출·피해 결합과 미계산 사고를 보존해야 한다",
            "PASS" if generic_frequency_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(generic_equipment_frequency_binding_path,),
            observed={
                "status": (
                    generic_equipment_frequency_binding_audit.get("status")
                    if isinstance(generic_equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "asset_count": (
                    generic_equipment_frequency_binding_audit.get("asset_count")
                    if isinstance(generic_equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "resolved_asset_count": (
                    generic_equipment_frequency_binding_audit.get("resolved_asset_count")
                    if isinstance(generic_equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "frequency_event_count": (
                    generic_equipment_frequency_binding_audit.get("frequency_event_count")
                    if isinstance(generic_equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "valid_frequency_event_count": (
                    generic_equipment_frequency_binding_audit.get("valid_frequency_event_count")
                    if isinstance(generic_equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "uncomputed_family_count": (
                    generic_equipment_frequency_binding_audit.get("uncomputed_family_count")
                    if isinstance(generic_equipment_frequency_binding_audit, Mapping)
                    else None
                ),
                "provider_release_required": generic_frequency_gates.get(
                    "provider_release_required"
                ),
                "consequence_binding_allowed": generic_frequency_gates.get(
                    "consequence_binding_allowed"
                ),
                "facility_qra_allowed": generic_frequency_gates.get("facility_qra_allowed"),
            },
            blocking_reason=None if generic_frequency_ok else (
                "일반 시설 문헌빈도 연결의 provenance·미계산 사고·provider 요구 정책이 확인되지 않았다"
            ),
            interpretation=(
                "문헌 빈도는 일반 시설의 사고 시작 빈도 후보로만 연결한다. "
                "센서 정상상태에서 빈도를 학습하지 않으며, provider 방출 packet 없이는 피해와 IR/F-N을 계산하지 않는다."
            ),
        ))

    # Release closure is a prerequisite for a qualified provider packet, but
    # the worklist itself is an intake/collection ledger.  Keep it outside
    # the core and strict slices above so an open worklist cannot be mistaken
    # for a new numerical failure or silently change the established blocker
    # taxonomy.  A closed worklist still does not promote provider evidence,
    # frequency, physical validation, or facility QRA.
    closure_summary = (
        release_closure_worklist.get("summary", {})
        if isinstance(release_closure_worklist, Mapping)
        else {}
    )
    if not isinstance(closure_summary, Mapping):
        closure_summary = {}
    closure_gaps = closure_summary.get("closure_gap_counts", {})
    if not isinstance(closure_gaps, Mapping):
        closure_gaps = {}
    closure_promotions = (
        release_closure_worklist.get("promotion_gates", {})
        if isinstance(release_closure_worklist, Mapping)
        else {}
    )
    if not isinstance(closure_promotions, Mapping):
        closure_promotions = {}
    closure_case_count = (
        _int(release_closure_worklist.get("case_count"))
        if isinstance(release_closure_worklist, Mapping)
        else None
    )
    closure_open_case_count = (
        _int(release_closure_worklist.get("open_case_count"))
        if isinstance(release_closure_worklist, Mapping)
        else None
    )
    closure_input_ok = (
        isinstance(release_closure_worklist, Mapping)
        and release_closure_worklist.get("schema_version")
        == "prism.release_closure_worklist.v1"
        and release_closure_worklist.get("status") in {
            "OPEN_RELEASE_CLOSURE_WORKLIST",
            "CLOSED_DIAGNOSTIC_BOUNDARY_WORKLIST",
        }
        and closure_case_count is not None
        and closure_case_count >= 0
        and closure_open_case_count is not None
        and 0 <= closure_open_case_count <= closure_case_count
        and isinstance(closure_summary.get("closure_status_counts"), Mapping)
        and closure_promotions.get("release_boundary_promotion_allowed") is False
        and closure_promotions.get("frequency_inference_allowed") is False
        and closure_promotions.get("facility_qra_allowed") is False
        and closure_promotions.get("physical_validation_claim") is False
        and closure_promotions.get("diagnostic_only") is True
    )
    closure_closed = (
        closure_input_ok
        and closure_open_case_count == 0
        and release_closure_worklist.get("status")
        == "CLOSED_DIAGNOSTIC_BOUNDARY_WORKLIST"
    )
    if release_closure_worklist is not None:
        rows.append(_row(
            "diagnostic_release_closure_worklist",
            "방출 종료·격리·재고 소진·질량잔차의 provider closure를 사건별로 추적하고 미해결 항목을 표시해야 한다",
            "PASS" if closure_closed else "BLOCKED_EVIDENCE",
            evidence_paths=(release_closure_worklist_path,),
            observed={
                "schema_version": (
                    release_closure_worklist.get("schema_version")
                    if isinstance(release_closure_worklist, Mapping)
                    else None
                ),
                "worklist_status": (
                    release_closure_worklist.get("status")
                    if isinstance(release_closure_worklist, Mapping)
                    else None
                ),
                "case_count": closure_case_count,
                "open_case_count": closure_open_case_count,
                "closure_input_valid": closure_input_ok,
                "closure_closed": closure_closed,
                "closure_gap_counts": dict(closure_gaps),
                "mass_closure_open_case_count": closure_summary.get(
                    "mass_closure_open_case_count"
                ),
                "isolation_open_case_count": closure_summary.get(
                    "isolation_open_case_count"
                ),
                "termination_open_case_count": closure_summary.get(
                    "termination_open_case_count"
                ),
                "inventory_closure_open_case_count": closure_summary.get(
                    "inventory_closure_open_case_count"
                ),
                "provider_packet_required_case_count": closure_summary.get(
                    "provider_packet_required_case_count"
                ),
                "promotion_gates": dict(closure_promotions),
            },
            blocking_reason=(
                None
                if closure_closed
                else (
                    "release closure worklist 입력이 없거나 종료·격리·재고 closure가 "
                    f"아직 열려 있다(open_case_count={closure_open_case_count})"
                )
            ),
            interpretation=(
                "이 행은 provider 자료 수집과 종료 경계 확인을 위한 진단 원장이다. "
                "worklist가 닫혀도 qualified provider evidence·독립 물리검증·시설 QRA를 "
                "자동으로 열지 않는다."
            ),
        ))

    # Keep the one-request-per-provider-packet catalog visible in the IJHE
    # ledger. It is an intake check only: it never promotes a packet,
    # assigns frequency, or opens facility QRA.
    provider_catalog = generic_provider_evidence_requests
    provider_catalog_packet_count = (
        _int(provider_catalog.get("packet_count"))
        if isinstance(provider_catalog, Mapping)
        else None
    )
    provider_catalog_request_count = (
        _int(provider_catalog.get("request_count"))
        if isinstance(provider_catalog, Mapping)
        else None
    )
    provider_catalog_closure_open_count = (
        _int(provider_catalog.get("closure_open_request_count"))
        if isinstance(provider_catalog, Mapping)
        else None
    )
    provider_catalog_qualification_open_count = (
        _int(provider_catalog.get("qualification_open_request_count"))
        if isinstance(provider_catalog, Mapping)
        else None
    )
    provider_catalog_input_ok = (
        isinstance(provider_catalog, Mapping)
        and provider_catalog.get("schema_version")
        == "prism.generic_provider_evidence_requests.v1"
        and provider_catalog.get("diagnostic_only") is True
        and provider_catalog.get("frequency_inference_allowed") is False
        and provider_catalog.get("facility_qra_allowed") is False
        and provider_catalog.get("qualified_provider_packet_count") == 0
        and provider_catalog_packet_count is not None
        and provider_catalog_request_count == provider_catalog_packet_count
        and provider_catalog_closure_open_count is not None
        and provider_catalog_qualification_open_count is not None
        and provider_catalog_closure_open_count
        + provider_catalog_qualification_open_count
        == provider_catalog_request_count
    )
    provider_catalog_matches_closure = (
        provider_catalog_input_ok
        and (
            not isinstance(generic_provider_closure_audit, Mapping)
            or _int(generic_provider_closure_audit.get("provider_packet_count"))
            == provider_catalog_packet_count
        )
    )
    if generic_provider_evidence_requests is not None:
        rows.append(_row(
            "diagnostic_generic_provider_evidence_requests",
            "모든 generic LH2 provider packet에 종료근거 또는 qualification 증거 요청이 정확히 하나씩 있어야 한다",
            "PASS" if provider_catalog_matches_closure else "BLOCKED_EVIDENCE",
            evidence_paths=(generic_provider_evidence_requests_path,),
            observed={
                "schema_version": (
                    provider_catalog.get("schema_version")
                    if isinstance(provider_catalog, Mapping)
                    else None
                ),
                "event_count": (
                    provider_catalog.get("event_count")
                    if isinstance(provider_catalog, Mapping)
                    else None
                ),
                "packet_path_count": (
                    provider_catalog.get("packet_path_count")
                    if isinstance(provider_catalog, Mapping)
                    else None
                ),
                "packet_count": provider_catalog_packet_count,
                "request_count": provider_catalog_request_count,
                "closure_open_request_count": provider_catalog_closure_open_count,
                "qualification_open_request_count": provider_catalog_qualification_open_count,
                "qualified_provider_packet_count": (
                    provider_catalog.get("qualified_provider_packet_count")
                    if isinstance(provider_catalog, Mapping)
                    else None
                ),
                "catalog_input_valid": provider_catalog_input_ok,
                "catalog_matches_closure": provider_catalog_matches_closure,
                "frequency_inference_allowed": (
                    provider_catalog.get("frequency_inference_allowed")
                    if isinstance(provider_catalog, Mapping)
                    else None
                ),
                "facility_qra_allowed": (
                    provider_catalog.get("facility_qra_allowed")
                    if isinstance(provider_catalog, Mapping)
                    else None
                ),
            },
            blocking_reason=(
                None
                if provider_catalog_matches_closure
                else "provider 증거 요청 catalog가 malformed이거나 closure audit의 packet 수와 일치하지 않는다"
            ),
            interpretation=(
                "catalog는 자료 수집의 누락을 방지하는 진단 장부다. 종료시간, 재고, 빈도, "
                "물리검증 또는 시설 QRA를 추정하거나 자동 승격하지 않는다."
            ),
        ))

    # The packet-count comparison above does not prove that every event has a
    # closure decision. Keep the provider-owned release-closure audit as a
    # separate diagnostic row so an open event, malformed status count, or an
    # accidental promotion flag is visible in the IJHE evidence ledger.
    provider_closure = generic_provider_closure_audit
    closure_status_counts = (
        provider_closure.get("event_closure_status_counts", {})
        if isinstance(provider_closure, Mapping)
        else {}
    )
    if not isinstance(closure_status_counts, Mapping):
        closure_status_counts = {}
    closure_event_count = (
        _int(provider_closure.get("event_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_ready_event_count = (
        _int(provider_closure.get("closure_ready_event_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_open_event_count = (
        _int(provider_closure.get("closure_open_event_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_packet_path_count = (
        _int(provider_closure.get("packet_path_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_provider_packet_count = (
        _int(provider_closure.get("provider_packet_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_ready_packet_path_count = (
        _int(provider_closure.get("closure_ready_packet_path_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_ready_provider_packet_count = (
        _int(provider_closure.get("closure_ready_provider_packet_count"))
        if isinstance(provider_closure, Mapping)
        else None
    )
    closure_promotion_gates = (
        provider_closure.get("promotion_gates", {})
        if isinstance(provider_closure, Mapping)
        else {}
    )
    if not isinstance(closure_promotion_gates, Mapping):
        closure_promotion_gates = {}
    closure_counts_match = (
        closure_event_count is not None
        and closure_ready_event_count is not None
        and closure_open_event_count is not None
        and closure_ready_event_count + closure_open_event_count == closure_event_count
        and closure_status_counts.get("CLOSURE_READY_FOR_QUALIFICATION", 0)
        == closure_ready_event_count
        and closure_status_counts.get("CLOSURE_EVIDENCE_OPEN", 0)
        == closure_open_event_count
        and closure_packet_path_count is not None
        and closure_provider_packet_count is not None
        and closure_ready_packet_path_count is not None
        and closure_ready_provider_packet_count is not None
        and 0 <= closure_ready_packet_path_count <= closure_packet_path_count
        and 0 <= closure_ready_provider_packet_count <= closure_provider_packet_count
    )
    provider_closure_input_ok = (
        isinstance(provider_closure, Mapping)
        and provider_closure.get("schema_version")
        == "prism.generic_provider_release_closure_audit.v1"
        and provider_closure.get("status")
        in {"CLOSURE_EVIDENCE_OPEN", "CLOSURE_READY_FOR_QUALIFICATION"}
        and closure_counts_match
        and provider_closure.get("qualified_provider_packet_count") == 0
        and provider_closure.get("frequency_from_provider_packet") is False
        and provider_closure.get("physical_validation_claim") is False
        and provider_closure.get("facility_qra_claim") is False
        and closure_promotion_gates.get("closure_ready") is False
        and closure_promotion_gates.get("qualified_provider_packet_allowed") is False
        and closure_promotion_gates.get("frequency_inference_allowed") is False
        and closure_promotion_gates.get("facility_qra_allowed") is False
        and closure_promotion_gates.get("diagnostic_only") is True
        and (
            not isinstance(provider_catalog, Mapping)
            or closure_provider_packet_count == provider_catalog_packet_count
        )
    )
    if generic_provider_closure_audit is not None:
        rows.append(_row(
            "diagnostic_generic_provider_release_closure",
            "generic LH2 provider의 사건별 방출 종료·차단·재고 closure 상태와 승격 차단을 직접 검증해야 한다",
            "PASS" if provider_closure_input_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(generic_provider_closure_path,),
            observed={
                "schema_version": (
                    provider_closure.get("schema_version")
                    if isinstance(provider_closure, Mapping)
                    else None
                ),
                "status": (
                    provider_closure.get("status")
                    if isinstance(provider_closure, Mapping)
                    else None
                ),
                "event_count": closure_event_count,
                "closure_ready_event_count": closure_ready_event_count,
                "closure_open_event_count": closure_open_event_count,
                "packet_path_count": closure_packet_path_count,
                "provider_packet_count": closure_provider_packet_count,
                "closure_ready_packet_path_count": closure_ready_packet_path_count,
                "closure_ready_provider_packet_count": closure_ready_provider_packet_count,
                "closure_counts_match": closure_counts_match,
                "catalog_packet_count": provider_catalog_packet_count,
                "catalog_packet_count_match": (
                    not isinstance(provider_catalog, Mapping)
                    or closure_provider_packet_count == provider_catalog_packet_count
                ),
                "qualified_provider_packet_count": (
                    provider_closure.get("qualified_provider_packet_count")
                    if isinstance(provider_closure, Mapping)
                    else None
                ),
                "promotion_gates": dict(closure_promotion_gates),
                "input_valid": provider_closure_input_ok,
            },
            blocking_reason=None if provider_closure_input_ok else (
                "generic provider release-closure audit가 malformed이거나 사건·packet 수와 승격 차단 정책이 일치하지 않는다"
            ),
            interpretation=(
                "열린 closure 사건은 provider 자료 수집 대기 상태로 남긴다. 이 행이 PASS여도 "
                "종료근거가 모든 사건에서 확보됐다는 뜻이 아니며, qualified provider·빈도 추론·시설 QRA를 열지 않는다."
            ),
        ))

    # Verify that the catalog was checked against adjacent qualification
    # sidecars.  This is an intake diagnostic only and cannot open frequency
    # or facility-QRA gates.
    provider_audit = generic_provider_evidence_audit
    provider_audit_input_ok = (
        isinstance(provider_audit, Mapping)
        and provider_audit.get("schema_version") == "prism.generic_provider_evidence_audit.v1"
        and provider_audit.get("diagnostic_only") is True
        and provider_audit.get("frequency_inference_allowed") is False
        and provider_audit.get("facility_qra_allowed") is False
        and _int(provider_audit.get("request_count")) is not None
        and _int(provider_audit.get("packet_count")) is not None
        and _int(provider_audit.get("exact_match_count")) is not None
        and _int(provider_audit.get("qualified_provider_packet_count")) is not None
        and _int(provider_audit.get("qualified_provider_packet_count"))
        <= _int(provider_audit.get("exact_match_count"))
        and _int(provider_audit.get("qualified_provider_packet_count"))
        <= _int(provider_audit.get("request_count"))
    )
    provider_audit_matches_catalog = (
        provider_audit_input_ok
        and (
            not isinstance(provider_catalog, Mapping)
            or _int(provider_audit.get("request_count"))
            == _int(provider_catalog.get("request_count"))
        )
        and (
            not isinstance(provider_catalog, Mapping)
            or _int(provider_audit.get("packet_count"))
            == _int(provider_catalog.get("packet_count"))
        )
    )
    if generic_provider_evidence_audit is not None:
        rows.append(_row(
            "diagnostic_generic_provider_evidence_audit",
            "provider evidence catalog의 각 packet에 qualification sidecar exact-match 감사가 실행되어야 한다",
            "PASS" if provider_audit_matches_catalog else "BLOCKED_EVIDENCE",
            evidence_paths=(generic_provider_evidence_audit_path,),
            observed={
                "schema_version": provider_audit.get("schema_version")
                if isinstance(provider_audit, Mapping) else None,
                "request_count": provider_audit.get("request_count")
                if isinstance(provider_audit, Mapping) else None,
                "packet_count": provider_audit.get("packet_count")
                if isinstance(provider_audit, Mapping) else None,
                "qualification_sidecar_present_count": provider_audit.get(
                    "qualification_sidecar_present_count"
                ) if isinstance(provider_audit, Mapping) else None,
                "exact_match_count": provider_audit.get("exact_match_count")
                if isinstance(provider_audit, Mapping) else None,
                "qualified_provider_packet_count": provider_audit.get(
                    "qualified_provider_packet_count"
                ) if isinstance(provider_audit, Mapping) else None,
                "audit_input_valid": provider_audit_input_ok,
                "audit_matches_catalog": provider_audit_matches_catalog,
            },
            blocking_reason=(
                None
                if provider_audit_matches_catalog
                else "qualification sidecar audit가 malformed이거나 evidence catalog의 request/packet 수와 일치하지 않는다"
            ),
            interpretation=(
                "sidecar exact-match 감사는 자료가 실제 packet에 귀속되는지 확인하는 진단 단계다. "
                "독립 물리검증, 빈도 결합 또는 시설 QRA 승격을 수행하지 않는다."
            ),
        ))

    # External release files are useful for discovery, but they must remain an
    # inventory-only diagnostic until the exact provider qualification sidecar
    # and release-boundary closure are supplied.  Keep this row outside the
    # established core/strict slices above so an expanded search cannot change
    # the qualification status by itself.
    external_intake = external_release_artifact_intake
    external_intake_policy = (
        external_intake.get("promotion_policy", {})
        if isinstance(external_intake, Mapping)
        else {}
    )
    if not isinstance(external_intake_policy, Mapping):
        external_intake_policy = {}
    external_intake_status = (
        external_intake.get("status")
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_rows = (
        _int(external_intake.get("release_row_count"))
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_files = (
        _int(external_intake.get("artifact_file_count"))
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_sidecars = (
        _int(external_intake.get("qualified_sidecar_row_count"))
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_closure_ready = (
        _int(external_intake.get("closure_ready_row_count"))
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_actual = (
        _int(external_intake.get("actual_origin_row_count"))
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_synthetic = (
        _int(external_intake.get("synthetic_or_model_prediction_row_count"))
        if isinstance(external_intake, Mapping)
        else None
    )
    external_intake_errors = (
        external_intake.get("errors", [])
        if isinstance(external_intake, Mapping)
        else []
    )
    if not isinstance(external_intake_errors, list):
        external_intake_errors = []
    external_intake_counts_ok = (
        external_intake_rows is not None
        and external_intake_rows >= 0
        and external_intake_files is not None
        and external_intake_files >= 0
        and external_intake_sidecars is not None
        and 0 <= external_intake_sidecars <= external_intake_rows
        and external_intake_closure_ready is not None
        and 0 <= external_intake_closure_ready <= external_intake_rows
        and external_intake_actual is not None
        and 0 <= external_intake_actual <= external_intake_rows
        and external_intake_synthetic is not None
        and 0 <= external_intake_synthetic <= external_intake_rows
        and len(external_intake_errors)
        == (external_intake.get("error_count") if isinstance(external_intake, Mapping) else None)
    )
    external_intake_ok = (
        isinstance(external_intake, Mapping)
        and external_intake.get("schema_version")
        == "prism.external_release_artifact_intake.v1"
        and external_intake_status == "EXTERNAL_RELEASE_ARTIFACTS_REQUIRE_QUALIFICATION"
        and external_intake.get("diagnostic_only") is True
        and external_intake_counts_ok
        and external_intake_policy.get("frequency_assigned") is False
        and external_intake_policy.get("provider_release_packet_promoted") is False
        and external_intake_policy.get("physical_validation_promoted") is False
        and external_intake_policy.get("facility_qra_promoted") is False
        and external_intake_policy.get("qualification_requires_exact_digest_bound_sidecar") is True
        and external_intake_policy.get("provider_ports_never_substituted_for_frequency_ports") is True
    )
    if external_release_artifact_intake is not None:
        rows.append(_row(
            "diagnostic_external_release_artifact_intake",
            "외부 LH2 방출 파일을 전체 검색하되 정확한 qualification sidecar와 종료근거가 없으면 진단 inventory로만 유지해야 한다",
            "PASS" if external_intake_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(external_release_artifact_intake_path,),
            observed={
                "schema_version": (
                    external_intake.get("schema_version")
                    if isinstance(external_intake, Mapping)
                    else None
                ),
                "status": external_intake_status,
                "artifact_file_count": external_intake_files,
                "qualification_file_count": (
                    external_intake.get("qualification_file_count")
                    if isinstance(external_intake, Mapping)
                    else None
                ),
                "release_row_count": external_intake_rows,
                "qualified_sidecar_row_count": external_intake_sidecars,
                "closure_ready_row_count": external_intake_closure_ready,
                "actual_origin_row_count": external_intake_actual,
                "synthetic_or_model_prediction_row_count": external_intake_synthetic,
                "closure_status_counts": (
                    dict(external_intake.get("closure_status_counts", {}))
                    if isinstance(external_intake, Mapping)
                    and isinstance(external_intake.get("closure_status_counts"), Mapping)
                    else external_intake.get("closure_status_counts")
                    if isinstance(external_intake, Mapping)
                    else None
                ),
                "error_count": (
                    external_intake.get("error_count")
                    if isinstance(external_intake, Mapping)
                    else None
                ),
                "counts_valid": external_intake_counts_ok,
                "promotion_policy": dict(external_intake_policy),
            },
            blocking_reason=None if external_intake_ok else (
                "외부 방출 inventory의 schema·집계·정확한 qualification 요구·승격 차단 정책이 확인되지 않았다"
            ),
            interpretation=(
                "검색된 파일은 설비·사고 후보를 찾는 보조 장부다. synthetic/model-prediction 자료와 "
                "sidecar 없는 방출은 실제 사고 근거·빈도·물리검증·시설 QRA로 승격하지 않는다."
            ),
        ))

    # When the current full completion audit is supplied, reconcile its
    # facility-wide case ledger with this objective ledger.  Older callers
    # provide only ``status`` and remain valid; the alignment row is added only
    # when the richer 44-check audit is present.
    completion_checks = completion_audit.get("checks", [])
    if isinstance(completion_checks, list) and completion_checks:
        completion_by_name = {
            row.get("name"): row
            for row in completion_checks
            if isinstance(row, Mapping) and isinstance(row.get("name"), str)
        }
        required_diagnostic_statuses = {
            "diagnostic_worklist_packet_coverage_evidence": {"PASS"},
            "diagnostic_release_trace_coverage": {"PASS"},
            "diagnostic_numerical_scope_coverage": {"PASS"},
            "diagnostic_facility_frequency_port_binding": {
                "PASS_DIAGNOSTIC_ONLY",
                "PASS_DIAGNOSTIC_ONLY_WITHHELD",
                "PASS",
            },
            "diagnostic_external_release_artifact_intake": {
                "PASS_DIAGNOSTIC_ONLY",
                "PASS",
            },
            "diagnostic_facility_evidence_request_coverage": {"PASS"},
        }
        diagnostic_status_observed = {
            name: completion_by_name.get(name, {}).get("status")
            for name in required_diagnostic_statuses
        }
        diagnostic_alignment_ok = (
            completion_audit.get("schema_version")
            == "prism.ijhe_completion_audit.v1"
            and completion_audit.get("status") == "INCOMPLETE_EVIDENCE"
            and len(completion_checks) >= 44
            and all(
                diagnostic_status_observed[name] in allowed
                for name, allowed in required_diagnostic_statuses.items()
            )
            and len(completion_audit.get("blocking_reasons", [])) == 5
            and completion_audit.get("physical_validation_claim") is False
            and completion_audit.get("complete_facility_qra_claim") is False
        )
        rows.append(_row(
            "diagnostic_full_completion_audit_alignment",
            "최신 시설 전체 완료감사의 case·구조적 작업목록·진단 검사·차단 이유를 IJHE 목표 원장과 일치시켜야 한다",
            "PASS" if diagnostic_alignment_ok else "BLOCKED_EVIDENCE",
            evidence_paths=(completion_path,),
            observed={
                "schema_version": completion_audit.get("schema_version"),
                "status": completion_audit.get("status"),
                "check_count": len(completion_checks),
                "required_diagnostic_statuses": diagnostic_status_observed,
                "blocking_reason_count": len(completion_audit.get("blocking_reasons", [])),
                "physical_validation_claim": completion_audit.get("physical_validation_claim"),
                "complete_facility_qra_claim": completion_audit.get("complete_facility_qra_claim"),
                "alignment_valid": diagnostic_alignment_ok,
            },
            blocking_reason=None if diagnostic_alignment_ok else (
                "최신 44개 case 완료감사의 schema·진단 검사·차단 이유 또는 승격 차단 플래그가 목표 원장과 일치하지 않는다"
            ),
            interpretation=(
                "이 행은 최신 전체 감사가 구조적 연결을 확인했는지 검증한다. "
                "PASS는 시설 QRA 완료를 뜻하지 않으며, 실제 provider·물리검증·범위 gate는 별도로 열린다."
            ),
        ))

    core_rows = rows[:8]
    # The first 15 rows are the established core/strict gates.  The external
    # observation row above is diagnostic-only and must not change either
    # blocker list or the overall qualification status.
    strict_rows = rows[8:15]
    core_blocked = [row["id"] for row in core_rows if row["status"] == "BLOCKED_EVIDENCE"]
    strict_blocked = [row["id"] for row in strict_rows if row["status"] == "BLOCKED_EVIDENCE"]
    if not core_blocked and strict_blocked:
        status = "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"
    elif not core_blocked and not strict_blocked:
        status = "IJHE_OBJECTIVE_COMPLETE"
    else:
        status = "OBJECTIVE_CHAIN_INCOMPLETE"

    row_by_id = {row["id"]: row for row in rows}
    completion_criteria = []
    for criterion_id, check_id, gate_ids in (
        ("A_equipment_state_and_release", "equipment_state_to_native_release", ("qualified_provider_evidence",)),
        ("B_release_to_final_damage", "release_to_final_damage", ("qualified_provider_evidence", "strict_facility_qra")),
        ("C_facility_ir_fn_and_scope", "generic_lh2_scope", ("strict_facility_scope", "strict_facility_qra")),
        ("D_literature_frequency_uncertainty", "literature_frequency_uncertainty", ("qualified_provider_evidence",)),
        ("E_validation_and_processing_time", "realtime_processing", ("independent_physical_validation",)),
    ):
        check = row_by_id[check_id]
        open_gate_ids = [gate_id for gate_id in gate_ids if gate_id in strict_blocked]
        completion_criteria.append({
            "id": criterion_id,
            "status": (
                "CONDITIONAL_PASS"
                if check["status"] in {"PASS", "CONDITIONALLY_COMPLETE"}
                else "BLOCKED"
            ),
            "check_id": check_id,
            "evidence": list(check.get("evidence_paths", [])),
            "strict_gate_ids": list(gate_ids),
            "open_strict_gate_ids": open_gate_ids,
            "strict_gate_open": bool(open_gate_ids),
        })

    return {
        "schema_version": "prism.ijhe_objective_coverage_audit.v1",
        "status": status,
        "objective": "일반 옥외 액화수소시설에서 설비 상태부터 방출·확산·점화·최종 피해·빈도 불확실성까지 실시간 진단 가능한 PRISM 모듈",
        "regular_completion_audit_status": completion_audit.get("status"),
        "checks": rows,
        "core_chain_check_ids": [row["id"] for row in core_rows],
        "strict_gate_check_ids": [row["id"] for row in strict_rows],
        "core_blocking_check_ids": core_blocked,
        "strict_blocking_check_ids": strict_blocked,
        "conditional_chain_complete": not core_blocked,
        "strict_facility_qra_claim": strict_qra_ok,
        "physical_validation_claim": physical_ok,
        "frequency_inference_performed": False,
        "completion_criteria": completion_criteria,
        "explicit_exclusions": [
            "field_accident_frequency_collection",
            "sensor_based_frequency_learning",
            "indoor_release_and_confinement",
            "detonation_or_DDT",
            "full_domino_escalation",
        ],
        "interpretation": (
            "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN은 상태 snapshot→native 방출→"
            "consequence→조건부 IR/F-N 연결이 닫혔다는 뜻이다. qualified provider, 독립 물리검증, "
            "엄격한 전체범위가 확보되기 전에는 시설 전체 QRA로 승격하지 않는다."
        ),
    }


__all__ = ["build_ijhe_objective_coverage_audit"]
