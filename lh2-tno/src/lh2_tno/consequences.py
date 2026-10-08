"""Validated inputs for the executable outdoor LH2 consequence chain."""
from __future__ import annotations
import math
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Contract, Name, Positive, Nonnegative, Fraction, Vector
from .frequency import FrequencyEvent
from .equipment_boundary import ResolvedGasRelease


class Weather(Contract):
    wind_speed_m_s: Positive
    wind_from_bearing_deg: float
    measurement_height_m: Positive = 10.0
    roughness_m: Positive = .03
    stability: Literal['A', 'B', 'C', 'D', 'E', 'F'] = 'D'
    relative_humidity: Fraction = .5

    @model_validator(mode='after')
    def valid(self):
        if self.measurement_height_m <= self.roughness_m:
            raise ValueError('wind measurement must be above surface roughness')
        return self


class PoolBoundary(Contract):
    # A resolved/declared footprint is a physical boundary, not a fitted rate.
    footprint_origin: Literal['reviewed_design', 'measured', 'declared_sensitivity']
    radius_m: Positive
    conductivity_w_mk: Positive
    diffusivity_m2_s: Positive
    initial_temperature_k: Positive
    domain_radius_m: Positive
    radial_step_m: Positive
    maximum_time_step_s: Positive = .01

    @model_validator(mode='after')
    def resolved(self):
        if not self.radial_step_m <= self.radius_m < self.domain_radius_m:
            raise ValueError('pool footprint must be resolved and inside its domain')
        if self.domain_radius_m / self.radial_step_m > 1000:
            raise ValueError('pool radial cell budget exceeded')
        return self


class IgnitionBranches(Contract):
    direct_probability: Fraction
    delayed_probability_given_no_direct: Fraction
    explosion_probability_given_delayed: Fraction
    delayed_time_s: Nonnegative
    burn_back_duration_s: Positive
    obstructed_energy_fraction: Fraction
    provenance: Name
    deflagration_only: Literal[True] = True

    def probabilities(self):
        direct = self.direct_probability
        delayed = (1-direct)*self.delayed_probability_given_no_direct
        return {'direct_fire': direct,
                'delayed_flash_fire': delayed*(1-self.explosion_probability_given_delayed),
                'delayed_explosion': delayed*self.explosion_probability_given_delayed,
                'no_ignition': (1-direct)*(1-self.delayed_probability_given_no_direct)}


class SpatialDomain(Contract):
    # Coordinates in the meteorological downwind/crosswind frame, z in ENU.
    downwind_bounds_m: tuple[float, float]
    crosswind_bounds_m: tuple[float, float]
    height_bounds_m: tuple[float, float]
    cell_size_m: Positive

    @model_validator(mode='after')
    def budget(self):
        bounds=(self.downwind_bounds_m,self.crosswind_bounds_m,self.height_bounds_m)
        if any(b<=a for a,b in bounds) or self.height_bounds_m[0]<0:
            raise ValueError('ordered domain bounds and nonnegative ground height required')
        cells=math.prod(math.ceil((b-a)/self.cell_size_m) for a,b in bounds)
        if cells>250000: raise ValueError('3-D cell budget exceeded')
        return self


class ReleaseTermination(Contract):
    basis: Literal['synthetic_diagnostic_horizon', 'reviewed_isolation_success', 'inventory_depletion', 'model_pressure_equalization']
    time_s: Positive
    provenance: Name


