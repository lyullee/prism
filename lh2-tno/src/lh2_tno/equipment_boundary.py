"""Resolved atmospheric gas exits supplied by an equipment-twin provider.

The provider owns the flow calculation. This contract never estimates a leak
from P/T or re-runs a tank/nozzle solver. Liquid and underexpanded outlets
need their own source/flash adapter and are deliberately rejected here.
"""
from __future__ import annotations
import math
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Contract, Name, Positive, Nonnegative, Fraction, Vector, PropertyBasis


class ResolvedGasStep(Contract):
    time_s: Nonnegative
    mass_flow_kg_s: Nonnegative
    pressure_pa_abs: Positive
    specific_enthalpy_j_kg: float
    temperature_k: Positive
    density_kg_m3: Positive
    effective_area_m2: Positive
    velocity_m_s: Nonnegative
    area_provenance: Name
    velocity_origin: Literal['provider_resolved', 'mass_continuity_from_declared_area']

    @model_validator(mode='after')
    def continuity(self):
        expected=self.density_kg_m3*self.velocity_m_s*self.effective_area_m2
        if not math.isclose(self.mass_flow_kg_s,expected,rel_tol=1e-8,abs_tol=1e-12):
            raise ValueError('resolved outlet mass/area/density/velocity do not close')
        if self.mass_flow_kg_s==0 and self.velocity_m_s!=0:
            raise ValueError('zero-flow interval requires zero bulk velocity')
        return self


class VerticalGasHandoffState(Contract):
    """One provider-resolved horizontal carrier state at a handoff time."""

    time_s: Nonnegative
    direction_enu: Vector
    velocity_m_s: Positive
    density_kg_m3: Positive
    temperature_k: Positive
    h2_mass_fraction: Fraction
    half_width_m: Positive
    depth_m: Positive
    provenance: Name

    @model_validator(mode='after')
    def valid(self):
        if not math.isclose(sum(x*x for x in self.direction_enu), 1., abs_tol=1e-10, rel_tol=0):
            raise ValueError('vertical handoff requires a unit horizontal direction')
        if abs(self.direction_enu[2]) > 1e-10:
            raise ValueError('vertical handoff direction must be horizontal')
        if self.h2_mass_fraction <= 0:
            raise ValueError('vertical handoff requires a positive hydrogen mass fraction')
        return self


class VerticalGasHandoff(Contract):
    """Provider-resolved state(s) after a vertical gas exit is redirected.

    The adapter is a boundary contract, not a PRISM rotation of a vertical
    jet.  It must provide the handoff position and a horizontal carrier
    section that the downstream SLABx route can consume.  ``states`` may be
    supplied when the provider handoff changes with the release clock; an
    empty tuple means that the scalar state is held for every release step.
    """

    position_enu_m: Vector
    direction_enu: Vector
    velocity_m_s: Positive
    density_kg_m3: Positive
    temperature_k: Positive
    h2_mass_fraction: Fraction
    half_width_m: Positive
    depth_m: Positive
    provenance: Name
    states: tuple[VerticalGasHandoffState, ...] = ()

    @model_validator(mode='after')
    def valid(self):
        if self.position_enu_m[2] <= 0:
            raise ValueError('vertical handoff must be above flat ground')
        base = VerticalGasHandoffState(
            time_s=0., direction_enu=self.direction_enu, velocity_m_s=self.velocity_m_s,
            density_kg_m3=self.density_kg_m3, temperature_k=self.temperature_k,
            h2_mass_fraction=self.h2_mass_fraction, half_width_m=self.half_width_m,
            depth_m=self.depth_m, provenance=self.provenance)
        if self.states:
            if self.states[0].time_s != 0. or len(self.states) > 100:
                raise ValueError('vertical handoff states must start at zero and be bounded')
            if any(b.time_s <= a.time_s for a, b in zip(self.states, self.states[1:])):
                raise ValueError('vertical handoff states require an ordered provider clock')
        return self

    def state_at(self, time_s: float) -> VerticalGasHandoffState:
        """Return the left-held state for one resolved release interval."""
        if not self.states:
            return VerticalGasHandoffState(
                time_s=time_s, direction_enu=self.direction_enu, velocity_m_s=self.velocity_m_s,
                density_kg_m3=self.density_kg_m3, temperature_k=self.temperature_k,
                h2_mass_fraction=self.h2_mass_fraction, half_width_m=self.half_width_m,
                depth_m=self.depth_m, provenance=self.provenance)
        selected = self.states[0]
        for state in self.states:
            if state.time_s > time_s:
                break
            selected = state
        return selected


