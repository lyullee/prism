import json
from pathlib import Path

from lh2_tno.external_model_contract_audit import audit_external_model_contract


def _catalog(module="lh2dt.layered_tank", model_class="LayeredTank", source_path="external/src/lh2dt/layered_tank.py"):
    return {
        "schema_version": "prism.equipment_model_binding.v1",
        "facility_neutral": True,
        "bindings": [{
            "component_kind": "storage_tank",
            "model_package": module,
            "model_class": model_class,
            "model_revision": "test",
            "source_path": source_path,
            "diagnostic_release_adapter": {"status": "missing"},
        }],
    }


def test_external_audit_distinguishes_native_missing_from_wrapper(tmp_path):
    root = tmp_path / "external"
    source = root / "src" / "lh2dt"
    source.mkdir(parents=True)
    (source / "layered_tank.py").write_text(
        "class LayeredTank:\n    def simulate(self): ...\n", encoding="utf-8"
    )
    report = audit_external_model_contract(_catalog(), root)
    assert report["status"] == "NATIVE_ACCIDENT_EXPORT_MISSING"
    assert report["native_accident_export_component_count"] == 0
    assert report["rows"][0]["native_normal_state_methods"] == ["simulate"]
    assert report["provider_packet_promoted"] is False
    assert report["external_model_git_provenance"]["repository_detected"] is False


def test_external_audit_records_native_export_and_adapter_contract(tmp_path):
    root = tmp_path / "external"
    source = root / "src" / "lh2dt"
    source.mkdir(parents=True)
    (source / "layered_tank.py").write_text(
        "class LayeredTank:\n    def simulate(self): ...\n    def export_accident_history(self, request): ...\n",
        encoding="utf-8",
    )
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "class Provider:\n    def export_accident_history(self, request): ...\n", encoding="utf-8"
    )
    catalog = _catalog()
    catalog["bindings"][0]["diagnostic_release_adapter"] = {
        "status": "available",
        "module": str(adapter),
        "provider_class": "Provider",
        "evidence_status": "synthetic_diagnostic",
    }
    report = audit_external_model_contract(catalog, root)
    assert report["status"] == "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND"
    assert report["native_accident_export_component_count"] == 1
    assert report["diagnostic_adapter_contract_verified_count"] == 1
    assert report["external_model_git_provenance"]["status"] == "NOT_A_GIT_REPOSITORY"
