import json
from pathlib import Path
from lh2_tno.backend import BackendConfig,PackagePin,tree_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.service import (ConsequenceService, FacilityRealtimeBinding,
    FacilityRealtimeConsequenceMonitor, RealtimeConsequenceMonitor,
    RealtimeFrequencyBinding,
    RealtimePopulationBinding,
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


class RiskPipeline(Pipeline):
    def consequences(self, request):
        result = super().consequences(request)
        result['data']['receptors'] = [{
            'id': 'worker-01',
            'harm_given_observed_release_low_high': [0.2, 0.4],
        }]
        return result


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


def _facility_binding(tmp_path, component_id, *, deadline_s=1.0, stream_id=None):
    template = request().model_copy(update={"component_id": component_id})
    normalizer = TelemetryNormalizer((
        TagMapping(tag='P', component_id=component_id, quantity='pressure', source_unit='Pa',
                   pressure_basis='absolute', sensor_location='tank-vapour'),
        TagMapping(tag='T', component_id=component_id, quantity='temperature', source_unit='K',
                   sensor_location='tank-vapour'),
    ), maximum_age_s=2.0)
    frame = Frame(
        stream_id=stream_id or f'{component_id}-stream', sequence=1,
        source_time_s=100.0, arrival_time_s=100.1, origin='synthetic',
        values={'P': Value(value=600000., unit='Pa', quality='valid'),
                'T': Value(value=20.893, unit='K', quality='valid')},
    )
    monitor = RealtimeConsequenceMonitor(
        ConsequenceService(Pipeline(tmp_path)), period_s=1.0, deadline_s=deadline_s
    )
    return FacilityRealtimeBinding(
        component_id=component_id, template=template, monitor=monitor,
        normalizer=normalizer, pressure_tag='P', temperature_tag='T'
    ), frame


def test_facility_realtime_monitor_aggregates_component_provenance_and_deadlines(tmp_path):
    first, first_frame = _facility_binding(tmp_path, 'storage-tank-01')
    second, second_frame = _facility_binding(tmp_path, 'transfer-pump-01')
    facility = FacilityRealtimeConsequenceMonitor({
        'storage-tank-01': first, 'transfer-pump-01': second,
    }, facility_id='generic-outdoor-lh2')
    result = facility.update_from_frames({
        'storage-tank-01': first_frame, 'transfer-pump-01': second_frame,
    }, now_s=100.2)
    assert result['status'] == 'ACCEPTED'
    assert result['component_count'] == 2
    assert result['accepted_component_count'] == 2
    assert result['aggregate']['deadline_status'] == 'MET'
    assert result['aggregate']['fresh_physics_count'] == 2
    assert result['aggregate']['facility_annual_risk_available'] is False
    assert result['aggregate']['current_weather_ir_available'] is False
    ranking = result['aggregate']['component_risk_ranking']
    assert ranking['status'] == 'WITHHELD_CURRENT_WEATHER_COMPONENT_RANKING'
    assert ranking['component_count'] == 2
    assert ranking['available_component_count'] == 0
    assert all(row['peak_annual_ir_low_high'] == [None, None] for row in ranking['rows'])
    assert ranking['stale_or_zero_fallback_used'] is False
    assert result['components']['storage-tank-01']['frame_digest']
    assert result['components']['transfer-pump-01']['mapping_digest']


def test_facility_realtime_monitor_rejects_partial_batch_without_stale_or_zero_fallback(tmp_path):
    first, first_frame = _facility_binding(tmp_path, 'storage-tank-01')
    second, _ = _facility_binding(tmp_path, 'transfer-pump-01')
    facility = FacilityRealtimeConsequenceMonitor({
        'storage-tank-01': first, 'transfer-pump-01': second,
    })
    result = facility.update_from_frames({'storage-tank-01': first_frame}, now_s=100.2)
    assert result['status'] == 'REJECTED'
    assert result['aggregate']['deadline_status'] == 'REJECTED'
    assert result['components']['transfer-pump-01']['error_type'] == 'MissingFrame'
    assert result['aggregate']['facility_annual_risk_available'] is False
    ranking = result['aggregate']['component_risk_ranking']
    assert ranking['status'] == 'WITHHELD_CURRENT_WEATHER_COMPONENT_RANKING'
    missing = next(row for row in ranking['rows'] if row['component_id'] == 'transfer-pump-01')
    assert missing['peak_annual_ir_low_high'] == [None, None]
    assert missing['rank'] is None
    assert 'result' not in result['components']['transfer-pump-01']


def test_facility_realtime_monitor_rejects_duplicate_stream_and_unknown_component(tmp_path):
    first, first_frame = _facility_binding(tmp_path, 'storage-tank-01', stream_id='shared')
    second, second_frame = _facility_binding(tmp_path, 'transfer-pump-01', stream_id='shared')
    facility = FacilityRealtimeConsequenceMonitor({
        'storage-tank-01': first, 'transfer-pump-01': second,
    })
    _, unknown_frame = _facility_binding(tmp_path, 'unexpected')
    result = facility.update_from_frames({
        'storage-tank-01': first_frame, 'transfer-pump-01': second_frame,
        'unexpected': unknown_frame,  # an extra frame cannot be ignored
    }, now_s=100.2)
    assert result['status'] == 'REJECTED'
    assert result['unknown_frame_components'] == ['unexpected']
    assert result['duplicate_streams']['shared'] == ['storage-tank-01', 'transfer-pump-01']
    assert result['components']['storage-tank-01']['error_type'] == 'DuplicateFrameStream'


def test_realtime_monitor_uses_explicit_literature_frequency_for_current_weather_ir(tmp_path):
    base_binding, frame = _facility_binding(tmp_path, 'storage-tank-01')
    binding = FacilityRealtimeBinding(
        component_id=base_binding.component_id,
        template=base_binding.template,
        monitor=RealtimeConsequenceMonitor(
            ConsequenceService(RiskPipeline(tmp_path)), period_s=1.0
        ),
        normalizer=base_binding.normalizer,
        pressure_tag=base_binding.pressure_tag,
        temperature_tag=base_binding.temperature_tag,
        frequency_binding=RealtimeFrequencyBinding(
            event_id='storage-tank-hole-01',
            asset_id='storage-tank-01',
            initiating_frequency_per_year=1.0e-3,
            annual_condition_probability=0.5,
            release_branch_probability=0.8,
            occupancy_probability=0.25,
            provenance='published LH2 vessel frequency median',
            source_digest='a' * 64,
            frequency_p05_per_year=5.0e-4,
            frequency_p95_per_year=2.0e-3,
        ),
    )
    facility = FacilityRealtimeConsequenceMonitor({'storage-tank-01': binding})
    result = facility.update_from_frames({'storage-tank-01': frame}, now_s=100.2)

    assert result['status'] == 'ACCEPTED'
    assert result['components']['storage-tank-01']['risk']['status'] == 'AVAILABLE_CURRENT_WEATHER_IR'
    assert result['aggregate']['current_weather_ir_available'] is True
    assert result['aggregate']['current_weather_annual_ir_low_high']['worker-01'] == pytest.approx(
        [2.0e-5, 4.0e-5]
    )
    assert result['aggregate']['current_weather_frequency_sensitivity_available'] is True
    assert result['aggregate']['current_weather_frequency_sensitivity_ir_low_high']['p05']['worker-01'] == pytest.approx(
        [1.0e-5, 2.0e-5]
    )
    assert result['aggregate']['current_weather_frequency_sensitivity_ir_low_high']['p95']['worker-01'] == pytest.approx(
        [4.0e-5, 8.0e-5]
    )
    ranking = result['aggregate']['component_risk_ranking']
    assert ranking['status'] == 'AVAILABLE_CURRENT_WEATHER_COMPONENT_RANKING'
    assert ranking['available_component_count'] == 1
    assert ranking['rows'][0]['component_id'] == 'storage-tank-01'
    assert ranking['rows'][0]['rank'] == 1
    assert ranking['rows'][0]['peak_annual_ir_low_high'] == pytest.approx(
        [2.0e-5, 4.0e-5]
    )
    assert ranking['frequency_reallocation_performed'] is False
    assert ranking['facility_ir_fn_promotion'] is False
    assert result['aggregate']['facility_annual_risk_available'] is False
    assert result['aggregate']['facility_fn_available'] is False
    assert result['aggregate']['frequency_learning'] is False


def test_realtime_monitor_calculates_conditional_expected_death_fn_from_explicit_population(tmp_path):
    base_binding, frame = _facility_binding(tmp_path, 'storage-tank-01')
    binding = FacilityRealtimeBinding(
        component_id=base_binding.component_id,
        template=base_binding.template,
        monitor=RealtimeConsequenceMonitor(
            ConsequenceService(RiskPipeline(tmp_path)), period_s=1.0
        ),
        normalizer=base_binding.normalizer,
        pressure_tag=base_binding.pressure_tag,
        temperature_tag=base_binding.temperature_tag,
        frequency_binding=RealtimeFrequencyBinding(
            event_id='storage-tank-hole-01',
            asset_id='storage-tank-01',
            initiating_frequency_per_year=1.0e-3,
            annual_condition_probability=0.5,
            release_branch_probability=0.8,
            occupancy_probability=0.25,
            provenance='published LH2 vessel frequency median',
            source_digest='d' * 64,
            frequency_p05_per_year=5.0e-4,
            frequency_p95_per_year=2.0e-3,
        ),
    )
    population = RealtimePopulationBinding(
        persons_by_receptor={'worker-01': 10.0},
        provenance='declared outdoor worker population snapshot',
        source_digest='e' * 64,
    )
    facility = FacilityRealtimeConsequenceMonitor(
        {'storage-tank-01': binding}, population_binding=population
    )
    result = facility.update_from_frames({'storage-tank-01': frame}, now_s=100.2)

    aggregate = result['aggregate']
    assert aggregate['conditional_current_weather_expected_death_fn_available'] is True
    assert aggregate['conditional_current_weather_expected_death_fn_low_high'] == pytest.approx(
        [2.0e-4, 4.0e-4]
    )
    sensitivity = aggregate[
        'conditional_current_weather_expected_death_fn'
    ]['frequency_sensitivity_expected_death_fn_low_high']
    assert sensitivity['p05'] == pytest.approx([1.0e-4, 2.0e-4])
    assert sensitivity['p95'] == pytest.approx([4.0e-4, 8.0e-4])
    assert aggregate['facility_fn_available'] is False
    assert aggregate['facility_annual_risk_available'] is False
    assert aggregate['frequency_learning'] is False


def test_realtime_population_binding_rejects_invalid_population_source_digest():
    with pytest.raises(ValueError, match='64-character SHA-256'):
        RealtimePopulationBinding(
            persons_by_receptor={'worker-01': 1.0},
            provenance='declared population',
            source_digest='short',
        )


def test_realtime_frequency_binding_rejects_non_sha256_source():
    with pytest.raises(ValueError, match='64-character SHA-256'):
        RealtimeFrequencyBinding(
            event_id='e', asset_id='a', initiating_frequency_per_year=1.0e-3,
            annual_condition_probability=1.0, release_branch_probability=1.0,
            occupancy_probability=1.0, provenance='literature', source_digest='short',
        )


def test_realtime_monitor_rejects_duplicate_frequency_event_bindings(tmp_path):
    first, _ = _facility_binding(tmp_path, 'storage-tank-01')
    second, _ = _facility_binding(tmp_path, 'transfer-pump-01')
    frequency = RealtimeFrequencyBinding(
        event_id='duplicate-event', asset_id='asset-1',
        initiating_frequency_per_year=1.0e-3,
        annual_condition_probability=1.0, release_branch_probability=1.0,
        occupancy_probability=1.0, provenance='literature', source_digest='b' * 64,
    )
    first = FacilityRealtimeBinding(
        component_id=first.component_id, template=first.template, monitor=first.monitor,
        normalizer=first.normalizer, pressure_tag=first.pressure_tag,
        temperature_tag=first.temperature_tag, frequency_binding=frequency,
    )
    second = FacilityRealtimeBinding(
        component_id=second.component_id, template=second.template, monitor=second.monitor,
        normalizer=second.normalizer, pressure_tag=second.pressure_tag,
        temperature_tag=second.temperature_tag, frequency_binding=frequency,
    )
    with pytest.raises(ValueError, match='one literature event'):
        FacilityRealtimeConsequenceMonitor({
            'storage-tank-01': first, 'transfer-pump-01': second,
        })


def test_facility_realtime_monitor_requires_unique_declared_component_identity(tmp_path):
    binding, _ = _facility_binding(tmp_path, 'storage-tank-01')
    with pytest.raises(ValueError, match='binding key'):
        FacilityRealtimeConsequenceMonitor({'wrong-key': binding})
