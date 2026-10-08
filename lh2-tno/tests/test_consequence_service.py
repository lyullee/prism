import json
from pathlib import Path
from lh2_tno.backend import BackendConfig,PackagePin,tree_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.service import (ConsequenceService, RealtimeConsequenceMonitor,
    request_from_equipment_resolver, request_from_telemetry,
    validate_equipment_process_state)
from lh2_tno.telemetry import Frame,TagMapping,TelemetryNormalizer,Value
from test_consequences import EXAMPLE
from test_provider_release import _defaults, _release
import pytest


class Pipeline:
    def __init__(self,tmp_path):
        (tmp_path/'model.py').write_text('a=1')
        self.config=BackendConfig(interpreter='unused',packages=(PackagePin(name='test',root=str(tmp_path),sha256=tree_digest(tmp_path)),))
        self.backend=self
        self.facility=self
        self.calls=0
    def digest(self):return 'facility'
    def consequences(self,request):
        self.calls+=1
        return {'data':{
                'pressure': None if request.source_input is None else request.source_input['tank']['pressure_pa'],
                'provider_event': None if request.resolved_release is None else request.resolved_release.event_id,
            },'elapsed_ms':100.,
            'adapter_source_digest':tree_digest(Path(__file__).parents[1]/'src/lh2_tno')}


def request():return ConsequenceRequest.model_validate_json(EXAMPLE.read_text(encoding='utf-8'))


def test_sensor_state_change_cannot_reuse_old_physics(tmp_path):
    pipeline=Pipeline(tmp_path);service=ConsequenceService(pipeline,capacity=1)
    a=request()
    service.evaluate(a)
    cached=service.evaluate(a)
    assert pipeline.calls==1 and cached['service']['exact_cache_hit']
    cached['data']['pressure']=-999.
    assert service.evaluate(a)['data']['pressure']==600000.
    normalized={'values':{'PT':{'quantity':'pressure','component_id':'storage','value_si':500000.},
        'TT':{'quantity':'temperature','component_id':'storage','value_si':20.893}}}
    b=request_from_telemetry(a,normalized,pressure_tag='PT',temperature_tag='TT')
    fresh=service.evaluate(b)
    assert pipeline.calls==2 and fresh['data']['pressure']==500000.
    assert not fresh['service']['exact_cache_hit']
    service.evaluate(a)
    assert pipeline.calls==3  # cache capacity eviction


def test_changed_backend_code_cannot_return_cached_result(tmp_path):
    pipeline=Pipeline(tmp_path);service=ConsequenceService(pipeline)
    service.evaluate(request())
    (tmp_path/'model.py').write_text('a=2')
    with pytest.raises(RuntimeError,match='revision mismatch'):service.evaluate(request())


def test_pressure_from_other_component_is_not_used_as_tank_state():
    normalized={'values':{'PT':{'quantity':'pressure','component_id':'vent','value_si':500000.},
        'TT':{'quantity':'temperature','component_id':'storage','value_si':20.893}}}
    with pytest.raises(ValueError):request_from_telemetry(request(),normalized,pressure_tag='PT',temperature_tag='TT')


def test_equipment_resolver_supplies_provider_boundary_without_frequency_or_source_inference():
    template = request().model_copy(update={"component_id": "storage-tank-01"})
    normalized={'values':{'PT':{'quantity':'pressure','component_id':'storage-tank-01','value_si':500000.},
        'TT':{'quantity':'temperature','component_id':'storage-tank-01','value_si':20.893}}}
    provider_request = __import__('lh2_tno.provider_release', fromlist=['build_consequence_request_from_provider_release']).build_consequence_request_from_provider_release(
        _release(), _defaults()
    )
    resolved = request_from_equipment_resolver(template, normalized, lambda _template, _state: provider_request)
    assert resolved.source_input is None
    assert resolved.resolved_release is not None
    assert resolved.annual_frequency_per_year is None


def test_process_state_contract_accepts_state_values_and_returns_isolated_copy():
    original = {
        'values': {
            'PT': {'quantity': 'pressure', 'component_id': 'storage',
                   'value_si': 500000.0, 'sensor_location': 'vapour'},
            'LVL': {'quantity': 'level_fraction', 'component_id': 'storage',
                    'value_si': 0.4, 'sensor_location': 'tank'},
        },
        'origin': 'model_prediction',
        'phase': {'vapour_fraction': 0.2},
    }
    snapshot = validate_equipment_process_state(original)
    snapshot['values']['PT']['value_si'] = 1.0
    assert original['values']['PT']['value_si'] == 500000.0
    assert snapshot['values']['LVL']['value_si'] == 0.4


@pytest.mark.parametrize('field', [
    'annual_frequency_per_year', 'failure_opening_diameter_m',
    'resolved_release', 'duration_s', 'steps', 'event_kind',
])
def test_process_state_contract_rejects_accident_owned_fields(field):
    state = {'values': {'PT': {'quantity': 'pressure', 'component_id': 'storage',
                               'value_si': 500000.0}}, field: 1}
    with pytest.raises(ValueError, match='accident-owned field'):
        validate_equipment_process_state(state)


