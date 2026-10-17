"""Validated inputs for the executable outdoor LH2 consequence chain."""
from __future__ import annotations
import json
import math
import time
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Contract, Name, Positive, Nonnegative, Fraction, Vector
from .frequency import FrequencyEvent
from .equipment_boundary import ResolvedGasRelease, ResolvedGasReleaseSet, ResolvedLiquidRelease
from .state_snapshot import EquipmentStateSnapshot
from .two_sided_interaction import combine_endpoint_harm


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
    footprint_origin: Literal['provider_resolved', 'reviewed_design', 'measured', 'declared_sensitivity']
    footprint_provenance: Name | None = None
    footprint_evidence_digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    # DynamicLH2PoolX currently implements the Hydrogen CoolProp basis.  Keep
    # that backend choice explicit so a ParaHydrogen provider packet cannot be
    # silently passed to a different property basis.
    fluid: Literal['Hydrogen', 'ParaHydrogen'] = 'Hydrogen'
    fluid_translation: Literal['none', 'para_hydrogen_to_hydrogen'] = 'none'
    translation_provenance: Name | None = None
    radius_m: Positive
    conductivity_w_mk: Positive
    diffusivity_m2_s: Positive
    initial_temperature_k: Positive
    domain_radius_m: Positive
    radial_step_m: Positive
    maximum_time_step_s: Positive = .01

    @model_validator(mode='after')
    def resolved(self):
        if self.fluid_translation == 'para_hydrogen_to_hydrogen':
            if self.fluid != 'Hydrogen' or not self.translation_provenance:
                raise ValueError('ParaHydrogen-to-Hydrogen pool translation requires Hydrogen and provenance')
        elif self.translation_provenance is not None:
            raise ValueError('pool translation provenance requires an explicit translation')
        if self.footprint_origin in {'provider_resolved', 'reviewed_design', 'measured'}:
            if not self.footprint_provenance:
                raise ValueError('resolved pool footprint requires provenance')
        elif self.footprint_provenance is not None or self.footprint_evidence_digest is not None:
            raise ValueError('declared sensitivity footprint cannot carry reviewed evidence metadata')
        if self.footprint_origin == 'provider_resolved' and self.footprint_evidence_digest is None:
            raise ValueError('provider-resolved pool footprint requires an evidence digest')
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
    basis: Literal['synthetic_diagnostic_horizon', 'reviewed_isolation_success', 'inventory_depletion', 'inventory_over_600s', 'model_pressure_equalization', 'two_sided_rupture', 'emergency_relief_discharge']
    time_s: Positive
    provenance: Name


