from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import scripts.bind_native_full_scope_union_evidence as binder


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_union_binder_keeps_audit_domains_in_their_named_arguments(tmp_path, monkeypatch) -> None:
    union = tmp_path / "union"
    union.mkdir()
    for name in (
        "scope_matrix.json",
        "campaign_result.json",
        "facility_assessment.json",
        "facility_case_packet_coverage.json",
        "verification.json",
    ):
        _write(union / name, {})
    _write(union / "frequency_scenarios.json", {"scenarios": [{"id": "published"}]})

    required = {}
    current_status = _write(tmp_path / "current_status.json", required)
    provider_worklist = _write(tmp_path / "provider_worklist.json", {"kind": "worklist"})
    registry = _write(tmp_path / "registry.json", {"kind": "registry"})
    domain = _write(tmp_path / "domain.json", {"kind": "domain"})
    paths = {
        key: _write(tmp_path / f"{key}.json", {})
        for key in (
            "pool_record",
            "equipment_audit",
            "native_contract",
            "external_sweep",
            "ijhe_audit_source",
            "vertical_handoff_result",
            "realtime_cache_benchmark",
        )
    }

    observed: dict[str, object] = {}

    def fake_matrix(*args, **kwargs):
        observed["matrix_kwargs"] = kwargs
        return {
            "status": "RESTRICTED",
            "decision": "FACILITY_QRA_WITHHELD",
            "evidence_domains": [],
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        }

    def fake_audit(current, scope, campaign, **kwargs):
        observed.update(kwargs)
        return {
            "status": "INCOMPLETE_EVIDENCE",
            "checks": [{"status": "PASS"}],
            "blocking_reasons": [],
        }

    monkeypatch.setattr(binder, "build_validation_evidence_matrix", fake_matrix)
    monkeypatch.setattr(binder, "build_ijhe_completion_audit", fake_audit)

    optional_names = (
        "native_full_bore_result",
        "state_snapshot_binding_audit",
        "native_state_snapshot_campaign_ledger",
        "native_scope_packet_catalog_verification",
        "native_model_contract_audit",
        "frequency_provenance_report",
        "diagnostic_worklist_evidence",
        "native_packet_campaign_ledger",
        "native_binding_reconciliation",
        "observed_state_evidence",
        "observed_state_model_binding_audit",
        "external_equipment_model_contract_audit",
        "slabx_validation_evidence",
        "slabx_direct_comparison_evidence",
        "slabx_independent_comparison_evidence",
        "scope_ledger_consistency",
        "risk_atom_chain_audit",
        "equipment_state_release_audit",
        "facility_aggregate_closure_audit",
        "facility_component_contribution_audit",
        "facility_frequency_uncertainty_audit",
        "isolation_union_extension_verification",
    )
    args = SimpleNamespace(
        union_dir=union,
        current_status=current_status,
        pool_record=paths["pool_record"],
        equipment_audit=paths["equipment_audit"],
        native_contract=paths["native_contract"],
        external_sweep=paths["external_sweep"],
        ijhe_audit_source=paths["ijhe_audit_source"],
        provider_worklist=provider_worklist,
        diagnostic_adapter_registry=registry,
        vertical_handoff_result=paths["vertical_handoff_result"],
        realtime_cache_benchmark=paths["realtime_cache_benchmark"],
        domain_recovery_audit=domain,
    )
    for name in optional_names:
        setattr(args, name, None)
    args.slabx_direct_comparison_evidence = domain
    args.slabx_independent_comparison_evidence = domain

    binder.run(args)

    uncertainty = observed["uncertainty_result"]
    assert isinstance(uncertainty, dict)
    assert uncertainty["scenarios"] == [{"id": "published"}]
    assert observed["provider_worklist"]["kind"] == "worklist"
    assert observed["diagnostic_adapter_registry"]["kind"] == "registry"
    assert observed["facility_assessment"]["_record_path"].endswith("facility_assessment.json")
    assert observed["domain_recovery_audit"]["kind"] == "domain"
    assert observed["matrix_kwargs"]["slabx_direct_comparison_path"] == domain
    assert observed["matrix_kwargs"]["slabx_independent_comparison_path"] == domain
