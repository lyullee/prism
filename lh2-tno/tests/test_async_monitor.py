from types import SimpleNamespace
import threading
import time

import pytest

import lh2_tno.async_monitor as async_module
import lh2_tno.service as service_module
from lh2_tno.async_monitor import AsyncRuntimeConsequenceMonitor
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames
from lh2_tno.provider_release import build_consequence_request_from_provider_release
from lh2_tno.service import ConsequenceService, RealtimeConsequenceMonitor
from test_consequence_service import Pipeline, request
from test_observed_state_runtime import _source
from test_provider_release import _defaults, _release


def frame(captured):
    source = _source()
    source['samples'] = [dict(source['samples'][-1], captured_at_s=captured)]
    return build_observed_state_runtime_frames([source])['frames'][0]


def provider_request():
    defaults = _defaults()
    defaults['component_id'] = 'tank-01'
    return build_consequence_request_from_provider_release(
        _release().model_copy(update={'component_id': 'tank-01'}), defaults,
    )


def monitor(tmp_path, resolver, *, max_age=60, deadline=1):
    sync = RealtimeConsequenceMonitor(ConsequenceService(Pipeline(tmp_path)), deadline_s=deadline)
    return AsyncRuntimeConsequenceMonitor(
        sync, request().model_copy(update={'component_id': 'tank-01'}),
        release_resolver=resolver, scenario_id='tank-shell-leak',
        source_id='historian-tank-01', maximum_age_s=max_age,
    )


def wait_completion(queue, job_id):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        snapshot = queue.poll()
        if (snapshot['completion'] or {}).get('job_id') == job_id:
            return snapshot
        time.sleep(0.002)
    pytest.fail(f'job {job_id} did not complete: {queue.poll()}')


