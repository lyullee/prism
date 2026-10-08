"""Auditable initiating-event frequencies for generic LH2 facilities.

Purple LOCs and hydrogen area bins are alternative partitions, not additive
estimates of the same equipment's failures. No pressure-to-frequency heuristic
or implicit GH2/OREDA fallback is used.
"""
from __future__ import annotations

import json
import math
from importlib.resources import files
from statistics import NormalDist
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Contract, Name, Positive, Nonnegative, Fraction, Facility, canonical_digest


class ReleaseDefinition(Contract):
    mode: Literal['instantaneous_inventory', 'inventory_over_600s', 'hole',
                  'two_sided_rupture', 'maximum_relief_discharge']
    hole_diameter_m: Positive | None = None
    area_fraction: Fraction | None = None
    ruptured_tubes: int = Field(default=1, ge=1)


class FrequencyEvent(Contract):
    id: Name
    asset_id: Name
    model_component_id: Name
    profile: Name
    loc: Name
    basis: Literal['TNO_PURPLE_LOC', 'LH2_LITERATURE']
    base_rate: Nonnegative
    rate_unit: Literal['item^-1 year^-1', 'm^-1 year^-1']
    exposure_multiplier: Positive
    annual_frequency_per_year: Nonnegative
    statistic: Literal['published_default', 'published_median']
    marginal_p05_per_year: Nonnegative | None = None
    marginal_p95_per_year: Nonnegative | None = None
    frequency_distribution: Literal['none', 'published_lognormal'] = 'none'
    log_rate_mu: float | None = None
    log_rate_sigma: Positive | None = None
    source: Name
    source_sha256: Name
    catalogue_digest: Name
    release: ReleaseDefinition
    classification_basis: Name
    limitations: tuple[str, ...]
    physical_validation_claim: Literal[False] = False

    @model_validator(mode='after')
    def arithmetic(self):
        if not math.isclose(self.annual_frequency_per_year, self.base_rate*self.exposure_multiplier, rel_tol=1e-12, abs_tol=0):
            raise ValueError('initiating frequency does not match rate times exposure')
        if self.release.mode in ('hole', 'two_sided_rupture') and self.release.hole_diameter_m is None:
            raise ValueError('effective release diameter required')
        if self.frequency_distribution == 'published_lognormal':
            if self.log_rate_mu is None or self.log_rate_sigma is None:
                raise ValueError('published lognormal distribution requires mu and sigma')
            if not math.isfinite(self.log_rate_mu) or self.log_rate_sigma <= 0:
                raise ValueError('published lognormal distribution requires finite mu and positive sigma')
        elif self.log_rate_mu is not None or self.log_rate_sigma is not None:
            raise ValueError('distribution parameters require published_lognormal provenance')
        return self


