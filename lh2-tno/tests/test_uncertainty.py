import json

import pytest

from lh2_tno.contracts import Facility
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.uncertainty import (LiteratureFrequencyDistributionScenario,
                                  LiteratureFrequencyScenario,
                                  literature_frequency_uncertainty,
                                  sample_literature_frequency_distributions)


def _valve_events():
    facility = Facility.model_validate_json(open('examples/lh2_frequency_facility.json', encoding='utf-8').read())
    plan = FrequencyPlan.model_validate_json(json.dumps({
        'id': 'uncertainty-test',
        'assets': [{
            'id': 'valves', 'model_component_id': 'valves', 'profile': 'LH2_VALVE',
            'physical_scope_ids': ['valve-1'], 'count': 1, 'nominal_diameter_m': .025,
            'classification_basis': 'test-only reviewed category'
        }], 'excluded_model_components': {
            x.id: 'test scope excludes other components' for x in facility.components if x.id != 'valves'
        }
    }))
    return generate_events(facility, plan)


def _result(events):
    atoms = [{
        'event_id': event.id, 'asset_id': event.asset_id,
        'conditional_weight': 1.0,
        'initiating_frequency_per_year': event.annual_frequency_per_year,
        'receptor_harm_low_high': {'worker': [.1, .2]},
        'expected_deaths_low_high': [.1, .2]
    } for event in events]
    return {
        'events': [event.model_dump(mode='json') for event in events],
        'risk_atoms': atoms,
        'known_contribution_annual_ir_low_high': {'worker': [.1, .2]},
        'uncomputed_cases': [], 'declared_scope_numerically_complete': True,
        'total_facility_annual_ir_low_high': [.1, .2],
        'campaign_digest': 'campaign',
    }


def _lh2_events():
    facility = json.loads(open('examples/lh2_frequency_facility.json', encoding='utf-8').read())
    plan = json.loads(open('examples/lh2_frequency_plan.json', encoding='utf-8').read())
    events = generate_events(Facility.model_validate_json(json.dumps(facility)),
                             FrequencyPlan.model_validate_json(json.dumps(plan)))
    return tuple(event for event in events if event.profile == 'LH2_VALVE')


def test_published_literature_quantiles_reweight_atoms_without_physics():
    events = _valve_events()
    payload = _result(events)
    for atom in payload['risk_atoms']:
        atom['scenario_families'] = ['valve_hole', 'liquid_two_phase']
    result = literature_frequency_uncertainty(payload, (
        LiteratureFrequencyScenario(id='low', asset_quantiles={'valves': 'p05'}, provenance='published test bounds'),
        LiteratureFrequencyScenario(id='high', asset_quantiles={'valves': 'p95'}, provenance='published test bounds'),
    ))
    assert result['fresh_physics_executed'] is False
    low, high = result['scenarios']
    assert low['event_frequency_per_year'][events[0].id] == events[0].marginal_p05_per_year
    assert high['event_frequency_per_year'][events[0].id] == events[0].marginal_p95_per_year
    assert set(low['scenario_family_known_expected_fatalities_low_high']) == {
        'valve_hole', 'liquid_two_phase'
    }
    assert low['scenario_family_rank_by_known_expected_fatalities_low_high'][0] == {
        'liquid_two_phase': 1, 'valve_hole': 2
    }
    assert result['facility_credible_interval'] is False
    assert result['provider_packet_promoted'] is False
    assert result['qualified_provider_packet_case_count'] == 0
    assert result['complete_facility_qra_claim'] is False


def test_frequency_uncertainty_accepts_facility_event_family_annotations():
    events = _valve_events()
    payload = _result(events)
    for event in payload['events']:
        event['scenario_families'] = ['valve_hole', 'liquid_two_phase']
    result = literature_frequency_uncertainty(
        payload,
        (LiteratureFrequencyScenario(
            id='annotated-central',
            asset_quantiles={'valves': 'published'},
            provenance='facility ledger metadata is ignored by frequency parser',
        ),),
    )
    assert result['scenarios'][0]['event_frequency_per_year'][events[0].id] == events[0].annual_frequency_per_year


def test_p05_requires_a_published_event_bound():
    events = _valve_events()
    event = events[0].model_copy(update={'marginal_p05_per_year': None})
    with pytest.raises(ValueError, match='both p05 and p95'):
        literature_frequency_uncertainty(_result((event,)), (
            LiteratureFrequencyScenario(id='low', asset_quantiles={'valves': 'p05'}, provenance='test'),
        ))


def test_fixed_quantile_keeps_catalogue_rate_when_no_bounds_exist():
    events = _valve_events()
    event = events[0].model_copy(update={
        'marginal_p05_per_year': None,
        'marginal_p95_per_year': None,
        'frequency_distribution': 'none',
        'log_rate_mu': None,
        'log_rate_sigma': None,
    })
    result = literature_frequency_uncertainty(_result((event,)), (
        LiteratureFrequencyScenario(
            id='mixed-catalogue-fixed',
            asset_quantiles={'valves': 'fixed'},
            provenance='catalogue median held fixed because no published bounds exist',
        ),
    ))
    assert result['scenarios'][0]['event_frequency_per_year'][event.id] == event.annual_frequency_per_year


