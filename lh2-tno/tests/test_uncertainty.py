import json

import pytest

from lh2_tno.contracts import Facility
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.uncertainty import LiteratureFrequencyScenario, literature_frequency_uncertainty


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


def test_published_literature_quantiles_reweight_atoms_without_physics():
    events = _valve_events()
    result = literature_frequency_uncertainty(_result(events), (
        LiteratureFrequencyScenario(id='low', asset_quantiles={'valves': 'p05'}, provenance='published test bounds'),
        LiteratureFrequencyScenario(id='high', asset_quantiles={'valves': 'p95'}, provenance='published test bounds'),
    ))
    assert result['fresh_physics_executed'] is False
    low, high = result['scenarios']
    assert low['event_frequency_per_year'][events[0].id] == events[0].marginal_p05_per_year
    assert high['event_frequency_per_year'][events[0].id] == events[0].marginal_p95_per_year
    assert result['facility_credible_interval'] is False


def test_p05_requires_a_published_event_bound():
    events = _valve_events()
    event = events[0].model_copy(update={'marginal_p05_per_year': None})
    with pytest.raises(ValueError, match='both p05 and p95'):
        literature_frequency_uncertainty(_result((event,)), (
            LiteratureFrequencyScenario(id='low', asset_quantiles={'valves': 'p05'}, provenance='test'),
        ))