class ConsequenceRequest(Contract):
    component_id: Name
    # HAZOP-selected operating mode is identity metadata carried with the
    # consequence request. It does not provide a frequency or alter release
    # physics, but prevents the downstream chain from losing the mode that
    # selected the accident family.
    operating_mode: Name | None = None
    # Exact HAZOP row/scenario identity selected from the supplied operating
    # mode and state frame.  It is metadata only and never assigns frequency
    # or changes the provider release physics.
    hazop_scenario_id: Name | None = None
    # Equipment state is an input-side handoff from the digital twin. It is
    # deliberately separate from the resolved accident packet: a release
    # history must never be promoted to a normal operating state.
    state_snapshot: EquipmentStateSnapshot | None = None
    state_snapshot_digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    provider_state_snapshot_digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    # A two-sided rupture may be answered by more than one provider endpoint.
    # Keep the historical single echo for compatibility, while retaining the
    # complete per-endpoint echo list when it is available.
    provider_state_snapshot_digests: tuple[str, ...] | None = None
    source_input: dict | None = None
    resolved_release: ResolvedGasRelease | None = None
    resolved_release_set: ResolvedGasReleaseSet | None = None
    resolved_liquid_release: ResolvedLiquidRelease | None = None
    available_mass_kg: Positive
    source_position_enu_m: Vector
    source_positions_enu_m: tuple[Vector, ...] | None = None
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
    source_operator: Literal['integrated_transient', 'inventory_liquid_jet', 'equipment_inventory_depletion', 'equipment_liquid_release', 'inventory_over_600s', 'equipment_inventory_over_600s', 'equipment_liquid_over_600s', 'equipment_pressure_equalization', 'equipment_two_sided_rupture', 'equipment_two_sided_rupture_endpoint', 'equipment_emergency_relief'] = 'integrated_transient'
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
        if self.state_snapshot is None:
            if (
                self.state_snapshot_digest is not None
                or self.provider_state_snapshot_digest is not None
                or self.provider_state_snapshot_digests is not None
            ):
                raise ValueError('state snapshot digests require a canonical state_snapshot payload')
        else:
            if self.state_snapshot.component_id != self.component_id:
                raise ValueError('state_snapshot component_id must match consequence component_id')
            computed_state_digest = self.state_snapshot.digest()
            if self.state_snapshot_digest != computed_state_digest:
                raise ValueError('state_snapshot_digest does not match canonical state_snapshot')
            if self.provider_state_snapshot_digest != computed_state_digest:
                raise ValueError('provider_state_snapshot_digest must equal canonical state_snapshot digest')
            if self.provider_state_snapshot_digests is not None:
                if not self.provider_state_snapshot_digests:
                    raise ValueError('provider_state_snapshot_digests must not be empty')
                if any(value != computed_state_digest for value in self.provider_state_snapshot_digests):
                    raise ValueError('provider_state_snapshot_digests must equal canonical state_snapshot digest')
        times=self.evaluation_times_s
        if len(times)<2 or times[0]!=0 or any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError('evaluation clock must start at zero and increase')
        if times[-1]>600 or len(times)>500:
            raise ValueError('consequence horizon budget exceeded')
        owners=sum(x is not None for x in (self.source_input,self.resolved_release,self.resolved_release_set,self.resolved_liquid_release))
        if owners != 1:
            raise ValueError('choose exactly one source owner: integrated source, equipment gas exit, liquid/two-phase exit, or two-sided equipment gas exits')
        release=self.resolved_release
        release_set=self.resolved_release_set
        liquid_release=self.resolved_liquid_release
        if release_set is not None:
            source=resolved_source_context(release_set.releases[0],self.weather)
        elif liquid_release is not None:
            source=resolved_liquid_source_context(liquid_release,self.weather)
        else:
            source=self.source_input if release is None else resolved_source_context(release,self.weather)
        duration=source['duration_s']; dt=source['time_step_s']
        if not 0<dt<=duration<=times[-1] or duration/dt>100:
            raise ValueError('source horizon must lie inside consequence horizon; max 100 source intervals')
        if duration not in times or self.ignition.delayed_time_s not in times:
            raise ValueError('release end and delayed ignition must be explicit evaluation timestamps')
        if self.source_operator == 'inventory_liquid_jet':
            if release is not None:
                raise ValueError('inventory_liquid_jet requires an integrated source_input')
            if self.source_duration_mode != 'declared':
                raise ValueError('inventory_liquid_jet uses its declared depletion horizon')
            if self.release_termination is None or self.release_termination.basis != 'inventory_depletion':
                raise ValueError('inventory_liquid_jet requires inventory-depletion termination provenance')
            if source['tank'].get('vapour_quality') != 0:
                raise ValueError('inventory_liquid_jet requires a declared liquid inlet state')
            if source.get('pipe_sections'):
                raise ValueError('inventory_liquid_jet does not silently include unresolved pipe sections')
            spray = source.get('liquid_jet')
            if not isinstance(spray, dict):
                raise ValueError('inventory_liquid_jet requires explicit liquid_jet assumptions')
            required = ('discharge_coefficient', 'droplet_diameter_m', 'd2_evaporation_constant_m2_s',
                        'spray_half_angle_deg', 'liquid_velocity_fraction')
            if any(k not in spray for k in required):
                raise ValueError('liquid_jet assumptions must declare discharge, droplet, evaporation, spray and velocity inputs')
        elif self.source_operator == 'equipment_inventory_depletion':
            if release is None:
                raise ValueError('equipment_inventory_depletion requires a resolved equipment release')
            if release.event_kind != 'accidental_leak':
                raise ValueError('equipment_inventory_depletion requires an accidental-leak resolved release')
            if self.source_duration_mode != 'declared':
                raise ValueError('equipment_inventory_depletion uses its declared provider horizon')
            if self.release_termination is None or self.release_termination.basis != 'inventory_depletion':
                raise ValueError('equipment_inventory_depletion requires inventory-depletion termination provenance')
        elif self.source_operator == 'equipment_inventory_over_600s':
            if release is None:
                raise ValueError('equipment_inventory_over_600s requires a resolved equipment release')
            if release.event_kind != 'accidental_leak':
                raise ValueError('equipment_inventory_over_600s requires an accidental-leak resolved release')
            if self.source_duration_mode != 'declared':
                raise ValueError('equipment_inventory_over_600s uses its declared provider horizon')
            if self.release_termination is None or self.release_termination.basis != 'inventory_over_600s':
                raise ValueError('equipment_inventory_over_600s requires inventory-over-600s termination provenance')
            if not math.isclose(duration, 600.0, rel_tol=0, abs_tol=1e-9):
                raise ValueError('equipment_inventory_over_600s requires exactly 600 s of provider history')
        elif self.source_operator == 'equipment_pressure_equalization':
            if release is None:
                raise ValueError('equipment_pressure_equalization requires a resolved gas release')
            if release.event_kind != 'accidental_leak':
                raise ValueError('equipment_pressure_equalization requires an accidental-leak resolved release')
            if self.source_duration_mode != 'model_natural':
                raise ValueError('equipment_pressure_equalization requires model_natural duration')
            if self.release_termination is None or self.release_termination.basis != 'model_pressure_equalization':
                raise ValueError('equipment_pressure_equalization requires pressure-equalization termination provenance')
            if self.available_mass_kg != release.available_mass_kg:
                raise ValueError('pressure-equalization request and provider inventories disagree')
        elif self.source_operator == 'equipment_liquid_release':
            if liquid_release is None:
                raise ValueError('equipment_liquid_release requires a provider-resolved liquid/two-phase release')
            if liquid_release.event_kind != 'accidental_leak':
                raise ValueError('equipment_liquid_release requires an accidental-leak resolved release')
            if release is not None or release_set is not None or self.source_input is not None:
                raise ValueError('equipment_liquid_release requires one resolved liquid release')
            if self.source_duration_mode not in {'declared', 'model_natural'}:
                raise ValueError('equipment_liquid_release uses a provider-declared or provider-natural horizon')
            if self.release_termination is None or self.release_termination.basis not in {
                'inventory_depletion', 'reviewed_isolation_success', 'synthetic_diagnostic_horizon',
                'model_pressure_equalization',
            }:
                raise ValueError(
                    'equipment_liquid_release requires provider inventory, reviewed isolation, '
                    'pressure-equalization, or explicit diagnostic-horizon termination provenance'
                )
            if self.source_duration_mode == 'model_natural' and self.release_termination.basis != 'model_pressure_equalization':
                raise ValueError('provider-natural liquid duration requires pressure-equalization termination provenance')
            if self.available_mass_kg != liquid_release.available_mass_kg:
                raise ValueError('liquid request and provider inventories disagree')
        elif self.source_operator == 'equipment_liquid_over_600s':
            if liquid_release is None:
                raise ValueError('equipment_liquid_over_600s requires a resolved liquid/two-phase release')
            if liquid_release.event_kind != 'accidental_leak':
                raise ValueError('equipment_liquid_over_600s requires an accidental-leak resolved release')
            if self.source_duration_mode != 'declared':
                raise ValueError('equipment_liquid_over_600s uses its declared provider horizon')
            if self.release_termination is None or self.release_termination.basis != 'inventory_over_600s':
                raise ValueError('equipment_liquid_over_600s requires inventory-over-600s termination provenance')
            if not math.isclose(duration, 600.0, rel_tol=0, abs_tol=1e-9):
                raise ValueError('equipment_liquid_over_600s requires exactly 600 s of provider history')
            if self.available_mass_kg != liquid_release.available_mass_kg:
                raise ValueError('liquid request and provider inventories disagree')
        elif self.source_operator == 'equipment_emergency_relief':
            if release is None or release_set is not None or liquid_release is not None or self.source_input is not None:
                raise ValueError('equipment_emergency_relief requires one resolved gas release')
            if release.event_kind != 'emergency_relief' or release.failure_opening_diameter_m is not None:
                raise ValueError('equipment_emergency_relief requires a provider emergency-relief boundary without a random leak opening')
            if self.source_duration_mode != 'declared':
                raise ValueError('equipment_emergency_relief uses the provider-declared discharge horizon')
            if self.release_termination is None or self.release_termination.basis != 'emergency_relief_discharge':
                raise ValueError('equipment_emergency_relief requires emergency-relief termination provenance')
        elif self.source_operator == 'equipment_two_sided_rupture':
            if release_set is None:
                raise ValueError('equipment_two_sided_rupture requires two provider-resolved endpoints')
            if release is not None or self.source_input is not None:
                raise ValueError('equipment_two_sided_rupture requires a resolved release set')
            if self.source_duration_mode != 'declared':
                raise ValueError('equipment_two_sided_rupture uses the provider-declared horizon')
            if self.release_termination is None or self.release_termination.basis != 'two_sided_rupture':
                raise ValueError('equipment_two_sided_rupture requires two-sided rupture termination provenance')
            if self.available_mass_kg != release_set.available_mass_kg:
                raise ValueError('two-sided request and provider inventories disagree')
            positions=self.source_positions_enu_m
            if positions is None or tuple(positions) != release_set.positions_enu_m:
                raise ValueError('two-sided request must declare both provider endpoint positions')
        elif self.source_operator == 'equipment_two_sided_rupture_endpoint':
            if release is None or release_set is not None:
                raise ValueError('two-sided endpoint operator requires one resolved endpoint')
            if self.source_duration_mode != 'declared':
                raise ValueError('two-sided endpoint uses the provider-declared horizon')
            if self.release_termination is None or self.release_termination.basis != 'two_sided_rupture':
                raise ValueError('two-sided endpoint requires two-sided rupture termination provenance')
        elif self.source_operator == 'inventory_over_600s':
            if release is not None:
                raise ValueError('inventory_over_600s requires an integrated finite-inventory source')
            if self.source_duration_mode != 'declared':
                raise ValueError('inventory_over_600s requires a complete declared horizon')
            if self.release_termination is None or self.release_termination.basis != 'inventory_over_600s':
                raise ValueError('inventory_over_600s requires an inventory-over-600s termination provenance')
            if not math.isclose(duration, 600.0, rel_tol=0, abs_tol=1e-9):
                raise ValueError('inventory_over_600s requires exactly 600 s of source history')
        elif self.release_termination is not None and self.release_termination.basis == 'inventory_depletion':
            raise ValueError('inventory-depletion termination requires an explicit inventory source operator')
        elif self.release_termination is not None and self.release_termination.basis == 'inventory_over_600s':
            raise ValueError('inventory-over-600s termination requires the inventory_over_600s source operator')
        elif self.release_termination is not None and self.release_termination.basis == 'two_sided_rupture' and self.source_operator != 'equipment_two_sided_rupture_endpoint':
            raise ValueError('two-sided rupture termination requires the two-sided equipment operator')
        if self.source_duration_mode == 'model_natural':
            if liquid_release is None and release is not None and self.source_operator != 'equipment_pressure_equalization':
                raise ValueError('model_natural duration requires an integrated transient source or provider liquid release')
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
        source_fluid = source['tank']['fluid']
        if self.pool is not None and source_fluid != self.pool.fluid:
            if not (source_fluid == 'ParaHydrogen' and self.pool.fluid == 'Hydrogen'
                    and self.pool.fluid_translation == 'para_hydrogen_to_hydrogen'):
                raise ValueError('source and pool property bases differ without an explicit pool translation')
        if ambient['wind_speed_m_s']!=self.weather.wind_speed_m_s or ambient['wind_from_bearing_deg']!=self.weather.wind_from_bearing_deg:
            raise ValueError('source and dispersion wind must agree')
        if release_set is None and abs(self.source_position_enu_m[2]-source['nozzle']['height_m'])>1e-9:
            raise ValueError('source ENU height must equal nozzle height above flat ground')
        if release_set is None and self.source_position_enu_m[2]<=0:
            raise ValueError('resolved jet source height above ground required')
        if release_set is not None:
            if any(position[2] <= 0 for position in release_set.positions_enu_m):
                raise ValueError('all two-sided resolved jet endpoints must be above flat ground')
            if self.source_position_enu_m != release_set.positions_enu_m[0]:
                raise ValueError('source_position_enu_m must anchor the first two-sided provider endpoint')
            if any(release.ambient_pressure_pa_abs != release_set.releases[0].ambient_pressure_pa_abs or
                   release.ambient_temperature_k != release_set.releases[0].ambient_temperature_k
                   for release in release_set.releases[1:]):
                raise ValueError('two-sided endpoints require one ambient boundary')
        direction=source['nozzle']['direction_enu']
        if release_set is None and liquid_release is None and math.hypot(direction[0],direction[1])==0:
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
        if liquid_release is not None:
            if liquid_release.component_id != self.component_id or liquid_release.position_enu_m != self.source_position_enu_m:
                raise ValueError('provider liquid component/exit position must match consequence request')
            if liquid_release.available_mass_kg != self.available_mass_kg:
                raise ValueError('provider liquid and consequence inventories disagree')
            if any(x.time_s not in times for x in liquid_release.steps):
                raise ValueError('all provider liquid breakpoints must be explicit evaluation timestamps')
            if liquid_release.event_kind == 'normal_vent' and any(x is not None for x in (self.annual_frequency_per_year,self.frequency_event,self.initiation_intensity_per_s)):
                raise ValueError('normal liquid vent history must not be assigned a random accident initiation frequency')
        if release_set is not None:
            if any(release.component_id != self.component_id or release.position_enu_m != position
                   for release,position in zip(release_set.releases,self.source_positions_enu_m or ())):
                raise ValueError('provider endpoints must match the declared two-sided component and positions')
            if any(any(step.time_s not in times for step in release.steps) for release in release_set.releases):
                raise ValueError('all two-sided provider breakpoints must be explicit evaluation timestamps')
        if self.annual_frequency_per_year is not None and self.annual_frequency_provenance is None:
            raise ValueError('annual frequency provenance required')
        event = self.frequency_event
        if event is not None:
            if self.release_termination is None or self.release_termination.time_s != duration:
                raise ValueError('bound event requires explicit release-duration/termination basis; frequency does not justify cutting a release short')
            if (
                event.model_component_id != self.component_id
                or (event.exposure_multiplier != 1 and event.location_weight is None)
            ):
                raise ValueError('frequency event requires a matching single-item release')
            if event.port_ids is not None:
                if release_set is not None:
                    request_port_ids = tuple(release.port_id for release in release_set.releases)
                elif release is not None:
                    request_port_ids = (release.port_id,)
                elif liquid_release is not None:
                    request_port_ids = (liquid_release.port_id,)
                else:
                    request_port_ids = ()
                if request_port_ids != event.port_ids:
                    raise ValueError(
                        'frequency event port_ids must exactly match the provider-resolved accident exit(s)'
                    )
            if event.release.mode == 'instantaneous_inventory':
                if self.source_operator not in {'inventory_liquid_jet', 'equipment_inventory_depletion', 'equipment_liquid_release'} or self.release_termination.basis != 'inventory_depletion':
                    raise ValueError('instantaneous inventory event requires an inventory-depletion operator')
            elif event.release.mode == 'inventory_over_600s':
                if self.source_operator not in {'inventory_over_600s', 'equipment_inventory_over_600s', 'equipment_liquid_over_600s', 'equipment_pressure_equalization'} or self.release_termination.basis not in {'inventory_over_600s', 'model_pressure_equalization'}:
                    raise ValueError('600 s inventory event requires an inventory-over-600s operator')
            elif event.release.mode == 'two_sided_rupture':
                if self.source_operator != 'equipment_two_sided_rupture' or release_set is None or self.release_termination.basis != 'two_sided_rupture':
                    raise ValueError('two-sided rupture event requires the equipment_two_sided_rupture operator')
            elif event.release.mode == 'maximum_relief_discharge':
                if (self.source_operator != 'equipment_emergency_relief' or release is None
                        or release.event_kind != 'emergency_relief'
                        or release.failure_opening_diameter_m is not None
                        or self.release_termination.basis != 'emergency_relief_discharge'):
                    raise ValueError('maximum relief discharge requires the equipment_emergency_relief operator and provider termination')
            elif event.release.mode != 'hole':
                raise ValueError('frequency event requires a supported release operator')
            if release is None and release_set is None and liquid_release is None and event.profile not in ('TNO_PRESSURE_VESSEL', 'TNO_PROCESS_VESSEL', 'TNO_REACTOR_VESSEL', 'LH2_VESSEL'):
                raise ValueError('current source binding supports reviewed tank/vessel hole events only')
            provider_release = release if release is not None else liquid_release
            if event.release.mode == 'maximum_relief_discharge':
                if (not isinstance(provider_release, ResolvedGasRelease)
                        or provider_release.event_kind != 'emergency_relief'
                        or provider_release.failure_opening_diameter_m is not None):
                    raise ValueError('resolved relief binding requires an emergency-relief gas exit without a failure opening')
            elif provider_release is not None:
                inventory_mode = event.release.mode in {'instantaneous_inventory', 'inventory_over_600s'}
                if provider_release.event_kind != 'accidental_leak':
                    raise ValueError('resolved frequency binding requires an accidental-leak provider boundary')
                if inventory_mode:
                    # New inventory adapters leave this field null.  Legacy
                    # diagnostic packets may still carry the provider's
                    # calculation-area metadata; inventory frequency binding
                    # deliberately ignores it and never compares it with the
                    # literature LOC diameter.
                    pass
                elif provider_release.failure_opening_diameter_m is None:
                    raise ValueError('resolved hole frequency binding requires an explicit failure opening')
            if provider_release is not None and event.basis=='LH2_LITERATURE' and provider_release.upstream_service!='LH2':
                raise ValueError('LH2 literature frequency must not be applied to a GH2/cold-GH2 component merely because it belongs to an LH2 facility')
            if release_set is not None:
                if event.release.mode != 'two_sided_rupture' or any(endpoint.upstream_service != 'LH2' and event.basis == 'LH2_LITERATURE' for endpoint in release_set.releases):
                    raise ValueError('two-sided frequency and endpoint service must agree')
                if any(endpoint.failure_opening_diameter_m is None or
                       not math.isclose(endpoint.failure_opening_diameter_m,event.release.hole_diameter_m,rel_tol=1e-10,abs_tol=1e-12)
                       for endpoint in release_set.releases):
                    raise ValueError('two-sided frequency diameter must equal both physical endpoint openings')
            if self.annual_frequency_per_year != event.annual_frequency_per_year:
                raise ValueError('request/event frequency mismatch')
            if self.initiation_intensity_per_s is not None and not math.isclose(
                    self.initiation_intensity_per_s, event.annual_frequency_per_year/(365.25*86400), rel_tol=1e-10, abs_tol=0):
                raise ValueError('bound event cannot carry a conflicting initiation intensity; explicit stationary calendar-year conversion required')
            if event.release.mode == 'hole':
                opening=source['nozzle']['diameter_m'] if provider_release is None else provider_release.failure_opening_diameter_m
                if not math.isclose(opening, event.release.hole_diameter_m, rel_tol=1e-10, abs_tol=1e-12):
                    raise ValueError('request/event leak diameter mismatch')
        if self.transition_x_max_m/self.transition_dx_m>10000:
            raise ValueError('near-field integration budget exceeded')
        return self


