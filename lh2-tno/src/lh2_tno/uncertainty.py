"""Literature-frequency uncertainty for already-computed risk atoms.

This module changes only initiating frequencies.  It never reruns physics and
it never invents a distribution for an event without published marginal
limits.  A scenario assigns one published quantile to each frequency asset;
all LOC rows belonging to that asset use the same quantile direction.  This
is an explicit within-asset correlation assumption, not a facility-wide
credible interval.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, Name, canonical_digest
from .frequency import FrequencyEvent


class LiteratureFrequencyScenario(Contract):
    id: Name
    asset_quantiles: dict[str, Literal["p05", "published", "fixed", "p95"]] = Field(default_factory=dict)
    event_quantiles: dict[str, Literal["p05", "published", "fixed", "p95"]] = Field(default_factory=dict)
    provenance: Name
    correlation_assumption: Literal["within_asset_shared_quantile", "independent_event_bounds"] = "within_asset_shared_quantile"

    @model_validator(mode="after")
    def nonempty(self):
        if self.correlation_assumption == "within_asset_shared_quantile":
            if not self.asset_quantiles or self.event_quantiles:
                raise ValueError("within-asset scenarios require asset quantiles only")
            if any(not k.strip() for k in self.asset_quantiles):
                raise ValueError("explicit asset quantiles required")
        else:
            if not self.event_quantiles or self.asset_quantiles:
                raise ValueError("independent-event scenarios require event quantiles only")
            if any(not k.strip() for k in self.event_quantiles):
                raise ValueError("explicit event quantiles required")
        return self


class LiteratureFrequencyDistributionScenario(Contract):
    """A published-rate distribution sampling assumption.

    Sampling is allowed only when every event carries the catalogue's
    published log-rate ``mu`` and ``sigma``.  The correlation choice is
    explicit: one normal draw per asset, or one draw per event.
    """

    id: Name
    provenance: Name
    correlation_assumption: Literal["within_asset_shared_normal", "independent_event_normal"]
    fixed_event_policy: Literal["reject", "hold_published"] = "reject"


def _event_frequency(event: FrequencyEvent, quantile: str) -> float:
    if quantile in {"published", "fixed"}:
        return event.annual_frequency_per_year
    value = event.marginal_p05_per_year if quantile == "p05" else event.marginal_p95_per_year
    if value is None:
        raise ValueError(f"event {event.id} has no published {quantile} frequency bound")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"event {event.id} has an invalid published {quantile} frequency bound")
    return value


def _scenario_family_contribution(
    atoms: list[dict],
    event_frequency: dict[str, float],
) -> dict[str, list[float]]:
    """Return expected-fatality views grouped by the atom's scenario families."""
    contribution: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for atom in atoms:
        families = atom.get("scenario_families", ())
        if not isinstance(families, (list, tuple)):
            continue
        weight = event_frequency[atom["event_id"]] * atom["conditional_weight"]
        for family in families:
            if not isinstance(family, str) or not family.strip():
                continue
            for endpoint in range(2):
                contribution[family][endpoint] += weight * atom[
                    "expected_deaths_low_high"
                ][endpoint]
    return dict(sorted(contribution.items()))


def _rank_contributions(
    contribution: dict[str, list[float]],
) -> list[dict[str, int]]:
    ranks: list[dict[str, int]] = []
    families = sorted(contribution)
    for endpoint in range(2):
        order = sorted(
            families,
            key=lambda family: (-contribution[family][endpoint], family),
        )
        ranks.append({family: rank for rank, family in enumerate(order, start=1)})
    return ranks


