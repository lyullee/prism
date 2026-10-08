"""Generic digital-twin equipment manifest and promotion gate.

The manifest is the small, facility-neutral contract between an equipment
model and PRISM.  It records what the provider actually knows (components,
ports, connections and scenario controls) and never fills a missing tag,
position or parameter with a guessed value.  A manifest can therefore be
used for any outdoor LH2 facility; a particular inspection centre is only one
possible producer of the JSON input.

This module deliberately stops before numerical consequence evaluation.  It
answers the more basic question first: *is this equipment state complete
enough to create a PRISM Facility and which scenarios remain uncomputed?*
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .contracts import (
    Component,
    Contract,
    Edge,
    Facility,
    Name,
    Port,
    PropertyBasis,
    Receptor,
    Vector,
)


ComponentKind = Literal[
    "storage_tank", "pipe", "valve", "vent_stack", "vaporizer",
    "pump", "reliquefier", "boundary",
]
ScenarioStatus = Literal["declared", "screening_only", "excluded"]


class ManifestComponent(Contract):
    """One provider component.

    ``position_enu_m`` and ``property_basis`` are optional at the manifest
    boundary so an incomplete provider export can be diagnosed rather than
    rejected before the audit report is produced.
    """

    id: Name
    kind: ComponentKind
    position_enu_m: Vector | None = None
    property_basis: PropertyBasis | None = None
    parameters_si: dict[str, float] = Field(default_factory=dict)
    source_status: Literal["declared", "candidate", "unresolved"] = "declared"
    source_provenance: Name | None = None


class ManifestPort(Contract):
    id: Name
    component_id: Name
    phase: Literal["liquid", "vapour", "two_phase", "any"]
    direction: Literal["in", "out", "bidirectional"]
    position_enu_m: Vector | None = None
    source_status: Literal["declared", "candidate", "unresolved"] = "declared"
    source_provenance: Name | None = None


class ManifestEdge(Contract):
    id: Name
    source_port: Name
    target_port: Name
    source_status: Literal["declared", "candidate", "unresolved"] = "declared"
    source_provenance: Name | None = None


class ManifestScenario(Contract):
    id: Name
    status: ScenarioStatus = "declared"
    required_ports: tuple[Name, ...] = ()
    required_controls: tuple[Name, ...] = ()
    observed_controls: tuple[Name, ...] = ()
    provenance: Name | None = None
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_requirements(self):
        if len(set(self.required_ports)) != len(self.required_ports):
            raise ValueError("scenario required_ports must be unique")
        if len(set(self.required_controls)) != len(self.required_controls):
            raise ValueError("scenario required_controls must be unique")
        if len(set(self.observed_controls)) != len(self.observed_controls):
            raise ValueError("scenario observed_controls must be unique")
        return self


class EquipmentManifest(Contract):
    """Facility-neutral provider export used by the promotion gate."""

    schema_version: Literal["1.0"] = "1.0"
    facility_id: Name
    environment: Literal["outdoor", "indoor", "semi_enclosed"]
    configuration_origin: Literal["synthetic", "reviewed_design", "field_confirmed"]
    components: tuple[ManifestComponent, ...]
    ports: tuple[ManifestPort, ...] = ()
    edges: tuple[ManifestEdge, ...] = ()
    receptors: tuple[Receptor, ...] = ()
    scenarios: tuple[ManifestScenario, ...] = ()
    provider_source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_ids(self):
        for values, label in (
            (self.components, "component"), (self.ports, "port"),
            (self.edges, "edge"), (self.receptors, "receptor"),
            (self.scenarios, "scenario"),
        ):
            if len({item.id for item in values}) != len(values):
                raise ValueError(f"duplicate {label} id")
        return self

    @classmethod
    def from_json(cls, path: str | Path) -> "EquipmentManifest":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def to_facility(self) -> Facility:
        """Build the strict PRISM Facility only after ``audit`` is executable."""
        audit = audit_manifest(self)
        if audit["status"] != "EXECUTABLE":
            raise ValueError("manifest is not executable; inspect audit blocking_reasons")
        return Facility(
            id=self.facility_id,
            configuration_origin=self.configuration_origin,
            environment=self.environment,
            components=tuple(
                Component(
                    id=x.id, kind=x.kind, position_enu_m=x.position_enu_m,
                    property_basis=x.property_basis, parameters_si=x.parameters_si,
                ) for x in self.components
            ),
            ports=tuple(
                Port(
                    id=x.id, component_id=x.component_id, phase=x.phase,
                    direction=x.direction, position_enu_m=x.position_enu_m,
                ) for x in self.ports
            ),
            edges=tuple(Edge(id=x.id, source_port=x.source_port, target_port=x.target_port) for x in self.edges),
            receptors=self.receptors,
        )


def _component_blockers(manifest: EquipmentManifest) -> tuple[dict, ...]:
    ports_by_component: dict[str, list[ManifestPort]] = {}
    for port in manifest.ports:
        ports_by_component.setdefault(port.component_id, []).append(port)
    rows = []
    for component in manifest.components:
        reasons: list[str] = []
        if component.position_enu_m is None:
            reasons.append("component position_enu_m is missing")
        if component.property_basis is None:
            reasons.append("component property_basis is missing")
        if component.source_status != "declared":
            reasons.append(f"component source_status={component.source_status}")
        if not ports_by_component.get(component.id):
            reasons.append("no declared port mapping")
        rows.append({
            "component_id": component.id,
            "kind": component.kind,
            "status": "EXECUTABLE" if not reasons else "UNCOMPUTED",
            "port_count": len(ports_by_component.get(component.id, ())),
            "blocking_reasons": reasons,
        })
    return tuple(rows)


def audit_manifest(manifest: EquipmentManifest) -> dict:
    """Return an explicit promotion report without inferring missing data.

    ``EXECUTABLE`` means the strict Facility contract can be constructed and
    all declared scenarios have their required ports and controls.  A
    ``PARTIAL`` result is useful for topology review but must not be passed to
    a facility risk campaign.  ``EXCLUDED`` is reserved for environments
    outside the declared outdoor scope.
    """
    component_ids = {x.id for x in manifest.components}
    port_ids = {x.id for x in manifest.ports}
    reasons: list[str] = []
    if manifest.environment != "outdoor":
        reasons.append("declared scope is outdoor only")
    if not manifest.components:
        reasons.append("no components declared")
    component_rows = _component_blockers(manifest)
    if any(row["status"] != "EXECUTABLE" for row in component_rows):
        reasons.append("one or more components lack a complete position/property/port contract")
        for row in component_rows:
            reasons.extend(f"component {row['component_id']}: {reason}" for reason in row["blocking_reasons"])
    for port in manifest.ports:
        if port.component_id not in component_ids:
            reasons.append(f"orphan port: {port.id}")
        if port.source_status != "declared":
            reasons.append(f"port {port.id} source_status={port.source_status}")
    for edge in manifest.edges:
        if edge.source_port not in port_ids or edge.target_port not in port_ids:
            reasons.append(f"edge {edge.id} has an unresolved port endpoint")
        if edge.source_status != "declared":
            reasons.append(f"edge {edge.id} source_status={edge.source_status}")
    # Reuse the strict PRISM topology/parameter validator.  This catches
    # wrong directions, phase mismatches, missing required tank/pipe geometry
    # and property-basis mismatches without inventing a repair.
    if not reasons:
        try:
            Facility(
                id=manifest.facility_id,
                configuration_origin=manifest.configuration_origin,
                environment=manifest.environment,
                components=tuple(
                    Component(
                        id=x.id, kind=x.kind, position_enu_m=x.position_enu_m,
                        property_basis=x.property_basis, parameters_si=x.parameters_si,
                    ) for x in manifest.components
                ),
                ports=tuple(
                    Port(
                        id=x.id, component_id=x.component_id, phase=x.phase,
                        direction=x.direction, position_enu_m=x.position_enu_m,
                    ) for x in manifest.ports
                ),
                edges=tuple(Edge(id=x.id, source_port=x.source_port, target_port=x.target_port) for x in manifest.edges),
                receptors=manifest.receptors,
            )
        except (ValueError, TypeError) as error:
            reasons.append(f"strict PRISM Facility validation failed: {error}")
    scenario_rows = []
    for scenario in manifest.scenarios:
        missing_ports = sorted(set(scenario.required_ports) - port_ids)
        missing_controls = sorted(set(scenario.required_controls) - set(scenario.observed_controls))
        row_reasons = list(scenario.limitations)
        if missing_ports:
            row_reasons.append("required ports are not declared: " + ", ".join(missing_ports))
        if missing_controls:
            row_reasons.append("required controls are not observed: " + ", ".join(missing_controls))
        if scenario.status == "excluded":
            row_reasons.append("provider marked scenario excluded")
        scenario_status = "EXECUTABLE" if not row_reasons else "UNCOMPUTED"
        scenario_rows.append({
            "scenario_id": scenario.id,
            "status": scenario_status,
            "missing_required_ports": missing_ports,
            "missing_required_controls": missing_controls,
            "blocking_reasons": row_reasons,
        })
        if row_reasons:
            reasons.append(f"scenario {scenario.id} is not executable")
    if manifest.environment != "outdoor":
        status = "EXCLUDED"
    elif not manifest.components or reasons:
        status = "PARTIAL"
    else:
        status = "EXECUTABLE"
    return {
        "status": status,
        "facility_id": manifest.facility_id,
        "manifest_digest": manifest.digest(),
        "component_coverage": list(component_rows),
        "scenario_coverage": scenario_rows,
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "can_build_facility": status == "EXECUTABLE",
        "promotion_policy": {
            "missing_tags_are_not_inferred": True,
            "missing_positions_are_not_inferred": True,
            "missing_controls_are_not_inferred": True,
            "screening_values_are_not_promoted_to_field_confirmed": True,
            "facility_risk_requires_status": "EXECUTABLE",
        },
        "scope": "generic outdoor LH2 equipment manifest; no inspection-centre identifiers are required",
    }


def audit_json(path: str | Path) -> dict:
    manifest = EquipmentManifest.from_json(path)
    return audit_manifest(manifest)


def write_audit(manifest_path: str | Path, output_path: str | Path) -> dict:
    result = audit_json(manifest_path)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
