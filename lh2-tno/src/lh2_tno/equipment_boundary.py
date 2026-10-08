"""Resolved atmospheric gas exits supplied by an equipment-twin provider.

The provider owns the flow calculation. This contract never estimates a leak
from P/T or re-runs a tank/nozzle solver. Liquid and underexpanded outlets
need their own source/flash adapter and are deliberately rejected here.
"""
from __future__ import annotations
import math
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Contract, Name, Positive, Nonnegative, Vector, PropertyBasis


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


class ResolvedGasRelease(Contract):
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
    # A failure opening can differ from an expanded exit area. Explicitly
    # retain it if attaching an accident-frequency definition.
    failure_opening_diameter_m: Positive | None = None

    @model_validator(mode='after')
    def ledger(self):
        if self.property_basis.energy_reference!=f'CoolProp-HEOS:{self.property_basis.fluid}:native':
            raise ValueError('resolved boundary requires the declared native enthalpy reference')
        if not math.isclose(sum(x*x for x in self.direction_enu),1.,abs_tol=1e-10,rel_tol=0):
            raise ValueError('unit ENU outlet direction required')
        if self.direction_enu[2]!=0:
            raise ValueError('resolved gas path currently supports horizontal exits; vertical momentum adapter required')
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


def thermodynamic_rows(packet: dict, ambient_pressure: float, cp) -> tuple[list[dict],dict]:
    """Validate the contract, then resolve its PH state without solving flow."""
    from .resolved_gas_worker import resolve_gas_rows
    release=ResolvedGasRelease.model_validate_json(__import__('json').dumps(packet,allow_nan=False))
    return resolve_gas_rows(release.model_dump(mode='json'),ambient_pressure,cp)
