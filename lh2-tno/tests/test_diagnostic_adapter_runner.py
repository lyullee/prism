from pathlib import Path

import pytest

from lh2_tno.diagnostic_adapter_runner import (
    DiagnosticAdapterSpec,
    DiagnosticAdapterRunner,
    DiagnosticAdapterRunnerError,
    load_diagnostic_adapter_specs,
)
from lh2_tno.service import request_from_equipment_resolver
from test_equipment_accident_export import _Provider, _request
from test_equipment_accident_export import _snapshot
from test_consequence_service import request as consequence_template
from test_provider_release import _defaults


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "generic_lh2_model_binding.json"


class _ConfiguredProvider:
    def __init__(self, marker):
        self.marker = marker

    def export_accident_history(self, request):
        raise AssertionError("construction-only test provider must not export")


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


def test_runner_attaches_strict_release_to_consequence_context_without_frequency():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)
    runner.register_provider("storage_tank", _Provider())
    execution = runner.execute(
        "storage_tank",
        _request(
            component_id="storage-tank-01",
            port_id="tank-out",
            event_id="provider-accident-01",
        ),
        release_kind="gas",
    )
    defaults = _defaults()
    request = runner.to_consequence_request(execution, defaults)

    assert request.source_input is None
    assert request.resolved_release is not None
    assert request.resolved_release.event_id == "provider-accident-01"
    assert request.annual_frequency_per_year is None
    assert request.frequency_event is None


def test_runner_resolver_factory_connects_state_callbacks_to_consequence_request():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)
    provider = _Provider()
    resolver = runner.make_resolver(
        "storage_tank",
        lambda _template, state: _request(
            component_id="storage-tank-01",
            port_id="tank-out",
            event_id=f"provider-accident-{state['values']['PT']['value_si']:.0f}",
        ),
        lambda _template, _state: _defaults(),
        provider=provider,
    )

    request = resolver(
        object(),
        {"values": {"PT": {"value_si": 500000.0}}},
    )

    assert request.resolved_release is not None
    assert request.resolved_release.event_id == "provider-accident-500000"
    assert request.frequency_event is None
    assert len(provider.requests) == 1


def test_runner_resolver_can_bind_canonical_state_snapshot_before_provider_call():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)
    provider = _Provider()
    resolver = runner.make_resolver(
        "storage_tank",
        lambda _template, _state: _request(
            component_id="storage-tank-01",
            port_id="tank-out",
            event_id="provider-accident-with-state",
        ),
        lambda _template, _state: _defaults(),
        provider=provider,
        state_snapshot_builder=lambda _template, _state: _snapshot("storage-tank-01"),
    )

    resolved = resolver(object(), {"values": {"PT": {"value_si": 500000.0}}})

    assert resolved.resolved_release is not None
    handed = provider.requests[0]
    assert handed["state_snapshot"]["component_id"] == "storage-tank-01"
    assert handed["state_snapshot_digest"] == _snapshot("storage-tank-01").digest()


def test_runner_resolver_factory_plugs_into_state_boundary_contract():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)
    resolver = runner.make_resolver(
        "storage_tank",
        lambda _template, _state: _request(
            component_id="storage-tank-01",
            port_id="tank-out",
            event_id="provider-accident-boundary",
        ),
        lambda _template, _state: _defaults(),
        provider=_Provider(),
    )
    resolved = request_from_equipment_resolver(
        consequence_template().model_copy(update={"component_id": "storage-tank-01"}),
        {"values": {"PT": {"value_si": 500000.0}}},
        resolver,
    )

    assert resolved.source_input is None
    assert resolved.resolved_release is not None
    assert resolved.resolved_release.event_id == "provider-accident-boundary"
    assert resolved.annual_frequency_per_year is None


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


def test_provider_can_be_constructed_only_from_explicit_constructor_config():
    runner = DiagnosticAdapterRunner([
        DiagnosticAdapterSpec(
            component_kind="storage_tank",
            module=__name__,
            provider_class="_ConfiguredProvider",
            evidence_status="synthetic_diagnostic",
        )
    ])
    provider = runner.register_provider_from_config(
        "storage_tank", {"marker": "explicit-host-setting"}
    )

    assert provider.marker == "explicit-host-setting"

    with pytest.raises(DiagnosticAdapterRunnerError, match="cannot construct"):
        runner.register_provider_from_config("storage_tank", {})


def test_runner_keeps_multiple_physical_instances_separate():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)
    first = _Provider()
    second = _Provider()
    runner.register_provider_instance("tank-01", "storage_tank", first)
    runner.register_provider_instance("tank-02", "storage_tank", second)

    first_execution = runner.execute(
        "storage_tank",
        _request(
            component_id="tank-01",
            port_id="tank-out",
            event_id="provider-accident-tank-01",
        ),
        provider_instance_id="tank-01",
    )
    second_execution = runner.execute(
        "storage_tank",
        _request(
            component_id="tank-02",
            port_id="tank-out",
            event_id="provider-accident-tank-02",
        ),
        provider_instance_id="tank-02",
    )

    assert runner.provider_instance_ids == ("tank-01", "tank-02")
    assert first_execution.provider_instance_id == "tank-01"
    assert second_execution.provider_instance_id == "tank-02"
    assert len(first.requests) == 1
    assert len(second.requests) == 1


def test_runner_rejects_instance_kind_mismatch_and_duplicate_ids():
    runner = DiagnosticAdapterRunner.from_binding_catalog(CATALOG)
    runner.register_provider_instance("tank-01", "storage_tank", _Provider())

    with pytest.raises(DiagnosticAdapterRunnerError, match="duplicate provider instance"):
        runner.register_provider_instance("tank-01", "storage_tank", _Provider())
    with pytest.raises(DiagnosticAdapterRunnerError, match="bound to storage_tank"):
        runner.execute(
            "pipe",
            _request(
                component_id="tank-01",
                port_id="tank-out",
                event_id="provider-accident-mismatch",
            ),
            provider_instance_id="tank-01",
        )
