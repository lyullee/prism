"""Common execution contract for PRISM-side LH2 diagnostic adapters.

The facility binding catalog records seven PRISM-side adapters that can run
screening or synthetic diagnostics while an external equipment package is
still missing a qualified accident-history export.  Before this module each
script was discoverable only by its filename.  This runner makes the seam
explicit:

* the catalog is the source of the component-kind to adapter mapping;
* a provider object must be registered for a component kind explicitly;
* the provider is called only through ``export_accident_history``; and
* the existing strict PRISM export validators are the only promotion path.

The runner never constructs a provider from a normal-state model, guesses a
provider constructor argument, or promotes synthetic/screening evidence to a
qualified packet.  It is therefore suitable for a realtime resolver to call
after it has selected a scenario and assembled an explicit provider request.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import importlib
import inspect
from pathlib import Path
from typing import Any

from .equipment_accident_export import (
    AccidentHistoryProvider,
    AccidentReleaseExportRequest,
    AccidentReleaseExportResult,
    EmergencyReliefExportRequest,
    InventoryReleaseExportRequest,
    EquipmentAccidentExportError,
    export_equipment_emergency_relief_history,
    export_equipment_gas_accident_history,
    export_equipment_inventory_release_history,
    export_equipment_liquid_accident_history,
)


DIAGNOSTIC_ADAPTER_REGISTRY_SCHEMA = "prism.diagnostic_adapter_registry.v1"
_EVIDENCE_STATUSES = {"synthetic_diagnostic", "screening_only"}
_RELEASE_KINDS = {
    "gas",
    "liquid",
    "emergency_relief",
    "inventory_gas",
    "inventory_liquid",
}


class DiagnosticAdapterRunnerError(ValueError):
    """Raised when a diagnostic adapter cannot satisfy the common seam."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiagnosticAdapterRunnerError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class DiagnosticAdapterSpec:
    """One catalog declaration, kept separate from a provider instance."""

    component_kind: str
    module: str
    provider_class: str
    evidence_status: str

    def __post_init__(self) -> None:
        _text(self.component_kind, "component_kind")
        _text(self.module, "module")
        _text(self.provider_class, "provider_class")
        if self.evidence_status not in _EVIDENCE_STATUSES:
            raise DiagnosticAdapterRunnerError(
                f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}"
            )


@dataclass(frozen=True)
class DiagnosticAdapterExecution:
    """Result of one adapter call plus its non-qualification ledger."""

    spec: DiagnosticAdapterSpec
    result: AccidentReleaseExportResult

    @property
    def promoted(self) -> bool:
        """Whether the strict exporter accepted qualified actual evidence."""

        return self.result.provider_packet_promoted

    def audit_record(self) -> dict[str, Any]:
        """Return JSON-friendly metadata without serialising the release model."""

        return {
            "component_kind": self.spec.component_kind,
            "adapter_module": self.spec.module,
            "adapter_provider_class": self.spec.provider_class,
            "evidence_status": self.spec.evidence_status,
            "provider_result_digest": self.result.provider_result_digest,
            "promotion_status": self.result.promotion_status,
            "provider_packet_promoted": self.promoted,
            "provider_method": self.result.provider_method,
            "provider_export_schema": self.result.provider_export_schema,
        }