class ResolvedGasRelease(Contract):
    # Flat provider packets carry their contract version with the resolved
    # boundary itself.  This prevents a normal-flow JSON object with similar
    # fields from being mistaken for a PRISM accident export.
    provider_export_schema: Literal['prism.resolved_release.v1'] = 'prism.resolved_release.v1'
    component_id: Name
    port_id: Name
    event_id: Name
    event_kind: Literal['accidental_leak', 'normal_vent', 'emergency_relief']
    upstream_service: Literal['LH2', 'GH2', 'COLD_GH2']
    upstream_service_provenance: Name
    state_owner: Literal['equipment_twin'] = 'equipment_twin'
    discharge_owner: Literal['equipment_twin'] = 'equipment_twin'
    boundary_kind: Literal['resolved_atmospheric_gas_exit'] = 'resolved_atmospheric_gas_exit'
    enthalpy_convention: Literal['static_exit_enthalpy']
    property_basis: PropertyBasis
    provider_source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider_result_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider_boundary_reference: Name
    input_origin: Literal['synthetic', 'model_prediction', 'reviewed_measurement']
    position_enu_m: Vector
    direction_enu: Vector
    ambient_pressure_pa_abs: Positive
    ambient_temperature_k: Positive
    duration_s: Positive
    available_mass_kg: Positive
    cumulative_mass_out_kg: Nonnegative
    cumulative_static_enthalpy_out_j: float
    steps: tuple[ResolvedGasStep, ...]
    termination_provenance: Name
    vertical_handoff: VerticalGasHandoff | None = None
    # A failure opening can differ from an expanded exit area. Explicitly
    # retain it if attaching an accident-frequency definition.
    failure_opening_diameter_m: Positive | None = None

    @model_validator(mode='after')
    def ledger(self):
        if self.property_basis.energy_reference!=f'CoolProp-HEOS:{self.property_basis.fluid}:native':
            raise ValueError('resolved boundary requires the declared native enthalpy reference')
        if not math.isclose(sum(x*x for x in self.direction_enu),1.,abs_tol=1e-10,rel_tol=0):
            raise ValueError('unit ENU outlet direction required')
        if abs(self.direction_enu[2]) > 1e-10:
            if abs(self.direction_enu[0]) > 1e-10 or abs(self.direction_enu[1]) > 1e-10 or self.vertical_handoff is None:
                raise ValueError('vertical exit requires a provider-resolved horizontal handoff adapter')
        elif self.vertical_handoff is not None:
            raise ValueError('vertical handoff metadata requires a vertical exit direction')
        if self.vertical_handoff is not None:
            handoff = self.vertical_handoff
            if handoff.states:
                if len(handoff.states) != len(self.steps):
                    raise ValueError('vertical handoff state count must match release steps')
                for step, state in zip(self.steps, handoff.states):
                    if not math.isclose(step.time_s, state.time_s, rel_tol=0, abs_tol=1e-12):
                        raise ValueError('vertical handoff clock must match resolved release clock')
                    total = (state.density_kg_m3 * state.velocity_m_s *
                             (2. * state.half_width_m) * state.depth_m)
                    expected_h2 = total * state.h2_mass_fraction
                    if not math.isclose(step.mass_flow_kg_s, expected_h2, rel_tol=1e-8, abs_tol=1e-12):
                        raise ValueError('vertical handoff carrier section does not close provider mass flow')
        if self.position_enu_m[2]<=0:
            raise ValueError('resolved gas exit must be above flat ground')
        if not self.steps or self.steps[0].time_s!=0 or self.steps[-1].time_s>=self.duration_s:
            raise ValueError('left-held provider history starts at zero and stores interval starts before end')
        if len(self.steps)>100 or any(b.time_s<=a.time_s for a,b in zip(self.steps,self.steps[1:])):
            raise ValueError('ordered bounded provider clock required; retain command event times')
        mass,energy=self.integrated_mass_kg,self.integrated_static_enthalpy_j
        if not math.isclose(mass,self.cumulative_mass_out_kg,rel_tol=1e-8,abs_tol=1e-10):
            raise ValueError('provider cumulative mass and history do not close')
        if not math.isclose(energy,self.cumulative_static_enthalpy_out_j,rel_tol=1e-8,abs_tol=1e-6):
            raise ValueError('provider cumulative static enthalpy and history do not close')
        if mass>self.available_mass_kg+1e-9:
            raise ValueError('resolved release exceeds the available inventory')
        if self.event_kind!='accidental_leak' and self.failure_opening_diameter_m is not None:
            raise ValueError('normal vent/relief is not a declared random-leak opening')
        return self

    def intervals(self):
        return zip(self.steps,[x.time_s for x in self.steps[1:]]+[self.duration_s])

    @property
    def integrated_mass_kg(self):
        return sum(x.mass_flow_kg_s*(end-x.time_s) for x,end in self.intervals())

    @property
    def integrated_static_enthalpy_j(self):
        return sum(x.mass_flow_kg_s*x.specific_enthalpy_j_kg*(end-x.time_s) for x,end in self.intervals())