class FrequencyAsset(Contract):
    id: Name
    model_component_id: Name
    profile: Name
    # Explicit engineering classification, especially pressure vs atmospheric
    # cryogenic storage and tube/shell pressure hierarchy. Never infer from P alone.
    classification_basis: Name
    physical_scope_ids: tuple[Name, ...]
    count: int = Field(default=1, ge=1)
    nominal_diameter_m: Positive | None = None
    length_per_item_m: Positive | None = None
    vessel_external_impact_or_operating_error: bool | None = None
    pipe_conditions: Literal['default_conditions', 'increased_failure_potential'] | None = None
    pipe_correction_factor: float | None = None
    correction_provenance: Name | None = None
    # Optional allocation of an item/length frequency to one reviewed physical
    # rupture location.  Without this factor a generated event represents
    # the entire counted exposure and cannot be bound to one outlet.
    location_weight: Fraction | None = None
    location_weight_provenance: Name | None = None
    relief_direct_substance_contact_and_atmospheric_discharge: bool | None = None

    @model_validator(mode='after')
    def validate_scope(self):
        if not self.physical_scope_ids or len(set(self.physical_scope_ids)) != len(self.physical_scope_ids):
            raise ValueError('nonempty unique physical scope ids required')
        if len(self.physical_scope_ids) != self.count:
            raise ValueError('one physical scope id per counted item/pipe segment required')
        if self.profile not in catalogue()['profiles']:
            raise ValueError('no reviewed frequency profile; do not substitute zero or an implicit proxy')
        profile = catalogue()['profiles'][self.profile]
        needs_d = self.profile.startswith('LH2_') or self.profile == 'TNO_PIPE' or self.profile.startswith('TNO_PUMP') or self.profile == 'TNO_HX_INSIDE_WEAK_SHELL' or self.profile == 'TNO_HX_INSIDE_STRONG_SHELL'
        if needs_d and self.nominal_diameter_m is None:
            raise ValueError('reference/connecting pipe diameter required')
        if profile['unit'] == 'm^-1 year^-1':
            if self.length_per_item_m is None:
                raise ValueError('pipe frequency requires length, not a component count alone')
        elif self.length_per_item_m is not None:
            raise ValueError('item frequency cannot be multiplied by pipe length')
        vessel = self.profile in ('TNO_PRESSURE_VESSEL', 'TNO_PROCESS_VESSEL', 'TNO_REACTOR_VESSEL')
        if vessel != (self.vessel_external_impact_or_operating_error is not None):
            raise ValueError('vessel external-impact/operating-error applicability must be explicit and vessel-only')
        if self.profile == 'TNO_PIPE':
            if self.pipe_conditions is None or self.pipe_correction_factor is None:
                raise ValueError('explicit Purple pipe conditions and correction factor required')
            factor = self.pipe_correction_factor
            if self.pipe_conditions == 'default_conditions' and factor != 1:
                raise ValueError('default pipe conditions require factor one')
            if self.pipe_conditions == 'increased_failure_potential' and (not 3 <= factor <= 10 or not self.correction_provenance):
                raise ValueError('Purple pipe correction requires reviewed factor 3-10 and provenance')
        elif any(x is not None for x in (self.pipe_conditions, self.pipe_correction_factor, self.correction_provenance)):
            raise ValueError('Purple pipe correction is not a generic LH2 multiplier')
        if self.profile == 'TNO_RELIEF_DEVICE':
            if self.relief_direct_substance_contact_and_atmospheric_discharge is not True:
                raise ValueError('Purple relief discharge requires direct substance contact and atmospheric discharge')
        elif self.relief_direct_substance_contact_and_atmospheric_discharge is not None:
            raise ValueError('relief applicability supplied for unrelated profile')
        if (self.location_weight is None) != (self.location_weight_provenance is None):
            raise ValueError('location weight and its provenance must be supplied together')
        if self.location_weight is not None and self.location_weight <= 0:
            raise ValueError('location weight must be positive')
        return self


class FrequencyPlan(Contract):
    id: Name
    assets: tuple[FrequencyAsset, ...]
    excluded_model_components: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def ownership(self):
        if not self.assets or len({x.id for x in self.assets}) != len(self.assets):
            raise ValueError('nonempty unique assets required')
        scopes = [scope for x in self.assets for scope in x.physical_scope_ids]
        if len(set(scopes)) != len(scopes):
            raise ValueError('physical scope counted twice; alternative frequency partitions cannot be added')
        if any(not v.strip() for v in self.excluded_model_components.values()):
            raise ValueError('exclusion reason required')
        return self


def catalogue() -> dict:
    # Fresh deserialization prevents caller mutation of shared catalogue state.
    return json.loads(files('lh2_tno').joinpath('data/frequency_catalogue.json').read_text(encoding='utf-8'))


