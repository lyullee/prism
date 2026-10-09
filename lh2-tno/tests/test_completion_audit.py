from lh2_tno.completion_audit import build_ijhe_completion_audit


def _campaign_result(total=True):
    return {
        "events": [{"id": "event-1"}],
        "cases": [{
            "status": "EXECUTED",
            "termination": {"basis": "synthetic", "time_s": 0.2},
            "mass_ledger": {"end_to_end_residual_kg": 0.0},
        }],
        "timing": {"fresh_physics_cases": 1, "campaign_elapsed_ms": 12.5},
        "total_facility_annual_ir_low_high": {"r1": [1e-6, 2e-6]} if total else None,
        "total_facility_expected_death_fn_low_high": [[], []] if total else None,
    }


def _matrix(complete=True):
    return {
        "matrix_complete": complete,
        "blocking_reasons": [] if complete else ["pipe_hole: UNCOMPUTED"],
        "required_families": ["pipe_hole"],
    }


def _status(validated=True):
    return {
        "physical_validation_claim": validated,
        "physical_validation_evidence_status": "INDEPENDENT_END_TO_END" if validated else "RESTRICTED",
        "equipment_model_binding_status": "ACCIDENT_RELEASE_INTERFACE_BOUND" if validated else "STATE_ONLY_BOUND",
        "equipment_model_binding_component_count": 1,
        "equipment_model_binding_state_supported_component_count": 1,
        "equipment_model_binding_accident_release_supported_component_count": 1 if validated else 0,
        "equipment_model_binding_record": "model_binding.json",
        "provider_release_contract_actual_facility_packet_available": validated,
        "external_provider_evidence_release_inventory_status": "QUALIFIED_ACCIDENT_RELEASE_EXPORT" if validated else "NO_ACCIDENT_RELEASE_EXPORT",
        "one_hz_fresh_physics_demonstrated": False,
        "realtime_monitor_implemented": True,
        "realtime_monitor_module": "src/lh2_tno/service.py",
        "realtime_monitor_test_status": "contract",
        "realtime_monitor_one_hz_claim": False,
        "equipment_provider_release_worklist_status": "READY_FOR_PROVIDER_PACKETS",
        "equipment_provider_release_worklist_event_count": 1,
        "equipment_provider_release_worklist_provider_packet_count": 1,
        "equipment_provider_release_worklist_uncomputed_count": 0,
    }


def _diagnostic_execution(**overrides):
    execution = {
        "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
        "adapter_execution": {
            "provider_instance_id": "storage-tank-01",
        },
        "worklist_item_id": "scope/storage-shell/AREA_0.01%/provider-release",
        "worklist_exact_match": {
            "event_id": True,
            "component_id": True,
            "port_id": True,
            "opening_diameter_m": True,
        },
        "consequence_chain_executed": True,
        "consequence_chain_status": "END_TO_END_DIAGNOSTIC_EXECUTED",
        "consequence_chain_elapsed_ms": 2000.0,
        "fresh_execution_elapsed_ms": 1000.0,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": False,
        "worklist_frequency_bound": False,
        "consequence_context_frequency_bound": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    execution.update(overrides)
    return execution


def _worklist_evidence(**overrides):
    evidence = {
        "status": "PARTIAL_DIAGNOSTIC_EVIDENCE",
        "worklist_event_count": 24,
        "candidate_event_count": 19,
        "exact_match_event_count": 19,
        "strict_packet_valid_event_count": 19,
        "consequence_chain_event_count": 10,
        "qualified_provider_packet_count": 0,
        "frequency_bound": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    evidence.update(overrides)
    return evidence


def _facility_assessment(**overrides):
    assessment = {
        "status": "PARTIAL_FACILITY_SCOPE",
        "facility_total_risk_available": False,
        "complete_facility_qra_claim": False,
        "conditional_diagnostic_facility_risk_available": True,
        "conditional_diagnostic_facility_annual_ir_low_high": {
            "worker-01": [1.0e-6, 2.0e-6]
        },
        "conditional_diagnostic_facility_expected_death_fn_low_high": [
            [[0.0, 0.0]],
            [[0.0, 0.0]],
        ],
        "conditional_diagnostic_facility_coverage": {
            "event_count": 24,
            "case_count": 24,
            "risk_atom_count": 96,
            "uncomputed_case_count": 20,
        },
    }
    assessment.update(overrides)
    return assessment


def test_completion_audit_blocks_incomplete_facility_claim():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {"scenarios": [{"id": "known"}], "facility_credible_interval": False},
    )
    assert report["status"] == "INCOMPLETE_EVIDENCE"
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_passes_only_when_every_claim_gate_is_present():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
    )
    assert report["status"] == "READY_FOR_IJHE_SCOPE"
    assert report["complete_facility_qra_claim"] is True
    assert not report["blocking_reasons"]