class ConsequenceRequest(Contract):
    component_id: Name
    source_input: dict | None = None
    resolved_release: ResolvedGasRelease | None = None
    available_mass_kg: Positive
    source_position_enu_m: Vector
    weather: Weather
    pool: PoolBoundary | None = None
    ignition: IgnitionBranches
    domain: SpatialDomain
    evaluation_times_s: tuple[Nonnegative, ...]
    # Explicit LH2 radiation sensitivity, not the legacy unexplained 22.7 factor.
    radiative_fraction_range: tuple[Fraction, Fraction]
    radiation_provenance: Name
    annual_frequency_per_year: Nonnegative | None = None
    annual_frequency_provenance: Name | None = None
    frequency_event: FrequencyEvent | None = None
    release_termination: ReleaseTermination | None = None
    # ``declared`` requires the source model to cover the requested horizon.
    # ``model_natural`` uses the model's actual pressure-equalisation stop and
    # never extrapolates the final flow interval.
    source_duration_mode: Literal['declared', 'model_natural'] = 'declared'
    occupancy_probability: Fraction = 1.0
    initiation_intensity_per_s: Nonnegative | None = None
    frequency_scope: Literal['single_initiating_event_current_weather'] = 'single_initiating_event_current_weather'
    dispersion_x_max_m: Positive = 150.0
    transition_dx_m: Positive = .05
    transition_x_max_m: Positive = 100.0
    n_puff_steps: int = Field(default=80, ge=20, le=500)

    @model_validator(mode='after')
    def valid(self):
        times=self.evaluation_times_s
        if len(times)<2 or times[0]!=0 or any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError('evaluation clock must start at zero and increase')
        if times[-1]>120 or len(times)>500:
            raise ValueError('consequence horizon budget exceeded')
        if (self.source_input is None)==(self.resolved_release is None):
            raise ValueError('choose exactly one source owner: integrated source or equipment-resolved gas exit')
        release=self.resolved_release
        source=self.source_input if release is None else resolved_source_context(release,self.weather)
        duration=source['duration_s']; dt=source['time_step_s']
        if not 0<dt<=duration<=times[-1] or duration/dt>100:
            raise ValueError('source horizon must lie inside consequence horizon; max 100 source intervals')
        if duration not in times or self.ignition.delayed_time_s not in times:
            raise ValueError('release end and delayed ignition must be explicit evaluation timestamps')
        if self.source_duration_mode == 'model_natural':
            if release is not None:
                raise ValueError('model_natural duration requires an integrated transient source')
            if self.release_termination is None or self.release_termination.basis != 'model_pressure_equalization':
                raise ValueError('model_natural duration requires pressure-equalization termination provenance')
            if self.release_termination.time_s != duration:
                raise ValueError('pressure-equalization termination must declare the requested source horizon')
        elif self.release_termination is not None and self.release_termination.basis == 'model_pressure_equalization':
            raise ValueError('pressure-equalization termination requires source_duration_mode=model_natural')
        if self.ignition.delayed_time_s+self.ignition.burn_back_duration_s>times[-1]:
            raise ValueError('horizon must cover the entire delayed burn-back')
        lo,hi=self.radiative_fraction_range
        if not 0<lo<=hi<1:raise ValueError('ordered positive radiative fraction range required')
        ambient=source['ambient']
        if ambient['wind_speed_m_s']!=self.weather.wind_speed_m_s or ambient['wind_from_bearing_deg']!=self.weather.wind_from_bearing_deg:
            raise ValueError('source and dispersion wind must agree')
        if abs(self.source_position_enu_m[2]-source['nozzle']['height_m'])>1e-9:
            raise ValueError('source ENU height must equal nozzle height above flat ground')
        if self.source_position_enu_m[2]<=0:
            raise ValueError('resolved jet source height above ground required')
        direction=source['nozzle']['direction_enu']
        if math.hypot(direction[0],direction[1])==0:
            raise ValueError('vertical-only release requires a vertical near-field adapter')
        if release is not None:
            if release.component_id!=self.component_id or release.position_enu_m!=self.source_position_enu_m:
                raise ValueError('provider component/exit position must match consequence request')
            if release.available_mass_kg!=self.available_mass_kg:
                raise ValueError('provider and consequence inventories disagree')
            if any(x.time_s not in times for x in release.steps):
                raise ValueError('all provider/command breakpoints must be explicit evaluation timestamps')
            if release.event_kind=='normal_vent' and any(x is not None for x in (self.annual_frequency_per_year,self.frequency_event,self.initiation_intensity_per_s)):
                raise ValueError('normal vent history must not be assigned a random accident initiation frequency')
        if self.annual_frequency_per_year is not None and self.annual_frequency_provenance is None:
            raise ValueError('annual frequency provenance required')
        event = self.frequency_event
        if event is not None:
            if self.release_termination is None or self.release_termination.time_s != duration:
                raise ValueError('bound event requires explicit release-duration/termination basis; frequency does not justify cutting a release short')
            if event.model_component_id != self.component_id or event.release.mode != 'hole' or event.exposure_multiplier != 1:
                raise ValueError('frequency event requires a matching single-item hole release')
            if release is None and event.profile not in ('TNO_PRESSURE_VESSEL', 'TNO_PROCESS_VESSEL', 'TNO_REACTOR_VESSEL', 'LH2_VESSEL'):
                raise ValueError('current source binding supports reviewed tank/vessel hole events only')
            if release is not None and (release.event_kind!='accidental_leak' or release.failure_opening_diameter_m is None):
                raise ValueError('resolved frequency binding requires an accidental leak with explicit failure opening')
            if release is not None and event.basis=='LH2_LITERATURE' and release.upstream_service!='LH2':
                raise ValueError('LH2 literature frequency must not be applied to a GH2/cold-GH2 component merely because it belongs to an LH2 facility')
            if self.annual_frequency_per_year != event.annual_frequency_per_year:
                raise ValueError('request/event frequency mismatch')
            if self.initiation_intensity_per_s is not None and not math.isclose(
                    self.initiation_intensity_per_s, event.annual_frequency_per_year/(365.25*86400), rel_tol=1e-10, abs_tol=0):
                raise ValueError('bound event cannot carry a conflicting initiation intensity; explicit stationary calendar-year conversion required')
            opening=source['nozzle']['diameter_m'] if release is None else release.failure_opening_diameter_m
            if not math.isclose(opening, event.release.hole_diameter_m, rel_tol=1e-10, abs_tol=1e-12):
                raise ValueError('request/event leak diameter mismatch')
        if self.transition_x_max_m/self.transition_dx_m>10000:
            raise ValueError('near-field integration budget exceeded')
        return self