def generate_events(facility: Facility, plan: FrequencyPlan) -> tuple[FrequencyEvent, ...]:
    known = {x.id for x in facility.components}
    selected = {x.model_component_id for x in plan.assets}
    excluded = set(plan.excluded_model_components)
    if selected - known or excluded - known or selected & excluded:
        raise ValueError('frequency plan references unknown or both selected/excluded components')
    if known - selected - excluded:
        raise ValueError('every model component must have a frequency scope or explicit exclusion reason')
    data = catalogue()
    out = []
    for asset in plan.assets:
        profile = data['profiles'][asset.profile]
        rows = profile['events']
        limitations = list(profile['limitations'])
        if asset.profile == 'TNO_PIPE':
            d = asset.nominal_diameter_m
            index = 0 if d < .075 else 1 if d <= .150 else 2
            rows = [{**r, 'rate': r['rates_by_diameter'][index]} for r in rows]
            multiplier = max(10., asset.length_per_item_m) * asset.count * asset.pipe_correction_factor
            limitations.append('Purple 10 m minimum includes flanges; do not count those flanges again. Allocate rupture location weights separately; do not repeat the whole frequency at every location.')
        elif profile['unit'] == 'm^-1 year^-1':
            multiplier = asset.length_per_item_m * asset.count
        else:
            multiplier = float(asset.count)
        if asset.location_weight is not None:
            multiplier *= asset.location_weight
            limitations.append('This event is allocated to one reviewed physical location with an explicit location_weight; the remaining exposure needs separate physical scope rows.')
        for row in rows:
            rate = row['rate']
            if asset.vessel_external_impact_or_operating_error and row['loc'] in ('G1', 'G2'):
                rate += 5e-6
            release = dict(row['release'])
            rule = release.pop('diameter_rule', None)
            if rule == 'area_fraction':
                release['hole_diameter_m'] = asset.nominal_diameter_m * math.sqrt(release['area_fraction'])
            elif rule == 'ten_percent_max_50mm':
                release['hole_diameter_m'] = min(.1 * asset.nominal_diameter_m, .05)
            elif rule == 'full_bore':
                release['hole_diameter_m'] = asset.nominal_diameter_m
            p05 = p95 = None
            if 'mu' in row:
                p05 = multiplier * math.exp(row['mu'] + NormalDist().inv_cdf(.05)*row['sigma'])
                p95 = multiplier * math.exp(row['mu'] + NormalDist().inv_cdf(.95)*row['sigma'])
                limitations.append('Marginal lognormal bounds; cross-bin correlation is unavailable, so summed bounds are not facility credible intervals.')
            out.append(FrequencyEvent(id=f'{plan.id}/{asset.id}/{row["loc"]}', asset_id=asset.id,
                model_component_id=asset.model_component_id, profile=asset.profile, loc=row['loc'],
                basis=profile['basis'], base_rate=rate, rate_unit=profile['unit'],
                exposure_multiplier=multiplier, annual_frequency_per_year=rate*multiplier,
                statistic=profile['statistic'], marginal_p05_per_year=p05, marginal_p95_per_year=p95,
                frequency_distribution='published_lognormal' if 'mu' in row else 'none',
                log_rate_mu=row.get('mu'), log_rate_sigma=row.get('sigma'),
                source=profile['source'], source_sha256=profile['source_sha256'], catalogue_digest=canonical_digest(data),
                release=ReleaseDefinition(**release), classification_basis=asset.classification_basis,
                limitations=tuple(dict.fromkeys(limitations))))
    return tuple(out)