def test_completion_audit_reads_legacy_provider_inventory_alias_fail_closed():
    status = _status(False)
    status.pop("provider_release_contract_actual_facility_packet_available")
    status["external_provider_evidence_accident_release_promotion_status"] = "NO_ACCIDENT_RELEASE_EXPORT"
    status["external_provider_evidence_accident_release_qualified_files"] = 0
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        None,
    )
    packet_check = next(item for item in report["checks"] if item["name"] == "actual_provider_release_packet")
    assert packet_check["status"] == "BLOCKED"
    assert packet_check["evidence"] == {
        "actual_facility_packet_available": False,
        "release_inventory_status": "NO_ACCIDENT_RELEASE_EXPORT",
        "qualified_packet_count": 0,
    }


def test_completion_audit_unwraps_campaign_uncertainty_ledger():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {
            "literature_frequency_uncertainty": {
                "scenarios": [{"id": "known"}],
                "facility_credible_interval": False,
            }
        },
    )
    uncertainty_check = next(
        item for item in report["checks"] if item["name"] == "frequency_uncertainty_reported"
    )
    assert uncertainty_check["status"] == "BLOCKED"
    assert uncertainty_check["evidence"] == {
        "uncertainty_result_present": True,
        "scenario_count": 1,
        "facility_credible_interval": False,
    }


def test_completion_audit_unwraps_facility_assessment_uncertainty_ledger():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {
            "frequency_uncertainty": {
                "scenarios": [{"id": "known"}],
                "facility_credible_interval": False,
            },
            "assessment_digest": "assessment-wrapper",
        },
    )
    uncertainty_check = next(
        item for item in report["checks"] if item["name"] == "frequency_uncertainty_reported"
    )
    assert uncertainty_check["status"] == "BLOCKED"
    assert uncertainty_check["evidence"]["scenario_count"] == 1


def test_completion_audit_blocks_provider_worklist_with_uncomputed_events():
    status = _status(True)
    status["equipment_provider_release_worklist_provider_packet_count"] = 0
    status["equipment_provider_release_worklist_uncomputed_count"] = 1
    report = build_ijhe_completion_audit(
        status,
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
    )
    assert report["status"] == "INCOMPLETE_EVIDENCE"
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["provider_packet_count"] == 0


def test_completion_audit_prefers_provider_worklist_file_over_stale_status():
    status = _status(True)
    report = build_ijhe_completion_audit(
        status,
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        {
            "status": "READY_FOR_PROVIDER_PACKETS",
            "generated_event_count": 2,
            "provider_packet_count": 0,
            "status_counts": {"UNCOMPUTED_PROVIDER_PACKET": 2},
            "model_binding_diagnostic_release_adapter_component_count": 7,
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["source"] == "provider_worklist"
    assert check["evidence"]["frequency_event_count"] == 2
    assert check["evidence"]["diagnostic_release_adapter_component_count"] == 7


def test_completion_audit_records_resolved_diagnostic_adapter_execution_contract():
    status = _status(False)
    status.update({
        "diagnostic_adapter_runner_implemented": True,
        "diagnostic_adapter_registry_live_audit_status": (
            "DECLARED_ADAPTERS_RESOLVED_PROVIDER_INSTANCES_REQUIRED; 7/7"
        ),
        "diagnostic_adapter_registry_adapter_count": 7,
        "diagnostic_adapter_registry_resolved_adapter_count": 7,
        "diagnostic_adapter_registry_provider_instance_count": 0,
        "diagnostic_adapter_registry_qualified_packet_count": 0,
        "diagnostic_adapter_registry_live_audit_record": "registry.json",
    })
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        None,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_adapter_execution_contract"
    )
    assert check["status"] == "PASS"
    assert check["evidence"]["resolved_adapter_count"] == 7


def test_completion_audit_records_nonqualifying_worklist_chain_execution():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_adapter_execution=_diagnostic_execution(_record_path="runner.json"),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_execution_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert check["evidence"]["record"] == "runner.json"
    assert check["evidence"]["provider_instance_id"] == "storage-tank-01"
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_rejects_invalid_diagnostic_execution_without_promoting_it():
    execution = _diagnostic_execution(
        worklist_exact_match={
            "event_id": True,
            "component_id": True,
            "port_id": False,
            "opening_diameter_m": True,
        },
        worklist_frequency_bound=True,
    )
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        diagnostic_adapter_execution=execution,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_execution_evidence"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["status"] == "READY_FOR_IJHE_SCOPE"


def test_completion_audit_records_partial_provider_worklist_coverage():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_worklist_evidence=_worklist_evidence(_record_path="evidence.json"),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_packet_coverage_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["exact_match_event_count"] == 19
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_records_conditional_facility_ir_fn_without_promoting_total():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        facility_assessment=_facility_assessment(),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_conditional_facility_risk_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert check["evidence"]["coverage"]["risk_atom_count"] == 96
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_rejects_worklist_evidence_without_chain_or_strict_packets():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        diagnostic_worklist_evidence=_worklist_evidence(
            strict_packet_valid_event_count=18,
            consequence_chain_event_count=0,
        ),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_packet_coverage_evidence"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["status"] == "READY_FOR_IJHE_SCOPE"
