from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
Fraction = Annotated[float, Field(ge=0, le=1)]
Vector = tuple[float, float, float]
Name = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PropertyBasis(Contract):
    fluid: Literal["Hydrogen", "ParaHydrogen"]
    backend: Literal["CoolProp-HEOS"] = "CoolProp-HEOS"
    energy_reference: Name


class Component(Contract):
    id: Name
    kind: Literal["storage_tank", "pipe", "valve", "vent_stack", "vaporizer", "pump", "reliquefier", "boundary"]
    position_enu_m: Vector
    property_basis: PropertyBasis
    parameters_si: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def parameters(self):
        if any(not math.isfinite(x) for x in self.parameters_si.values()):
            raise ValueError("finite SI parameters required")
        required = {"storage_tank": ("volume_m3",), "pipe": ("length_m", "diameter_m"),
                    "vent_stack": ("length_m", "diameter_m")}.get(self.kind, ())
        if any(self.parameters_si.get(k, 0) <= 0 for k in required):
            raise ValueError(f"positive parameters required: {required}")
        return self


class Port(Contract):
    id: Name
    component_id: Name
    phase: Literal["liquid", "vapour", "two_phase", "any"]
    direction: Literal["in", "out", "bidirectional"]
    # Optional outlet coordinate.  When a provider resolves a release at a
    # port, the consequence boundary can require this coordinate to match.
    position_enu_m: Vector | None = None


class Edge(Contract):
    id: Name
    source_port: Name
    target_port: Name


class Receptor(Contract):
    id: Name
    position_enu_m: Vector


class Facility(Contract):
    id: Name
    configuration_origin: Literal["synthetic", "reviewed_design", "field_confirmed"]
    environment: Literal["outdoor", "indoor", "semi_enclosed"]
    components: tuple[Component, ...]
    ports: tuple[Port, ...]
    edges: tuple[Edge, ...]
    receptors: tuple[Receptor, ...]

    @model_validator(mode="after")
    def topology(self):
        for items in (self.components, self.ports, self.edges, self.receptors):
            if len({x.id for x in items}) != len(items):
                raise ValueError("duplicate entity id")
        if not self.components:
            raise ValueError("at least one component required")
        components = {x.id: x for x in self.components}
        ports = {x.id: x for x in self.ports}
        if any(x.component_id not in components for x in self.ports):
            raise ValueError("orphan port")
        seen = set()
        for edge in self.edges:
            if edge.source_port not in ports or edge.target_port not in ports:
                raise ValueError("unknown edge endpoint")
            a, b = ports[edge.source_port], ports[edge.target_port]
            if a.id == b.id or a.component_id == b.component_id:
                raise ValueError("self connection")
            if a.direction == "in" or b.direction == "out":
                raise ValueError("connection opposes port direction")
            if a.phase != "any" and b.phase != "any" and a.phase != b.phase:
                raise ValueError("phase-incompatible connection")
            if components[a.component_id].property_basis != components[b.component_id].property_basis:
                raise ValueError("explicit property/energy-reference conversion required")
            pair = (a.id, b.id)
            if pair in seen:
                raise ValueError("duplicate physical connection")
            seen.add(pair)
        return self


class PartitionStep(Contract):
    time_s: Nonnegative
    total_kg_s: Nonnegative
    gas_kg_s: Nonnegative
    airborne_liquid_kg_s: Nonnegative
    ground_liquid_kg_s: Nonnegative

    @model_validator(mode="after")
    def closes(self):
        out = self.gas_kg_s + self.airborne_liquid_kg_s + self.ground_liquid_kg_s
        if not math.isclose(self.total_kg_s, out, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError("source mass partition does not close")
        return self


class SourceLedger(Contract):
    source_stage: Literal["nozzle_to_ground_partition"]
    property_basis: PropertyBasis
    position_enu_m: Vector
    direction_enu: Vector
    duration_s: Positive
    integration_rule: Literal["left_constant"]
    initial_available_mass_kg: Positive
    steps: tuple[PartitionStep, ...]
    model_revision: Name
    request_digest: Name
    energy_balance_scope: Literal["latent_evaporation_accounting_only", "total_energy", "unverified"]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def ledger(self):
        if not math.isclose(sum(x*x for x in self.direction_enu), 1, abs_tol=1e-8):
            raise ValueError("unit source direction required")
        if not self.steps or self.steps[0].time_s != 0:
            raise ValueError("source history must start at zero")
        if any(b.time_s <= a.time_s for a, b in zip(self.steps, self.steps[1:])):
            raise ValueError("source times must increase")
        if self.steps[-1].time_s >= self.duration_s:
            raise ValueError("left-constant history stores interval starts")
        if self.released_mass_kg > self.initial_available_mass_kg * (1+1e-8):
            raise ValueError("source release exceeds available inventory")
        return self

    @property
    def released_mass_kg(self) -> float:
        ends = [x.time_s for x in self.steps[1:]] + [self.duration_s]
        return sum(x.total_kg_s * (end-x.time_s) for x, end in zip(self.steps, ends))

    def branch_mass_kg(self, branch: Literal["gas_kg_s", "airborne_liquid_kg_s", "ground_liquid_kg_s"]) -> float:
        ends = [x.time_s for x in self.steps[1:]] + [self.duration_s]
        return sum(getattr(x, branch) * (end-x.time_s) for x, end in zip(self.steps, ends))