class ResolvedGasReleaseSet(Contract):
    """Two provider-resolved endpoints for a full-bore pipe rupture.

    A Purple full-bore pipe rupture is a two-ended event.  Keeping the two
    exits as separate ``ResolvedGasRelease`` objects preserves their own
    position, direction, PH state and time history; the set only owns the
    shared inventory ledger and event identity.  It is deliberately not a
    way to duplicate one endpoint or to add two independent frequencies.
    """

    event_id: Name
    component_id: Name
    rupture_mode: Literal['two_sided_rupture'] = 'two_sided_rupture'
    releases: tuple[ResolvedGasRelease, ResolvedGasRelease]
    available_mass_kg: Positive
    cumulative_mass_out_kg: Nonnegative
    inventory_provenance: Name

    @model_validator(mode='after')
    def ledger(self):
        if any(release.component_id != self.component_id for release in self.releases):
            raise ValueError('two-sided endpoints must belong to the same component')
        if any(release.event_kind != 'accidental_leak' for release in self.releases):
            raise ValueError('two-sided rupture endpoints must be accidental leaks')
        if any(release.event_id != self.event_id for release in self.releases):
            raise ValueError('two-sided endpoints must carry the shared rupture event id')
        if self.releases[0].port_id == self.releases[1].port_id:
            raise ValueError('two-sided rupture endpoints require distinct outward ports')
        if self.releases[0].property_basis != self.releases[1].property_basis:
            raise ValueError('two-sided endpoints require one property basis')
        if self.releases[0].upstream_service != self.releases[1].upstream_service:
            raise ValueError('two-sided endpoints require one upstream service')
        if any(not math.isclose(release.available_mass_kg, self.available_mass_kg,
                                rel_tol=1e-10, abs_tol=1e-12) for release in self.releases):
            raise ValueError('endpoint and shared available inventories disagree')
        if any(not math.isclose(release.duration_s, self.duration_s,
                                rel_tol=0, abs_tol=1e-12) for release in self.releases):
            raise ValueError('two-sided endpoints must share one release duration')
        total = sum(release.cumulative_mass_out_kg for release in self.releases)
        if not math.isclose(total, self.cumulative_mass_out_kg, rel_tol=1e-8, abs_tol=1e-10):
            raise ValueError('shared cumulative mass does not close across endpoints')
        if total > self.available_mass_kg + 1e-9:
            raise ValueError('two-sided release exceeds the shared available inventory')
        return self

    @property
    def duration_s(self):
        return self.releases[0].duration_s

    @property
    def positions_enu_m(self):
        return tuple(release.position_enu_m for release in self.releases)

    @property
    def integrated_mass_kg(self):
        return sum(release.integrated_mass_kg for release in self.releases)