def test_queued_states_coalesce_and_old_running_result_never_becomes_current(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def resolver(_template, state):
        calls.append(state['captured_at_s'])
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return provider_request()

    with monitor(tmp_path, resolver) as queue:
        try:
            queue.submit(frame(1), now_s=1)
            assert entered.wait(3)
            second = queue.submit(frame(2), now_s=2)
            third_frame = frame(3)
            third = queue.submit(third_frame, now_s=3)
            assert third['superseded_job_id'] == second['job_id']
            assert queue.poll()['result'] is None
            assert queue.poll()['pending_job_id'] == third['job_id']
            release.set()
            result = wait_completion(queue, third['job_id'])
            assert calls == [1, 3]
            assert result['status'] == 'READY'
            assert result['superseded_pending_count'] == 1
            assert result['superseded_running_count'] == 1
            assert result['result']['telemetry_boundary']['state_snapshot_digest'] == third_frame['state_snapshot_digest']
            result['result']['data']['provider_event'] = 'tampered'
            assert queue.poll()['result']['data']['provider_event'] != 'tampered'
        finally:
            release.set()


def test_failed_new_update_cannot_publish_previous_success(tmp_path):
    def resolver(_template, state):
        if state['captured_at_s'] == 2:
            raise ValueError('provider inventory unavailable')
        return provider_request()

    with monitor(tmp_path, resolver) as queue:
        first = queue.submit(frame(1), now_s=1)
        assert wait_completion(queue, first['job_id'])['result'] is not None
        second = queue.submit(frame(2), now_s=2)
        output = wait_completion(queue, second['job_id'])
        assert output['status'] == 'FAILED'
        assert output['result'] is None
        assert output['completion']['error']['message'] == 'provider inventory unavailable'


def test_stream_identity_order_digest_and_age_are_checked_before_queueing(tmp_path):
    with monitor(tmp_path, lambda *_: provider_request(), max_age=10) as queue:
        receipt = queue.submit(frame(1), now_s=1)
        wait_completion(queue, receipt['job_id'])
        with pytest.raises(ValueError, match='increasing'):
            queue.submit(frame(1), now_s=1)
        other = _source()
        other['source_id'] = 'another-stream'
        with pytest.raises(ValueError, match='configured stream'):
            queue.submit(build_observed_state_runtime_frames([other])['frames'][0], now_s=1)
        invalid = frame(2)
        invalid['values']['pressure']['value_si'] = 1
        with pytest.raises(ValueError, match='frame_digest'):
            queue.submit(invalid, now_s=2)
        with pytest.raises(ValueError, match='maximum_age_s'):
            queue.submit(frame(2), now_s=13)
        assert queue.poll()['latest_job_id'] == receipt['job_id']


@pytest.mark.parametrize('max_age, expected', [(1, 'EXPIRED_BEFORE_EXECUTION'), (10, 'READY_LATE')])
def test_queue_wait_counts_for_age_and_deadline(tmp_path, monkeypatch, max_age, expected):
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(async_module, 'time', SimpleNamespace(perf_counter=lambda: clock.value))
    entered, release = threading.Event(), threading.Event()
    calls = []

    def resolver(_template, state):
        calls.append(state['captured_at_s'])
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return provider_request()

    with monitor(tmp_path, resolver, max_age=max_age) as queue:
        try:
            queue.submit(frame(1), now_s=1)
            assert entered.wait(3)
            receipt = queue.submit(frame(2), now_s=2)
            clock.value = 2.0
            release.set()
            output = wait_completion(queue, receipt['job_id'])
            assert output['status'] == expected
            assert output['completion']['queue_elapsed_s'] == 2
            assert output['completion']['deadline_met'] is False
            if max_age == 1:
                assert calls == [1]
                assert output['result'] is None
            else:
                assert calls == [1, 2]
                assert output['result']['telemetry_boundary']['data_age_at_output_s'] >= 2
                assert output['result']['realtime']['deadline_status'] == 'MISSED'
                assert output['result']['realtime']['mode_contract']['reported_mode'] == 'deadline_missed'
        finally:
            release.set()


def test_completed_result_expires_at_poll_without_new_input(tmp_path, monkeypatch):
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(async_module, 'time', SimpleNamespace(perf_counter=lambda: clock.value))
    with monitor(tmp_path, lambda *_: provider_request(), max_age=1) as queue:
        receipt = queue.submit(frame(1), now_s=1)
        assert wait_completion(queue, receipt['job_id'])['status'] == 'READY'
        clock.value = 2.0
        assert queue.poll()['status'] == 'EXPIRED_AFTER_EXECUTION'
        assert queue.poll()['result'] is None


def test_state_expiring_during_physics_never_publishes_a_numeric_result(tmp_path, monkeypatch):
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(async_module, 'time', SimpleNamespace(perf_counter=lambda: clock.value))

    def resolver(*_):
        clock.value = 2.0
        return provider_request()

    with monitor(tmp_path, resolver, max_age=1) as queue:
        receipt = queue.submit(frame(1), now_s=1)
        output = wait_completion(queue, receipt['job_id'])
        assert output['status'] == 'EXPIRED_AFTER_EXECUTION'
        assert output['result'] is None
        assert output['completion']['data_age_at_completion_s'] == 2.0


def test_shutdown_cancels_pending_and_rejects_submission(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def resolver(_template, state):
        calls.append(state['captured_at_s'])
        entered.set()
        assert release.wait(3)
        return provider_request()

    queue = monitor(tmp_path, resolver)
    try:
        queue.submit(frame(1), now_s=1)
        assert entered.wait(3)
        receipt = queue.submit(frame(2), now_s=2)
        closure = queue.close(wait=False)
        assert closure['cancelled_pending_job_id'] == receipt['job_id']
        with pytest.raises(RuntimeError, match='closed'):
            queue.submit(frame(3), now_s=3)
        release.set()
        queue.close()
        assert calls == [1]
        assert queue.poll()['status'] == 'CLOSED'
        assert queue.poll()['result'] is None
    finally:
        release.set()
        queue.close()


def test_full_update_deadline_includes_provider_resolution_on_runtime_frames(tmp_path, monkeypatch):
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(service_module, 'time', SimpleNamespace(perf_counter=lambda: clock.value))

    def resolver(*_):
        clock.value += 2.0
        return provider_request()

    sync = RealtimeConsequenceMonitor(ConsequenceService(Pipeline(tmp_path)))
    output = sync.update_from_runtime_frame(
        request().model_copy(update={'component_id': 'tank-01'}), frame(1),
        now_s=1.5, release_resolver=resolver,
    )
    assert output['service']['service_elapsed_ms'] == 0.0
    assert output['service']['state_resolution_elapsed_ms'] == 2000.0
    assert output['realtime']['update_elapsed_s'] == 2.0
    assert output['realtime']['deadline_status'] == 'MISSED'
    assert output['realtime']['mode_contract']['reported_mode'] == 'deadline_missed'
    assert output['telemetry_boundary']['data_age_at_output_s'] == 2.5


def test_full_update_deadline_includes_historian_normalization(tmp_path, monkeypatch):
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(service_module, 'time', SimpleNamespace(perf_counter=lambda: clock.value))

    class Normalizer:
        def normalize(self, *_args, **_kwargs):
            clock.value += 1.5
            return dict(values={
                'P': dict(quantity='pressure', component_id='storage', value_si=600000.),
                'T': dict(quantity='temperature', component_id='storage', value_si=20.893),
            }, origin='synthetic', data_age_s=0.2, frame_digest='test',
                mapping_digest='test', independent_measurement_claim=False)

    sync = RealtimeConsequenceMonitor(ConsequenceService(Pipeline(tmp_path)))
    output = sync.update_from_frame(
        request(), Normalizer(), SimpleNamespace(source_time_s=1, stream_id='stream'),
        now_s=1.2, pressure_tag='P', temperature_tag='T',
    )
    assert output['realtime']['deadline_status'] == 'MISSED'
    assert output['realtime']['normalization_elapsed_s'] == 1.5
    assert output['telemetry_boundary']['data_age_at_output_s'] == 1.7
