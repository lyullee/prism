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
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, Name, canonical_digest
from .frequency import FrequencyEvent


class LiteratureFrequencyScenario(Contract):
    id: Name
    asset_quantiles: dict[str, Literal["p05", "published", "p95"]] = Field(default_factory=dict)
    event_quantiles: dict[str, Literal["p05", "published", "p95"]] = Field(default_factory=dict)
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


def _event_frequency(event: FrequencyEvent, quantile: str) -> float:
    if quantile == "published":
        return event.annual_frequency_per_year
    value = event.marginal_p05_per_year if quantile == "p05" else event.marginal_p95_per_year
    if value is None:
        raise ValueError(f"event {event.id} has no published {quantile} frequency bound")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"event {event.id} has an invalid published {quantile} frequency bound")
    return value


def literature_frequency_uncertainty(result: dict, scenarios: tuple[LiteratureFrequencyScenario, ...]) -> dict:
    """Reweight saved risk atoms using published event frequency bounds.

    The physical harm, weather, population, barrier and ignition terms remain
    fixed.  Every generated asset must be addressed explicitly, and a p05/p95
    case fails if any of its event rows lacks a corresponding published bound.
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
        outputs.append({
            'scenario': scenario.model_dump(mode='json'),
            'known_annual_ir_low_high': ir,
            'known_expected_death_fn_low_high': fn,
            'asset_known_annual_expected_fatalities_low_high': contribution,
            'asset_rank_by_known_expected_fatalities_low_high': ranked,
            'event_frequency_per_year': event_frequency,
            'uncomputed_cases': result['uncomputed_cases'],
            'declared_scope_annual_ir_low_high': ir if result['declared_scope_numerically_complete'] else None,
            'total_facility_annual_ir_low_high': ir if result['total_facility_annual_ir_low_high'] is not None else None,
        })
    return {
        'campaign_digest': result['campaign_digest'],
        'physical_risk_atoms_digest': canonical_digest(atoms),
        'scenarios': outputs,
        'fresh_physics_executed': False,
        'statistical_confidence_interval': False,
        'facility_credible_interval': False,
        'semantics': 'published marginal event-frequency quantiles with an explicit within-asset shared or independent-event bound comparison; fixed physical harm/weather/barrier/population/ignition; incomplete scope remains incomplete',
        'correlation_comparison_present': any(
            s.correlation_assumption == 'independent_event_bounds' for s in scenarios
        ) and any(s.correlation_assumption == 'within_asset_shared_quantile' for s in scenarios),
        'physical_validation_claim': False,
    }