def _catalog_object(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise DiagnosticAdapterRunnerError(
                f"cannot read diagnostic adapter catalog: {path}"
            ) from error
    else:
        payload = dict(value)
    if not isinstance(payload, dict):
        raise DiagnosticAdapterRunnerError("diagnostic adapter catalog must be an object")
    return payload


def load_diagnostic_adapter_specs(
    binding_catalog: Mapping[str, Any] | str | Path,
) -> tuple[DiagnosticAdapterSpec, ...]:
    """Load available adapter declarations from the model binding catalog."""

    catalog = _catalog_object(binding_catalog)
    raw_bindings = catalog.get("bindings")
    if not isinstance(raw_bindings, list):
        raise DiagnosticAdapterRunnerError("binding catalog bindings must be an array")
    specs: list[DiagnosticAdapterSpec] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise DiagnosticAdapterRunnerError(f"bindings[{index}] must be an object")
        kind = _text(raw.get("component_kind"), f"bindings[{index}].component_kind")
        if kind in seen:
            raise DiagnosticAdapterRunnerError(f"duplicate adapter component kind: {kind}")
        seen.add(kind)
        adapter = raw.get("diagnostic_release_adapter")
        if not isinstance(adapter, Mapping) or adapter.get("status", "missing") != "available":
            continue
        specs.append(
            DiagnosticAdapterSpec(
                component_kind=kind,
                module=_text(adapter.get("module"), f"bindings[{index}].adapter.module"),
                provider_class=_text(
                    adapter.get("provider_class"),
                    f"bindings[{index}].adapter.provider_class",
                ),
                evidence_status=_text(
                    adapter.get("evidence_status"),
                    f"bindings[{index}].adapter.evidence_status",
                ),
            )
        )
    return tuple(specs)


def _module_name(module: str) -> str:
    value = module.strip().replace("\\", "/")
    if value.endswith(".py"):
        value = value[:-3]
    return value.replace("/", ".")


class DiagnosticAdapterRunner:
    """Resolve and execute explicitly registered equipment adapters.

    Provider instances are deliberately supplied by the host application.
    Their constructors require equipment-model state and scenario parameters;
    silently inventing those arguments would turn a diagnostic helper into an
    untraceable accident model.
    """

    def __init__(self, specs: tuple[DiagnosticAdapterSpec, ...] | list[DiagnosticAdapterSpec]):
        self._specs = {spec.component_kind: spec for spec in specs}
        if len(self._specs) != len(specs):
            raise DiagnosticAdapterRunnerError("duplicate component kind in adapter specs")
        self._providers: dict[str, AccidentHistoryProvider] = {}

    @classmethod
    def from_binding_catalog(
        cls, binding_catalog: Mapping[str, Any] | str | Path
    ) -> "DiagnosticAdapterRunner":
        return cls(list(load_diagnostic_adapter_specs(binding_catalog)))

    @property
    def specs(self) -> tuple[DiagnosticAdapterSpec, ...]:
        return tuple(self._specs.values())

    def resolve_provider_class(self, component_kind: str) -> type[Any]:
        """Import a declared adapter class and verify the common method."""

        spec = self._spec(component_kind)
        try:
            module = importlib.import_module(_module_name(spec.module))
            provider_class = getattr(module, spec.provider_class)
        except (ImportError, AttributeError) as error:
            raise DiagnosticAdapterRunnerError(
                f"cannot resolve diagnostic adapter {spec.module}:{spec.provider_class}"
            ) from error
        if not inspect.isclass(provider_class) or not callable(
            getattr(provider_class, "export_accident_history", None)
        ):
            raise DiagnosticAdapterRunnerError(
                f"diagnostic adapter {spec.component_kind} must expose export_accident_history(request)"
            )
        return provider_class

    def register_provider(
        self, component_kind: str, provider: AccidentHistoryProvider
    ) -> None:
        """Bind one host-created provider instance to a component kind."""

        self._spec(component_kind)
        if not callable(getattr(provider, "export_accident_history", None)):
            raise DiagnosticAdapterRunnerError(
                "registered provider must expose export_accident_history(request)"
            )
        self._providers[component_kind] = provider

    def execute(
        self,
        component_kind: str,
        request: AccidentReleaseExportRequest
        | EmergencyReliefExportRequest
        | InventoryReleaseExportRequest
        | Mapping[str, Any],
        *,
        provider: AccidentHistoryProvider | None = None,
        release_kind: str = "gas",
    ) -> DiagnosticAdapterExecution:
        """Call one provider through the strict PRISM export contract."""

        if release_kind not in _RELEASE_KINDS:
            raise DiagnosticAdapterRunnerError(
                f"release_kind must be one of {sorted(_RELEASE_KINDS)}"
            )
        spec = self._spec(component_kind)
        selected = provider if provider is not None else self._providers.get(component_kind)
        if selected is None:
            raise DiagnosticAdapterRunnerError(
                f"no provider instance registered for component kind {component_kind}"
            )
        try:
            if release_kind == "gas":
                result = export_equipment_gas_accident_history(selected, request)  # type: ignore[arg-type]
            elif release_kind == "liquid":
                result = export_equipment_liquid_accident_history(selected, request)  # type: ignore[arg-type]
            elif release_kind == "emergency_relief":
                result = export_equipment_emergency_relief_history(selected, request)  # type: ignore[arg-type]
            elif release_kind == "inventory_gas":
                result = export_equipment_inventory_release_history(
                    selected, request, release_kind="gas"  # type: ignore[arg-type]
                )
            else:
                result = export_equipment_inventory_release_history(
                    selected, request, release_kind="liquid"  # type: ignore[arg-type]
                )
        except (EquipmentAccidentExportError, TypeError, ValueError) as error:
            raise DiagnosticAdapterRunnerError(
                f"diagnostic adapter execution failed for {component_kind}: {error}"
            ) from error
        return DiagnosticAdapterExecution(spec=spec, result=result)

    def _spec(self, component_kind: str) -> DiagnosticAdapterSpec:
        kind = _text(component_kind, "component_kind")
        try:
            return self._specs[kind]
        except KeyError as error:
            raise DiagnosticAdapterRunnerError(
                f"no diagnostic adapter is declared for component kind {kind}"
            ) from error


__all__ = [
    "DIAGNOSTIC_ADAPTER_REGISTRY_SCHEMA",
    "DiagnosticAdapterExecution",
    "DiagnosticAdapterRunner",
    "DiagnosticAdapterRunnerError",
    "DiagnosticAdapterSpec",
    "load_diagnostic_adapter_specs",
]
