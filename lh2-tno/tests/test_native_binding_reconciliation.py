from lh2_tno.native_binding_reconciliation import reconcile_native_binding_catalog


def _catalog(status="supported", ledger="provider_termination_and_mass", schema="prism.resolved_release.v1"):
    return {
        "schema_version": "prism.equipment_model_binding.v1",
        "bindings": [{
            "component_kind": "pipe",
            "model_package": "lh2dt.dynamic_pipe",
            "model_class": "DynamicHEMPipe",
            "accident_release_export_status": status,
            "termination_ledger_status": ledger,
            "provider_export_schema": schema,
        }],
    }


def _audit(native=True):
    return {
        "schema_version": "prism.external_model_contract_audit.v1",
        "rows": [{
            "component_kind": "pipe",
            "model_package": "lh2dt.dynamic_pipe",
            "native_accident_export_method": native,
        }],
    }


def test_reconciliation_accepts_native_interface_declaration_without_promotion():
    report = reconcile_native_binding_catalog(_catalog(), _audit())
    assert report["status"] == "RECONCILED_NATIVE_INTERFACES"
    assert report["reconciled_native_component_count"] == 1
    assert report["provider_packet_promoted"] is False
    assert report["frequency_inference_performed"] is False


def test_reconciliation_blocks_stale_state_only_catalog():
    report = reconcile_native_binding_catalog(_catalog(status="missing", ledger="normal_flow_only", schema=None), _audit())
    assert report["status"] == "BLOCKED_STALE_NATIVE_BINDING"
    assert len(report["blocking_reasons"]) == 3


def test_reconciliation_blocks_claim_when_native_method_is_absent():
    report = reconcile_native_binding_catalog(_catalog(), _audit(native=False))
    assert report["status"] == "BLOCKED_STALE_NATIVE_BINDING"
    assert "native method is absent" in report["blocking_reasons"][0]