def bind_event(request, event: FrequencyEvent):
    """Bind frequency to a matching hole or provider-resolved accident exit.

    A full-bore two-sided rupture requires two provider exits and one shared
    event frequency. Never approximate it with one short tank/nozzle history.
    Instantaneous inventory is accepted only when the explicit inventory
    liquid-jet operator is selected.
    """
    from .consequences import ConsequenceRequest
    if request.component_id != event.model_component_id:
        raise ValueError('failure component and current source component must match; an upstream-port adapter is required otherwise')
    if event.release.mode == 'two_sided_rupture':
        if request.source_operator != 'equipment_two_sided_rupture' or request.resolved_release_set is None:
            raise ValueError('two-sided rupture requires a provider-resolved two-endpoint release set; a single nozzle is not accepted')
        if request.release_termination is None or request.release_termination.basis != 'two_sided_rupture':
            raise ValueError('two-sided rupture binding requires explicit two-sided termination provenance')
        payload = request.model_dump(mode='json')
        if request.annual_frequency_per_year is not None:
            raise ValueError('remove external frequency before binding a catalogue event')
        payload['annual_frequency_per_year'] = event.annual_frequency_per_year
        payload['annual_frequency_provenance'] = f'{event.id}; {event.source}; {event.source_sha256}'
        payload['frequency_event'] = event.model_dump(mode='json')
        return ConsequenceRequest.model_validate_json(json.dumps(payload, allow_nan=False))
    if event.release.mode == 'maximum_relief_discharge':
        if request.source_operator != 'equipment_emergency_relief' or request.resolved_release is None:
            raise ValueError('maximum relief discharge requires a provider-resolved emergency-relief gas exit')
        if request.resolved_release.event_kind != 'emergency_relief' or request.resolved_release.failure_opening_diameter_m is not None:
            raise ValueError('maximum relief discharge cannot be bound to a random leak opening or normal vent')
        if request.release_termination is None or request.release_termination.basis != 'emergency_relief_discharge':
            raise ValueError('maximum relief discharge requires explicit emergency-relief termination provenance')
        payload = request.model_dump(mode='json')
        if request.annual_frequency_per_year is not None:
            raise ValueError('remove external frequency before binding a catalogue event')
        payload['annual_frequency_per_year'] = event.annual_frequency_per_year
        payload['annual_frequency_provenance'] = f'{event.id}; {event.source}; {event.source_sha256}'
        payload['frequency_event'] = event.model_dump(mode='json')
        return ConsequenceRequest.model_validate_json(json.dumps(payload, allow_nan=False))
    if event.release.mode != 'hole':
        if not (event.release.mode == 'instantaneous_inventory' and
                request.source_operator == 'inventory_liquid_jet'):
            if not (event.release.mode == 'inventory_over_600s' and
                    request.source_operator == 'inventory_over_600s'):
                raise ValueError('this LOC requires a different release operator; frequency exists but its consequences remain uncomputed')
        if request.release_termination is None:
            raise ValueError('non-hole inventory binding requires explicit termination provenance')
        if event.release.mode == 'instantaneous_inventory' and request.release_termination.basis != 'inventory_depletion':
            raise ValueError('instantaneous inventory binding requires an inventory-depletion termination basis')
        if event.release.mode == 'inventory_over_600s' and request.release_termination.basis != 'inventory_over_600s':
            raise ValueError('600 s inventory binding requires an inventory-over-600s termination basis')
        payload = request.model_dump(mode='json')
        if request.annual_frequency_per_year is not None:
            raise ValueError('remove external frequency before binding a catalogue event')
        payload['annual_frequency_per_year'] = event.annual_frequency_per_year
        payload['annual_frequency_provenance'] = f'{event.id}; {event.source}; {event.source_sha256}'
        payload['frequency_event'] = event.model_dump(mode='json')
        return ConsequenceRequest.model_validate_json(json.dumps(payload, allow_nan=False))
    if request.resolved_release is not None:
        if request.resolved_release.event_kind!='accidental_leak' or request.resolved_release.failure_opening_diameter_m is None:
            raise ValueError('resolved source frequency requires an accidental leak with a declared failure opening')
        diameter=request.resolved_release.failure_opening_diameter_m
    elif request.resolved_liquid_release is not None:
        if request.resolved_liquid_release.event_kind!='accidental_leak' or request.resolved_liquid_release.failure_opening_diameter_m is None:
            raise ValueError('resolved liquid frequency requires an accidental leak with a declared failure opening')
        diameter=request.resolved_liquid_release.failure_opening_diameter_m
    else:
        diameter = request.source_input['nozzle']['diameter_m']
    if not math.isclose(diameter, event.release.hole_diameter_m, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError('frequency leak size must equal the physical source opening')
    if event.exposure_multiplier != 1:
        raise ValueError('aggregated items/length need explicit location weights; cannot assign all frequency to one source point')
    payload = request.model_dump(mode='json')
    if request.annual_frequency_per_year is not None:
        raise ValueError('remove external frequency before binding a catalogue event')
    payload['annual_frequency_per_year'] = event.annual_frequency_per_year
    payload['annual_frequency_provenance'] = f'{event.id}; {event.source}; {event.source_sha256}'
    payload['frequency_event'] = event.model_dump(mode='json')
    return ConsequenceRequest.model_validate_json(json.dumps(payload, allow_nan=False))


def forecast_initiation_probability(event: FrequencyEvent, horizon_s: float) -> dict:
    if not math.isfinite(horizon_s) or horizon_s <= 0:
        raise ValueError('positive finite future horizon required')
    intensity = event.annual_frequency_per_year/(365.25*86400)
    return {'event_id': event.id, 'horizon_s': horizon_s,
            'initiation_probability': -math.expm1(-intensity*horizon_s),
            'initiation_intensity_per_s': intensity,
            'conditioning': 'not yet initiated; stationary calendar-year Poisson approximation; 365.25 days/year',
            'physical_validation_claim': False}


class DemandFailure(Contract):
    id: Name
    demands_per_year: Nonnegative
    failure_probability_per_demand: Fraction
    provenance: Name

    def annual_failure_rate(self) -> dict:
        return {'id': self.id, 'annual_frequency_per_year': self.demands_per_year*self.failure_probability_per_demand,
                'units': 'year^-1', 'meaning': 'failure on a demand; not spontaneous leak or normal vent frequency',
                'provenance': self.provenance, 'physical_validation_claim': False}


class EventBranch(Contract):
    id: Name
    probability_given_initiation: Fraction
    provenance: Name


def branch_frequencies(event: FrequencyEvent, branches: tuple[EventBranch, ...]) -> dict:
    if not branches or len({x.id for x in branches}) != len(branches):
        raise ValueError('unique nonempty branch ids required')
    if not math.isclose(sum(x.probability_given_initiation for x in branches), 1., abs_tol=1e-10, rel_tol=0):
        raise ValueError('mutually exclusive branches must close to one, including no ignition/no harm')
    return {'initiating_event': event.id, 'branches': [
        {'id': x.id, 'annual_frequency_per_year': event.annual_frequency_per_year*x.probability_given_initiation,
         'probability_given_initiation': x.probability_given_initiation, 'provenance': x.provenance} for x in branches],
        'conditioning': 'reviewed mutually exclusive conditional branches; initiation counted once'}


class ConfirmedLeakExperience(Contract):
    profile: Name
    loc: Name
    rate_unit: Literal['item^-1 year^-1', 'm^-1 year^-1']
    confirmed_leak_count: int = Field(ge=0)
    exposure: Positive
    origin: Literal['reviewed_field_event_register']
    observation_id: Name
    provenance: Name
    complete_ascertainment: Literal[True]
    # This is a cumulative register snapshot, not a sensor alarm stream. Updates
    # are pure recomputations from the original prior, not repeated ingestion.


class GammaRatePrior(Contract):
    profile: Name
    loc: Name
    rate_unit: Literal['item^-1 year^-1', 'm^-1 year^-1']
    shape: Positive
    exposure_rate: Positive
    provenance: Name


def updated_rate(prior: GammaRatePrior, observed: ConfirmedLeakExperience) -> dict:
    """Optional explicit Gamma-Poisson model, not Brooks lognormal re-fitting."""
    if (prior.profile, prior.loc, prior.rate_unit) != (observed.profile, observed.loc, observed.rate_unit):
        raise ValueError('same equipment/LOC/exposure unit required for Bayesian updating')
    shape = prior.shape + observed.confirmed_leak_count
    rate = prior.exposure_rate + observed.exposure
    return {'distribution': 'Gamma(shape, exposure_rate)', 'shape': shape, 'exposure_rate': rate,
            'mean_rate': shape/rate, 'rate_unit': prior.rate_unit,
            'variance': shape/rate**2, 'prior_provenance': prior.provenance,
            'observation_id': observed.observation_id, 'observation_provenance': observed.provenance,
            'conditioning': 'stationary Poisson counts, complete ascertainment; explicit alternative prior, not a conversion of published lognormal uncertainty',
            'physical_validation_claim': False}