def resolved_source_context(release,weather):
    first=release.steps[0]
    direction = release.vertical_handoff.direction_enu if release.vertical_handoff is not None else release.direction_enu
    return {'tank':{'fluid':release.property_basis.fluid},
        'nozzle':{'height_m':release.position_enu_m[2],'direction_enu':list(direction),
                  'diameter_m':math.sqrt(4*first.effective_area_m2/math.pi)},
        'ambient':{'pressure_pa':release.ambient_pressure_pa_abs,'temperature_k':release.ambient_temperature_k,
                   'wind_speed_m_s':weather.wind_speed_m_s,'wind_from_bearing_deg':weather.wind_from_bearing_deg},
        'duration_s':release.duration_s,'time_step_s':release.duration_s,
        'vertical_handoff':None if release.vertical_handoff is None else release.vertical_handoff.model_dump(mode='json'),
        'compressible_plane_handoff':None if release.compressible_plane_handoff is None else release.compressible_plane_handoff.model_dump(mode='json')}


def resolved_liquid_source_context(release, weather):
    next_time = release.steps[1].time_s if len(release.steps) > 1 else release.duration_s
    return {
        'tank': {'fluid': release.property_basis.fluid},
        'nozzle': {'height_m': release.position_enu_m[2], 'direction_enu': list(release.direction_enu),
                   'diameter_m': math.sqrt(4 * release.reference_area_m2 / math.pi)},
        'ambient': {'pressure_pa': release.ambient_pressure_pa_abs, 'temperature_k': release.ambient_temperature_k,
                    'wind_speed_m_s': weather.wind_speed_m_s, 'wind_from_bearing_deg': weather.wind_from_bearing_deg},
        'duration_s': release.duration_s,
        'time_step_s': next_time,
        'resolved_liquid_release': release.model_dump(mode='json'),
    }