def literature_frequency_uncertainty(result: dict, scenarios: tuple[LiteratureFrequencyScenario, ...]) -> dict:
    """Reweight saved risk atoms using published bounds and explicit fixed rates.

    The physical harm, weather, population, barrier and ignition terms remain
    fixed. Every generated asset must be addressed explicitly. A p05/p95 case
    fails if any of its event rows lacks a corresponding published bound;
    ``fixed`` deliberately retains that event's declared catalogue rate.
    """
    if not scenarios or len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("nonempty unique literature-frequency scenarios required")
    events = {e["id"]: FrequencyEvent.model_validate_json(json.dumps(e, allow_nan=False))
              for e in result["events"]}
    assets = {e.asset_id for e in events.values()}
    ids = set(result["known_contribution_annual_ir_low_high"])
    atoms = result["risk_atoms"]
    event_ids = set(events)
    for scenario in scenarios:
        if scenario.correlation_assumption == "within_asset_shared_quantile":
            if set(scenario.asset_quantiles) != assets:
                raise ValueError("each within-asset scenario must address every generated asset")
        elif set(scenario.event_quantiles) != event_ids:
            raise ValueError("each independent-event scenario must address every generated event")

    for atom in atoms:
        event = events.get(atom["event_id"])
        if event is None or atom["asset_id"] != event.asset_id:
            raise ValueError("risk atom does not match its originating event")
        if event.marginal_p05_per_year is not None or event.marginal_p95_per_year is not None:
            if event.marginal_p05_per_year is None or event.marginal_p95_per_year is None:
                raise ValueError(f"event {event.id} must provide both p05 and p95 frequency bounds")
            if not (event.marginal_p05_per_year <= event.annual_frequency_per_year <= event.marginal_p95_per_year):
                raise ValueError(f"event {event.id} has unordered published frequency bounds")
        if not math.isfinite(atom["initiating_frequency_per_year"]) or atom["initiating_frequency_per_year"] < 0:
            raise ValueError("risk atom frequency must be finite and nonnegative")
        if atom["initiating_frequency_per_year"] != event.annual_frequency_per_year:
            raise ValueError("risk atom does not retain the generated event frequency")
        if set(atom["receptor_harm_low_high"]) != ids:
            raise ValueError("risk atom receptor set mismatch")
        if len(atom["expected_deaths_low_high"]) != 2:
            raise ValueError("risk atom requires two expected-death endpoints")

    computed_assets = {a["asset_id"] for a in atoms}
    outputs = []
    for scenario in scenarios:
        if scenario.correlation_assumption == "within_asset_shared_quantile":
            event_frequency = {event.id: _event_frequency(event, scenario.asset_quantiles[event.asset_id])
                               for event in events.values()}
        else:
            event_frequency = {event.id: _event_frequency(event, scenario.event_quantiles[event.id])
                               for event in events.values()}
        ir = {rid: [0.0, 0.0] for rid in sorted(ids)}
        contribution = {asset: [0.0, 0.0] for asset in sorted(assets)}
        outcomes = [[], []]
        for atom in atoms:
            frequency = event_frequency[atom["event_id"]] * atom["conditional_weight"]
            for i in range(2):
                for rid in ir:
                    ir[rid][i] += frequency * atom["receptor_harm_low_high"][rid][i]
                contribution[atom["asset_id"]][i] += frequency * atom["expected_deaths_low_high"][i]
                outcomes[i].append((atom["expected_deaths_low_high"][i], frequency))
        fn = []
        for values in outcomes:
            ns = sorted({n for n, _ in values if n >= 1})
            fn.append({'expected_deaths': ns,
                       'cumulative_frequency_per_year': [sum(f for deaths, f in values if deaths >= n) for n in ns]})
        ranked = []
        for i in range(2):
            ranked.append({asset: None if asset not in computed_assets else
                           1 + sum(v[i] > value[i] and not math.isclose(v[i], value[i], rel_tol=1e-12, abs_tol=0)
                                    for key, v in contribution.items() if key in computed_assets)
                           for asset, value in contribution.items()})
        family_contribution = _scenario_family_contribution(atoms, event_frequency)
        outputs.append({
            'scenario': scenario.model_dump(mode='json'),
            'known_annual_ir_low_high': ir,
            'known_expected_death_fn_low_high': fn,
            'conditional_diagnostic_facility_annual_ir_low_high': ir,
            'conditional_diagnostic_facility_expected_death_fn_low_high': fn,
            'conditional_diagnostic_facility_risk_available': bool(atoms),
            'asset_known_annual_expected_fatalities_low_high': contribution,
            'asset_rank_by_known_expected_fatalities_low_high': ranked,
            'scenario_family_known_expected_fatalities_low_high': family_contribution,
            'scenario_family_rank_by_known_expected_fatalities_low_high': _rank_contributions(
                family_contribution
            ),
            'event_frequency_per_year': event_frequency,
            'uncomputed_cases': result['uncomputed_cases'],
            'declared_scope_annual_ir_low_high': ir if result['declared_scope_numerically_complete'] else None,
            'total_facility_annual_ir_low_high': ir if result['total_facility_annual_ir_low_high'] is not None else None,
            'provider_packet_promoted': result.get('provider_packet_promoted') is True,
            'qualified_provider_packet_case_count': result.get(
                'qualified_provider_packet_case_count', 0
            ),
            'complete_facility_qra_claim': result.get('complete_facility_qra_claim') is True,
            'physical_validation_claim': result.get('physical_validation_claim') is True,
        })
    return {
        'campaign_digest': result['campaign_digest'],
        'physical_risk_atoms_digest': canonical_digest(atoms),
        'scenarios': outputs,
        'fresh_physics_executed': False,
        'statistical_confidence_interval': False,
        'facility_credible_interval': False,
        'conditional_diagnostic_facility_risk': 'each scenario reweights the saved risk atoms and exposes a conditional facility IR/F-N diagnostic; incomplete scope, synthetic horizons, and operator limits still withhold a qualified facility total',
        'semantics': 'published marginal event-frequency quantiles plus explicit fixed catalogue rates, with within-asset shared or independent-event bound comparison; fixed physical harm/weather/barrier/population/ignition; incomplete scope remains incomplete',
        'correlation_comparison_present': any(
            s.correlation_assumption == 'independent_event_bounds' for s in scenarios
        ) and any(s.correlation_assumption == 'within_asset_shared_quantile' for s in scenarios),
        'provider_packet_promoted': result.get('provider_packet_promoted') is True,
        'provider_packet_case_count': result.get('provider_packet_case_count', 0),
        'qualified_provider_packet_case_count': result.get(
            'qualified_provider_packet_case_count', 0
        ),
        'complete_facility_qra_claim': result.get('complete_facility_qra_claim') is True,
        'physical_validation_claim': result.get('physical_validation_claim') is True,
    }