def test_equipment_resolver_receives_state_only_snapshot():
    seen = {}
    normalized = {'values': {'PT': {'quantity': 'pressure', 'component_id': 'storage',
                                    'value_si': 500000.0}}}
    provider_request = __import__('lh2_tno.provider_release', fromlist=['build_consequence_request_from_provider_release']).build_consequence_request_from_provider_release(
        _release(), _defaults()
    )

    def resolver(_template, state):
        seen['state'] = state
        state['values']['PT']['value_si'] = -1.0
        return provider_request

    request_from_equipment_resolver(request().model_copy(update={'component_id': 'storage-tank-01'}), normalized, resolver)
    assert 'annual_frequency_per_year' not in seen['state']
    assert normalized['values']['PT']['value_si'] == 500000.0


def test_service_marks_provider_resolved_telemetry_update(tmp_path):
    pipeline = Pipeline(tmp_path)
    service = ConsequenceService(pipeline)
    template = request().model_copy(update={"component_id": "storage-tank-01"})
    normalized={'values':{'PT':{'quantity':'pressure','component_id':'storage-tank-01','value_si':500000.},
        'TT':{'quantity':'temperature','component_id':'storage-tank-01','value_si':20.893},
    }, 'origin':'synthetic', 'independent_measurement_claim':False, 'data_age_s':0.1,
        'frame_digest':'frame', 'mapping_digest':'mapping'}
    provider_request = __import__('lh2_tno.provider_release', fromlist=['build_consequence_request_from_provider_release']).build_consequence_request_from_provider_release(
        _release(), _defaults()
    )
    result = service.update_from_telemetry(
        template, normalized, pressure_tag='PT', temperature_tag='TT',
        release_resolver=lambda _template, _state: provider_request,
    )
    assert result['data']['provider_event'] == 'provider-accident-01'
    assert result['telemetry_boundary']['equipment_release_resolved'] is True


@pytest.mark.parametrize('bad', [lambda template, state: template, lambda template, state: _defaults()])
def test_equipment_resolver_rejects_unresolved_or_non_request_output(bad):
    with pytest.raises((TypeError, ValueError)):
        request_from_equipment_resolver(request(), {'values': {}}, bad)


def test_realtime_monitor_records_deadline_and_keeps_frequency_inference_off(tmp_path):
    pipeline = Pipeline(tmp_path)
    monitor = RealtimeConsequenceMonitor(ConsequenceService(pipeline), period_s=1.0)
    normalizer = TelemetryNormalizer((
        TagMapping(tag='P', component_id='storage', quantity='pressure', source_unit='Pa',
                   pressure_basis='absolute', sensor_location='tank-vapour'),
        TagMapping(tag='T', component_id='storage', quantity='temperature', source_unit='K',
                   sensor_location='tank-vapour'),
    ), maximum_age_s=2.0)
    frame = Frame(
        stream_id='monitor', sequence=1, source_time_s=100.0, arrival_time_s=100.1,
        origin='synthetic',
        values={'P': Value(value=600000., unit='Pa', quality='valid'),
                'T': Value(value=20.893, unit='K', quality='valid')},
    )
    result = monitor.update_from_frame(
        request(), normalizer, frame, now_s=100.2, pressure_tag='P', temperature_tag='T'
    )
    assert result['realtime']['deadline_status'] == 'MET'
    assert result['realtime']['frequency_learning'] is False
    assert result['realtime']['release_inference'] is False
    assert result['service']['fresh_physics_this_update'] is True


def test_realtime_monitor_reports_deadline_miss_without_stale_substitution(tmp_path):
    pipeline = Pipeline(tmp_path)
    monitor = RealtimeConsequenceMonitor(ConsequenceService(pipeline), period_s=1.0, deadline_s=1e-12)
    normalizer = TelemetryNormalizer((
        TagMapping(tag='P', component_id='storage', quantity='pressure', source_unit='Pa',
                   pressure_basis='absolute', sensor_location='tank-vapour'),
        TagMapping(tag='T', component_id='storage', quantity='temperature', source_unit='K',
                   sensor_location='tank-vapour'),
    ), maximum_age_s=2.0)
    frame = Frame(
        stream_id='monitor', sequence=1, source_time_s=100.0, arrival_time_s=100.1,
        origin='synthetic',
        values={'P': Value(value=600000., unit='Pa', quality='valid'),
                'T': Value(value=20.893, unit='K', quality='valid')},
    )
    result = monitor.update_from_frame(
        request(), normalizer, frame, now_s=100.2, pressure_tag='P', temperature_tag='T'
    )
    assert result['realtime']['deadline_status'] == 'MISSED'
    assert result['realtime']['exact_cache_hit'] is False
    assert result['realtime']['interpretation'].startswith('deadline ledger only')