def evaluate_consequences(pipeline, request: ConsequenceRequest) -> dict:
    """Run one source-to-receptor chain, preserving facility and code identities."""
    components={x.id:x for x in pipeline.facility.components}
    if request.component_id not in components:raise ValueError('source component not in facility')
    component=components[request.component_id]
    if pipeline.facility.environment!='outdoor':raise ValueError('outdoor consequence chain required')
    if request.resolved_release is None and request.resolved_release_set is None and request.resolved_liquid_release is None:
        if component.kind!='storage_tank':raise ValueError('integrated source requires a storage tank boundary')
        tank=request.source_input['tank']
        if component.property_basis.fluid!=tank['fluid'] or component.property_basis.energy_reference!=f"CoolProp-HEOS:{tank['fluid']}:native":
            raise ValueError('source/facility property basis mismatch')
        if component.parameters_si['volume_m3']!=tank['volume_m3']:raise ValueError('source/facility tank volume mismatch')
    else:
        releases = ((request.resolved_release,) if request.resolved_release is not None else
                    request.resolved_release_set.releases if request.resolved_release_set is not None else
                    (request.resolved_liquid_release,))
        for release in releases:
            if component.property_basis!=release.property_basis:
                raise ValueError('provider/facility fluid or energy-reference mismatch')
            port=next((x for x in pipeline.facility.ports if x.id==release.port_id),None)
            is_liquid = isinstance(release, ResolvedLiquidRelease)
            allowed_phases = ('liquid', 'two_phase', 'any') if is_liquid else ('vapour', 'any')
            if port is None or port.component_id!=component.id or port.direction=='in' or port.phase not in allowed_phases:
                raise ValueError('resolved exit requires a matching outward facility port with the declared phase')
            if port.position_enu_m is not None and release.position_enu_m != port.position_enu_m:
                raise ValueError('provider release position does not match the declared facility port position')
    if not pipeline.facility.receptors:raise ValueError('at least one receptor required')
    if request.resolved_release_set is not None:
        started=time.perf_counter()
        endpoint_results=[]
        for release in request.resolved_release_set.releases:
            payload=request.model_dump(mode='json')
            payload.update(
                source_input=None,
                resolved_release=release.model_dump(mode='json'),
                resolved_release_set=None,
                source_operator='equipment_two_sided_rupture_endpoint',
                source_position_enu_m=list(release.position_enu_m),
                source_positions_enu_m=None,
                frequency_event=None,
                annual_frequency_per_year=None,
                annual_frequency_provenance=None,
                initiation_intensity_per_s=None,
            )
            child=ConsequenceRequest.model_validate_json(json.dumps(payload,allow_nan=False))
            endpoint_results.append(pipeline.consequences(child))
        child_data=[result['data'] for result in endpoint_results]
        branch_keys=('direct_fire','delayed_flash_fire','delayed_explosion','no_ignition')
        probabilities=child_data[0]['ignition_branch_probabilities']
        if any(data['ignition_branch_probabilities'] != probabilities for data in child_data[1:]):
            raise ValueError('two-sided endpoints must use one ignition branch partition')
        endpoint_receptors=[{row['id']:row['branch_harm_low_high'] for row in data['receptors']} for data in child_data]
        receptor_ids=[row.id for row in pipeline.facility.receptors]
        interaction = combine_endpoint_harm(endpoint_receptors, receptor_ids)
        receptors=[]
        for receptor_id in receptor_ids:
            branch_harm=interaction['receptors'][receptor_id]['branch_harm_low_high']
            receptors.append({'id':receptor_id,
                'branch_harm_low_high':branch_harm,
                'harm_given_observed_release_low_high':[sum(probabilities[key]*branch_harm[i][key] for key in branch_keys) for i in range(2)]})
        ledgers=[data.get('mass_ledger',{}) for data in child_data]
        ledger_keys=sorted(set().union(*(ledger.keys() for ledger in ledgers)))
        ledger={key:sum(float(item.get(key,0.)) for item in ledgers) for key in ledger_keys}
        ledger['end_to_end_residual_kg']=sum(float(item.get('end_to_end_residual_kg',0.)) for item in ledgers)
        data={
            'status':'END_TO_END_DIAGNOSTIC_EXECUTED',
            'full_chain_executed':all(item.get('full_chain_executed') is True for item in child_data),
            'physical_validation_claim':False,
            'facility_validation':'WITHHELD',
            'realtime_requirement_demonstrated':False,
            'stages':['two_sided_endpoint_a','two_sided_endpoint_b','frechet_union_with_intersection_interval'],
            'source_operator':'equipment_two_sided_rupture',
            'operator_limited':True,
            'source_ownership':{'state_owner':'equipment_twin','discharge_owner':'equipment_twin',
                                'discharge_recalculated':False,'shared_inventory_owner':'equipment_twin'},
            'release_endpoints':[item['source'] for item in child_data],
            'endpoint_results':endpoint_results,
            'ignition_branch_probabilities':probabilities,
            'receptors':receptors,
            'two_sided_interaction_diagnostic':interaction,
            'frequency_application':{
                'event_id':request.frequency_event.id if request.frequency_event is not None else None,
                'annual_frequency_per_year':request.annual_frequency_per_year,
                'endpoint_count':2,
                'endpoint_frequency_multiplier':1.0,
                'application':'one shared two-sided initiating event; endpoint frequency is not split or duplicated',
            },
            'mass_ledger':ledger,
            'explosion':{'domain_truncated':any(item.get('explosion',{}).get('domain_truncated',True) for item in child_data),
                         'endpoint_results':[item.get('explosion',{}) for item in child_data],
                         'combination':'Frechet union upper bound across endpoints; intersection interval recorded; plume interaction unresolved'},
            'stage_elapsed_ms':{'endpoint_a':endpoint_results[0].get('elapsed_ms'),
                                'endpoint_b':endpoint_results[1].get('elapsed_ms'),
                                'endpoint_aggregation':(time.perf_counter()-started)*1000},
            'risk_semantics':{'observed_release':'conditional harm for both provider endpoints; no initiating-frequency multiplier',
                              'endpoint_combination':'Frechet union upper bound min(1,sum(endpoint harm)); intersection lower/upper interval recorded; no independence assumed',
                              'interaction':'endpoint plume, pressure and inventory feedback are not jointly solved'},
            'limitations':['Two provider-resolved endpoints are evaluated separately and union-bounded at receptors.',
                           'Cross-endpoint jet/plume interaction, pipe pressure coupling and dynamic shared-inventory feedback are not resolved.',
                           'The event frequency is bound once to the shared two-sided rupture event; endpoint outputs are not assigned separate frequencies.'],
        }
        combined={'data':data,'facility_digest':pipeline.facility.digest(),
                  'request_digest':request.digest(),
                  'backend_config_digest':endpoint_results[0].get('backend_config_digest'),
                  'worker_sha256':endpoint_results[0].get('worker_sha256'),
                  'adapter_source_digest':endpoint_results[0].get('adapter_source_digest'),
                  'elapsed_ms':(time.perf_counter()-started)*1000,
                  'physical_validation_claim':False}
        if request.frequency_event is not None:
            combined['frequency_event']=request.frequency_event.model_dump(mode='json')
            combined['frequency_scope']='single two-sided initiating event; endpoint union bound; not total annual facility IR'
            combined['release_termination']=request.release_termination.model_dump(mode='json')
            combined['release_termination_verification']='shared two-ended boundary declared by provider; cross-endpoint pressure/inventory feedback not independently validated'
        return combined
    payload=request.model_dump(mode='json')
    if request.resolved_release is not None:
        payload['source_input']=resolved_source_context(request.resolved_release,request.weather)
    elif request.resolved_liquid_release is not None:
        payload['source_input']=resolved_liquid_source_context(request.resolved_liquid_release,request.weather)
    payload['receptors']=[x.model_dump(mode='json') for x in pipeline.facility.receptors]
    result=pipeline.backend.run('consequence_chain',payload)
    result['facility_digest']=pipeline.facility.digest()
    if request.frequency_event is not None:
        result['frequency_event'] = request.frequency_event.model_dump(mode='json')
        result['frequency_scope'] = 'single initiating event; other LOC consequences may be uncomputed; not total annual facility IR'
        result['release_termination'] = request.release_termination.model_dump(mode='json')
        result['release_termination_verification'] = 'declared boundary only; isolation/depletion not independently validated by this binding'
    return result