def resolved_source_context(release,weather):
    first=release.steps[0]
    return {'tank':{'fluid':release.property_basis.fluid},
        'nozzle':{'height_m':release.position_enu_m[2],'direction_enu':list(release.direction_enu),
                  'diameter_m':math.sqrt(4*first.effective_area_m2/math.pi)},
        'ambient':{'pressure_pa':release.ambient_pressure_pa_abs,'temperature_k':release.ambient_temperature_k,
                   'wind_speed_m_s':weather.wind_speed_m_s,'wind_from_bearing_deg':weather.wind_from_bearing_deg},
        'duration_s':release.duration_s,'time_step_s':release.duration_s}


def evaluate_consequences(pipeline, request: ConsequenceRequest) -> dict:
    """Run one source-to-receptor chain, preserving facility and code identities."""
    components={x.id:x for x in pipeline.facility.components}
    if request.component_id not in components:raise ValueError('source component not in facility')
    component=components[request.component_id]
    if pipeline.facility.environment!='outdoor':raise ValueError('outdoor consequence chain required')
    if request.resolved_release is None:
        if component.kind!='storage_tank':raise ValueError('integrated source requires a storage tank boundary')
        tank=request.source_input['tank']
        if component.property_basis.fluid!=tank['fluid'] or component.property_basis.energy_reference!=f"CoolProp-HEOS:{tank['fluid']}:native":
            raise ValueError('source/facility property basis mismatch')
        if component.parameters_si['volume_m3']!=tank['volume_m3']:raise ValueError('source/facility tank volume mismatch')
    else:
        release=request.resolved_release
        if component.property_basis!=release.property_basis:
            raise ValueError('provider/facility fluid or energy-reference mismatch')
        port=next((x for x in pipeline.facility.ports if x.id==release.port_id),None)
        if port is None or port.component_id!=component.id or port.direction=='in' or port.phase not in ('vapour','any'):
            raise ValueError('resolved exit requires a matching outward gas facility port')
    if not pipeline.facility.receptors:raise ValueError('at least one receptor required')
    payload=request.model_dump(mode='json')
    if request.resolved_release is not None:
        payload['source_input']=resolved_source_context(request.resolved_release,request.weather)
    payload['receptors']=[x.model_dump(mode='json') for x in pipeline.facility.receptors]
    result=pipeline.backend.run('consequence_chain',payload)
    result['facility_digest']=pipeline.facility.digest()
    if request.frequency_event is not None:
        result['frequency_event'] = request.frequency_event.model_dump(mode='json')
        result['frequency_scope'] = 'single initiating event; other LOC consequences may be uncomputed; not total annual facility IR'
        result['release_termination'] = request.release_termination.model_dump(mode='json')
        result['release_termination_verification'] = 'declared boundary only; isolation/depletion not independently validated by this binding'
    return result