class LiquidDropletOutcome(Contract):
    """Provider-owned fate of one liquid parcel class."""

    ground_liquid_mass_flow_kg_s: Nonnegative = 0.0
    airborne_liquid_mass_flow_kg_s: Nonnegative = 0.0
    flight_time_s: Nonnegative | None = None
    impact_position_m: Vector | None = None
    droplet_diameter_m: Positive | None = None

    @model_validator(mode='after')
    def resolved_ground_fate(self):
        if self.ground_liquid_mass_flow_kg_s > 1e-12:
            if self.flight_time_s is None or self.impact_position_m is None:
                raise ValueError('ground liquid outcome requires flight time and impact position')
        return self


class ResolvedLiquidStep(Contract):
    """Left-held provider state after liquid/two-phase flash partition."""

    time_s: Nonnegative
    total_mass_flow_kg_s: Nonnegative
    gas_mass_flow_kg_s: Nonnegative
    ground_liquid_mass_flow_kg_s: Nonnegative
    airborne_liquid_mass_flow_kg_s: Nonnegative
    specific_enthalpy_j_kg: float
    gas_pressure_pa_abs: Positive | None = None
    gas_temperature_k: Positive | None = None
    gas_density_kg_m3: Positive | None = None
    gas_effective_area_m2: Positive | None = None
    gas_velocity_m_s: Nonnegative | None = None
    gas_velocity_origin: Literal['provider_resolved', 'mass_continuity_from_declared_area'] | None = None
    droplet_class_outcomes: tuple[LiquidDropletOutcome, ...] = ()

    @model_validator(mode='after')
    def partition_and_gas_closure(self):
        expected = self.gas_mass_flow_kg_s + self.ground_liquid_mass_flow_kg_s + self.airborne_liquid_mass_flow_kg_s
        if not math.isclose(self.total_mass_flow_kg_s, expected, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError('liquid/two-phase provider mass partition does not close')
        ground = sum(x.ground_liquid_mass_flow_kg_s for x in self.droplet_class_outcomes)
        airborne = sum(x.airborne_liquid_mass_flow_kg_s for x in self.droplet_class_outcomes)
        if not math.isclose(ground, self.ground_liquid_mass_flow_kg_s, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError('liquid provider ground droplet classes do not close')
        if not math.isclose(airborne, self.airborne_liquid_mass_flow_kg_s, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError('liquid provider airborne droplet classes do not close')
        if self.gas_mass_flow_kg_s > 1e-12:
            fields = (self.gas_pressure_pa_abs, self.gas_temperature_k, self.gas_density_kg_m3,
                      self.gas_effective_area_m2, self.gas_velocity_m_s, self.gas_velocity_origin)
            if any(value is None for value in fields):
                raise ValueError('positive flashed gas flow requires a complete gas boundary state')
            expected_gas = self.gas_density_kg_m3 * self.gas_velocity_m_s * self.gas_effective_area_m2
            if not math.isclose(self.gas_mass_flow_kg_s, expected_gas, rel_tol=1e-8, abs_tol=1e-12):
                raise ValueError('flashed gas mass/area/density/velocity do not close')
        return self


class ResolvedLiquidRelease(Contract):
    """Provider-resolved atmospheric liquid/two-phase release.

    The equipment model owns pressure relief, flash and droplet partition.  A
    downstream PRISM route may consume flashed gas and ground liquid, but it
    refuses airborne liquid unless a separate validated droplet adapter exists.
    """

    # Keep the same flat export marker as the gas boundary so a provider can
    # use one request catalog for gas, liquid, and two-phase exits.
    provider_export_schema: Literal['prism.resolved_release.v1'] = 'prism.resolved_release.v1'
    component_id: Name
    port_id: Name
    event_id: Name
    event_kind: Literal['accidental_leak', 'normal_vent', 'emergency_relief']
    upstream_service: Literal['LH2', 'GH2', 'COLD_GH2']
    upstream_service_provenance: Name
    state_owner: Literal['equipment_twin'] = 'equipment_twin'
    discharge_owner: Literal['equipment_twin'] = 'equipment_twin'
    boundary_kind: Literal['resolved_atmospheric_liquid_exit'] = 'resolved_atmospheric_liquid_exit'
    phase_basis: Literal['liquid', 'two_phase']
    enthalpy_convention: Literal['provider_total_outlet_enthalpy']
    property_basis: PropertyBasis
    provider_source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider_result_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider_boundary_reference: Name
    input_origin: Literal['synthetic', 'model_prediction', 'reviewed_measurement']
    position_enu_m: Vector
    direction_enu: Vector
    ambient_pressure_pa_abs: Positive
    ambient_temperature_k: Positive
    duration_s: Positive
    available_mass_kg: Positive
    cumulative_mass_out_kg: Nonnegative
    cumulative_specific_enthalpy_out_j: float
    reference_area_m2: Positive
    reference_area_provenance: Name
    steps: tuple[ResolvedLiquidStep, ...]
    termination_provenance: Name
    droplet_partition_provenance: Name
    failure_opening_diameter_m: Positive | None = None

    @model_validator(mode='after')
    def ledger(self):
        if self.property_basis.energy_reference != f'CoolProp-HEOS:{self.property_basis.fluid}:native':
            raise ValueError('resolved liquid boundary requires the declared native enthalpy reference')
        if not math.isclose(sum(x*x for x in self.direction_enu), 1., abs_tol=1e-10, rel_tol=0):
            raise ValueError('unit ENU outlet direction required')
        if self.position_enu_m[2] <= 0:
            raise ValueError('resolved liquid exit must be above flat ground')
        if not self.steps or self.steps[0].time_s != 0 or self.steps[-1].time_s >= self.duration_s:
            raise ValueError('left-held liquid provider history starts at zero before its end')
        if len(self.steps) > 100 or any(b.time_s <= a.time_s for a, b in zip(self.steps, self.steps[1:])):
            raise ValueError('ordered bounded liquid provider clock required')
        if any(step.airborne_liquid_mass_flow_kg_s > 1e-12 for step in self.steps):
            raise ValueError('airborne liquid requires a validated droplet/flash adapter; it cannot be implicit gas')
        mass = self.integrated_mass_kg
        energy = self.integrated_specific_enthalpy_out_j
        if not math.isclose(mass, self.cumulative_mass_out_kg, rel_tol=1e-8, abs_tol=1e-10):
            raise ValueError('provider cumulative liquid mass and history do not close')
        if not math.isclose(energy, self.cumulative_specific_enthalpy_out_j, rel_tol=1e-8, abs_tol=1e-6):
            raise ValueError('provider liquid enthalpy ledger does not close')
        if mass > self.available_mass_kg + 1e-9:
            raise ValueError('resolved liquid release exceeds available inventory')
        if self.event_kind != 'accidental_leak' and self.failure_opening_diameter_m is not None:
            raise ValueError('normal vent/relief is not a declared random-leak opening')
        return self

    def intervals(self):
        return zip(self.steps, [x.time_s for x in self.steps[1:]] + [self.duration_s])

    @property
    def integrated_mass_kg(self):
        return sum(x.total_mass_flow_kg_s * (end - x.time_s) for x, end in self.intervals())

    @property
    def integrated_specific_enthalpy_out_j(self):
        return sum(x.total_mass_flow_kg_s * x.specific_enthalpy_j_kg * (end - x.time_s) for x, end in self.intervals())


def thermodynamic_rows(packet: dict, ambient_pressure: float, cp) -> tuple[list[dict],dict]:
    """Validate the contract, then resolve its PH state without solving flow."""
    from .resolved_gas_worker import resolve_gas_rows
    release=ResolvedGasRelease.model_validate_json(__import__('json').dumps(packet,allow_nan=False))
    return resolve_gas_rows(release.model_dump(mode='json'),ambient_pressure,cp)
