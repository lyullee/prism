from pathlib import Path

import pytest

from lh2_tno.diagnostic_adapter_runner import (
    DiagnosticAdapterRunner,
    DiagnosticAdapterRunnerError,
    load_diagnostic_adapter_specs,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "generic_lh2_model_binding.json"


def test_catalog_adapters_resolve_to_explicit_provider_methods():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)

    assert len(runner.specs) == 7
    assert {spec.component_kind for spec in runner.specs} == {
        "storage_tank",
        "pipe",
        "valve",
        "vent_stack",
        "pump",
        "vaporizer",
        "reliquefier",
    }
    for spec in runner.specs:
        provider_class = runner.resolve_provider_class(spec.component_kind)
        assert callable(getattr(provider_class, "export_accident_history", None))
        assert spec.evidence_status == "synthetic_diagnostic"


def test_runner_requires_host_created_provider_instance():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)

    with pytest.raises(DiagnosticAdapterRunnerError, match="no provider instance"):
        runner.execute("storage_tank", {})


def test_runner_does_not_fallback_to_normal_model_method():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)

    class NormalStateOnlyModel:
        def evaluate(self, request):
            return {"normal_state_snapshot": True}

    with pytest.raises(DiagnosticAdapterRunnerError, match="export_accident_history"):
        runner.register_provider("storage_tank", NormalStateOnlyModel())


def test_missing_adapter_is_not_invented_from_catalog():
    catalog = {
        "schema_version": "prism.equipment_model_binding.v1",
        "facility_neutral": True,
        "bindings": [{
            "component_kind": "boundary",
            "model_package": "prism.interface",
            "model_class": "FacilityBoundary",
            "model_revision": "test",
            "state_export_status": "supported",
            "accident_release_export_status": "missing",
            "termination_ledger_status": "missing",
            "provider_export_schema": None,
            "diagnostic_release_adapter": {"status": "missing"},
        }],
    }
    assert load_diagnostic_adapter_specs(catalog) == ()
    runner = DiagnosticAdapterRunner.from_binding_catalog(catalog)
    with pytest.raises(DiagnosticAdapterRunnerError, match="no diagnostic adapter"):
        runner.resolve_provider_class("boundary")