def test_independent_event_bounds_can_be_compared_with_shared_asset_bounds():
    events = _valve_events()
    independent = LiteratureFrequencyScenario(
        id='independent-low',
        event_quantiles={event.id: 'p05' for event in events},
        provenance='published test bounds; independent event sensitivity',
        correlation_assumption='independent_event_bounds',
    )
    shared = LiteratureFrequencyScenario(
        id='shared-low',
        asset_quantiles={'valves': 'p05'},
        provenance='published test bounds; within-asset shared sensitivity',
    )
    result = literature_frequency_uncertainty(_result(events), (shared, independent))
    assert result['correlation_comparison_present'] is True
    assert all(
        scenario['event_frequency_per_year'][event.id] == event.marginal_p05_per_year
        for scenario in result['scenarios']
        for event in events
    )


def test_frequency_scenario_rejects_mixed_correlation_inputs():
    with pytest.raises(ValueError, match='asset quantiles only'):
        LiteratureFrequencyScenario(
            id='mixed',
            asset_quantiles={'valves': 'p05'},
            event_quantiles={'event': 'p95'},
            provenance='test',
        )


def test_published_frequency_distribution_sampling_returns_known_interval_without_physics():
    events = _lh2_events()
    payload = _result(events)
    for atom in payload['risk_atoms']:
        atom['scenario_families'] = ['valve_hole', 'liquid_two_phase']
    result = sample_literature_frequency_distributions(
        payload,
        (
            LiteratureFrequencyDistributionScenario(
                id='shared', provenance='published test mu/sigma',
                correlation_assumption='within_asset_shared_normal',
            ),
            LiteratureFrequencyDistributionScenario(
                id='independent', provenance='published test mu/sigma',
                correlation_assumption='independent_event_normal',
            ),
        ),
        draws=100,
        seed=7,
    )
    assert result['fresh_physics_executed'] is False
    assert result['frequency_distribution_credible_interval'] is True
    assert result['provider_packet_promoted'] is False
    assert result['complete_facility_qra_claim'] is False
    assert len(result['scenarios'][0]['known_expected_death_quantiles'][0]) == 3
    assert result['scenarios'][0]['event_frequency_quantiles_per_year'][events[0].id][1] > 0
    stability = result['scenarios'][0]['asset_rank_stability'][events[0].asset_id]
    assert stability['mean_rank_low_high'] == pytest.approx([1.0, 1.0])
    assert stability['top_rank_probability_low_high'] == pytest.approx([1.0, 1.0])
    family_stability = result['scenarios'][0]['scenario_family_rank_stability']
    assert set(family_stability) == {'valve_hole', 'liquid_two_phase'}


def test_frequency_uncertainty_preserves_upstream_physical_validation_claim():
    events = _valve_events()
    payload = _result(events)
    payload['physical_validation_claim'] = True
    result = literature_frequency_uncertainty(
        payload,
        (LiteratureFrequencyScenario(
            id='validated-central',
            asset_quantiles={'valves': 'published'},
            provenance='validated test input',
        ),),
    )
    assert result['physical_validation_claim'] is True
    assert result['scenarios'][0]['physical_validation_claim'] is True


def test_distribution_sampling_can_hold_mixed_catalogue_events_fixed():
    events = _valve_events()
    fixed = events[0].model_copy(update={
        'frequency_distribution': 'none',
        'log_rate_mu': None,
        'log_rate_sigma': None,
    })
    result = sample_literature_frequency_distributions(
        _result((fixed,)),
        (LiteratureFrequencyDistributionScenario(
            id='mixed-fixed',
            provenance='published distribution plus fixed catalogue rate',
            correlation_assumption='within_asset_shared_normal',
            fixed_event_policy='hold_published',
        ),),
        draws=100,
        seed=7,
    )
    row = result['scenarios'][0]
    assert row['scenario']['fixed_event_policy'] == 'hold_published'
    assert row['event_frequency_quantiles_per_year'][fixed.id] == pytest.approx(
        [fixed.annual_frequency_per_year] * 3
    )
    assert result['frequency_distribution_credible_interval'] is True


def test_distribution_sampling_rejects_events_without_published_mu_sigma():
    events = generate_events(
        Facility.model_validate_json(open('examples/consequence_facility.json', encoding='utf-8').read()),
        FrequencyPlan.model_validate_json(json.dumps({
            'id': 'no-distribution',
            'assets': [{
                'id': 'storage', 'model_component_id': 'storage', 'profile': 'TNO_PRESSURE_VESSEL',
                'physical_scope_ids': ['storage-1'], 'classification_basis': 'test-only reviewed category',
                'vessel_external_impact_or_operating_error': False,
            }],
            'excluded_model_components': {
                x['id']: 'test scope excludes other components'
                for x in json.loads(open('examples/consequence_facility.json', encoding='utf-8').read())['components']
                if x['id'] != 'storage'
            },
        }))
    )
    with pytest.raises(ValueError, match='no published lognormal'):
        sample_literature_frequency_distributions(
            _result(events),
            (LiteratureFrequencyDistributionScenario(
                id='shared', provenance='test',
                correlation_assumption='within_asset_shared_normal',
            ),),
            draws=100,
        )