def _empirical_quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError('at least one sampled value required')
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _quantile_triplet(values: list[float]) -> list[float]:
    return [_empirical_quantile(values, p) for p in (0.05, 0.5, 0.95)]


def sample_literature_frequency_distributions(
    result: dict,
    scenarios: tuple[LiteratureFrequencyDistributionScenario, ...],
    *,
    draws: int = 1000,
    seed: int = 20261009,
) -> dict:
    """Sample published distributions and optionally retain fixed catalogue rates.

    Physical harm, weather, population, barrier and ignition terms are held
    fixed from ``result['risk_atoms']``.  Events without a published
    lognormal distribution are rejected by default; ``hold_published`` is an
    explicit option to keep their declared catalogue frequency. This is a
    frequency-model credible
    interval for the known contribution; it is not a physical or statistical
    confidence interval.  Incomplete facility scopes remain incomplete.
    """
    if not scenarios or len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError('nonempty unique distribution scenarios required')
    if not isinstance(draws, int) or draws < 100 or draws > 100_000:
        raise ValueError('draw count must be an integer from 100 to 100000')
    events = {e['id']: FrequencyEvent.model_validate_json(json.dumps(e, allow_nan=False))
              for e in result['events']}
    if not events:
        raise ValueError('distribution sampling requires generated events')
    atoms = result['risk_atoms']
    ids = set(result['known_contribution_annual_ir_low_high'])
    event_ids = set(events)
    assets = {e.asset_id for e in events.values()}
    fixed_events = {
        event.id: event
        for event in events.values()
        if event.frequency_distribution != 'published_lognormal'
    }
    for scenario in scenarios:
        if fixed_events and scenario.fixed_event_policy == 'reject':
            first = next(iter(fixed_events))
            raise ValueError(
                f'event {first} has no published lognormal distribution; '
                'set fixed_event_policy=hold_published to retain its declared catalogue rate'
            )
    for atom in atoms:
        event = events.get(atom['event_id'])
        if event is None or atom['asset_id'] != event.asset_id:
            raise ValueError('risk atom does not match its originating event')
        if set(atom['receptor_harm_low_high']) != ids or len(atom['expected_deaths_low_high']) != 2:
            raise ValueError('risk atom receptor/death endpoints do not match the campaign')
        if atom['initiating_frequency_per_year'] != event.annual_frequency_per_year:
            raise ValueError('risk atom does not retain the generated event frequency')

    outputs = []
    for scenario in scenarios:
        rng = random.Random(seed)
        ir_samples = {rid: [[], []] for rid in sorted(ids)}
        asset_samples = {asset: [[], []] for asset in sorted(assets)}
        scenario_families = sorted({
            family
            for atom in atoms
            for family in atom.get("scenario_families", ())
            if isinstance(family, str) and family.strip()
        })
        family_samples = {family: [[], []] for family in scenario_families}
        rank_sums = {asset: [0.0, 0.0] for asset in sorted(assets)}
        rank_top_counts = {asset: [0, 0] for asset in sorted(assets)}
        family_rank_sums = {family: [0.0, 0.0] for family in scenario_families}
        family_rank_top_counts = {family: [0, 0] for family in scenario_families}
        total_samples = [[], []]
        event_samples = {event_id: [] for event_id in sorted(event_ids)}
        for _ in range(draws):
            if scenario.correlation_assumption == 'within_asset_shared_normal':
                z_by_asset = {asset: rng.gauss(0.0, 1.0) for asset in sorted(assets)}
                frequencies = {
                    event.id: event.exposure_multiplier * math.exp(event.log_rate_mu + event.log_rate_sigma * z_by_asset[event.asset_id])
                    for event in events.values()
                    if event.frequency_distribution == 'published_lognormal'
                }
            else:
                frequencies = {
                    event.id: event.exposure_multiplier * math.exp(event.log_rate_mu + event.log_rate_sigma * rng.gauss(0.0, 1.0))
                    for event in events.values()
                    if event.frequency_distribution == 'published_lognormal'
                }
            if scenario.fixed_event_policy == 'hold_published':
                frequencies.update({event_id: event.annual_frequency_per_year
                                     for event_id, event in fixed_events.items()})
            for event_id, value in frequencies.items():
                event_samples[event_id].append(value)
            receptor_totals = {rid: [0.0, 0.0] for rid in sorted(ids)}
            asset_totals = {asset: [0.0, 0.0] for asset in sorted(assets)}
            family_totals = {family: [0.0, 0.0] for family in scenario_families}
            total = [0.0, 0.0]
            for atom in atoms:
                weight = frequencies[atom['event_id']] * atom['conditional_weight']
                for endpoint in range(2):
                    deaths = atom['expected_deaths_low_high'][endpoint]
                    total[endpoint] += weight * deaths
                    asset_totals[atom['asset_id']][endpoint] += weight * deaths
                    for family in atom.get('scenario_families', ()):
                        if family in family_totals:
                            family_totals[family][endpoint] += weight * deaths
                    for rid in receptor_totals:
                        receptor_totals[rid][endpoint] += weight * atom['receptor_harm_low_high'][rid][endpoint]
            for rid in receptor_totals:
                for endpoint in range(2):
                    ir_samples[rid][endpoint].append(receptor_totals[rid][endpoint])
            for asset in asset_totals:
                for endpoint in range(2):
                    asset_samples[asset][endpoint].append(asset_totals[asset][endpoint])
            for family in family_totals:
                for endpoint in range(2):
                    family_samples[family][endpoint].append(family_totals[family][endpoint])
            # Ranks are deterministic under exact ties: asset id is the
            # secondary key.  This makes a reported priority ordering
            # reproducible without pretending that ties have a physical
            # meaning.
            for endpoint in range(2):
                order = sorted(sorted(assets), key=lambda asset: (-asset_totals[asset][endpoint], asset))
                for rank, asset in enumerate(order, start=1):
                    rank_sums[asset][endpoint] += rank
                rank_top_counts[order[0]][endpoint] += 1
            for endpoint in range(2):
                family_order = sorted(
                    scenario_families,
                    key=lambda family: (-family_totals[family][endpoint], family),
                )
                if family_order:
                    for rank, family in enumerate(family_order, start=1):
                        family_rank_sums[family][endpoint] += rank
                    family_rank_top_counts[family_order[0]][endpoint] += 1
            for endpoint in range(2):
                total_samples[endpoint].append(total[endpoint])

        outputs.append({
            'scenario': scenario.model_dump(mode='json'),
            'draws': draws,
            'seed': seed,
            'quantiles': [0.05, 0.5, 0.95],
            'event_frequency_quantiles_per_year': {event_id: _quantile_triplet(values) for event_id, values in event_samples.items()},
            'known_annual_ir_quantiles': {rid: [_quantile_triplet(endpoints) for endpoints in endpoint_values]
                                          for rid, endpoint_values in ir_samples.items()},
            'conditional_diagnostic_facility_annual_ir_quantiles': {rid: [_quantile_triplet(endpoints) for endpoints in endpoint_values]
                                                                     for rid, endpoint_values in ir_samples.items()},
            'known_expected_death_quantiles': [_quantile_triplet(endpoints) for endpoints in total_samples],
            'conditional_diagnostic_facility_expected_death_quantiles': [_quantile_triplet(endpoints) for endpoints in total_samples],
            'conditional_diagnostic_facility_risk_available': bool(atoms),
            'asset_known_expected_death_quantiles': {asset: [_quantile_triplet(endpoints) for endpoints in endpoint_values]
                                                     for asset, endpoint_values in asset_samples.items()},
            'asset_rank_stability': {
                asset: {
                    'mean_rank_low_high': [rank_sums[asset][i] / draws for i in range(2)],
                    'top_rank_probability_low_high': [rank_top_counts[asset][i] / draws for i in range(2)],
                    'rank_definition': '1 is highest known expected-fatality contribution; exact ties use asset id',
                }
                for asset in sorted(assets)
            },
            'scenario_family_expected_death_quantiles': {
                family: [_quantile_triplet(endpoints) for endpoints in endpoint_values]
                for family, endpoint_values in family_samples.items()
            },
            'scenario_family_rank_stability': {
                family: {
                    'mean_rank_low_high': [
                        family_rank_sums[family][i] / draws for i in range(2)
                    ],
                    'top_rank_probability_low_high': [
                        family_rank_top_counts[family][i] / draws for i in range(2)
                    ],
                    'rank_definition': '1 is highest known expected-fatality contribution; exact ties use family id',
                }
                for family in scenario_families
            },
            'uncomputed_cases': result['uncomputed_cases'],
            'facility_credible_interval': result['total_facility_annual_ir_low_high'] is not None,
            'provider_packet_promoted': result.get('provider_packet_promoted') is True,
            'qualified_provider_packet_case_count': result.get(
                'qualified_provider_packet_case_count', 0
            ),
            'complete_facility_qra_claim': result.get('complete_facility_qra_claim') is True,
            'physical_validation_claim': result.get('physical_validation_claim') is True,
        })
    return {
        'campaign_digest': result['campaign_digest'],
        'physical_risk_atoms_digest': canonical_digest(atoms),
        'scenarios': outputs,
        'fresh_physics_executed': False,
        'statistical_confidence_interval': False,
        'frequency_distribution_credible_interval': True,
        'facility_credible_interval': result['total_facility_annual_ir_low_high'] is not None,
        'provider_packet_promoted': result.get('provider_packet_promoted') is True,
        'provider_packet_case_count': result.get('provider_packet_case_count', 0),
        'qualified_provider_packet_case_count': result.get(
            'qualified_provider_packet_case_count', 0
        ),
        'complete_facility_qra_claim': result.get('complete_facility_qra_claim') is True,
        'conditional_diagnostic_facility_risk': 'sampled known-atom facility expected-death totals are diagnostic frequency-model outputs; they are not a qualified facility confidence interval when scope blockers remain',
        'semantics': 'published lognormal initiating-frequency distributions with explicit shared-asset or independent-event normal draws; optional fixed events retain their declared catalogue frequency; physical harm/weather/barrier/population/ignition remain fixed and incomplete scope remains incomplete',
        'physical_validation_claim': result.get('physical_validation_claim') is True,
    }
