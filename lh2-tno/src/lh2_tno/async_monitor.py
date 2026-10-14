"""Bounded background reevaluation of one declared equipment/scenario stream.

The queue accepts state frames, never infers scenarios or frequencies, and
keeps one executing update plus at most one pending update. Each instance is
dedicated to a scenario selected upstream (for example by HAZOP and mode).
Use separate instances for different scenarios; this is not an alarm queue.
"""
from __future__ import annotations

import copy
import math
import threading
import time
from collections.abc import Mapping

from .consequences import ConsequenceRequest
from .observed_state_runtime import service_state_from_runtime_frame
from .service import RealtimeConsequenceMonitor


class AsyncRuntimeConsequenceMonitor:
    """Nonblocking submission/polling around the existing provider/physics path.

    The monitor and its service must be exclusively owned by this instance.
    Backend timeout remains responsible for bounding a running physics call.
    Close this scheduler before closing its externally owned backend.
    """

    def __init__(self, monitor, template, *, release_resolver, scenario_id,
                 source_id, maximum_age_s, mapping_digest=None):
        if not isinstance(monitor, RealtimeConsequenceMonitor):
            raise TypeError('monitor must be RealtimeConsequenceMonitor')
        if not isinstance(template, ConsequenceRequest):
            raise TypeError('template must be ConsequenceRequest')
        if not callable(release_resolver):
            raise TypeError('release_resolver must be callable')
        for name, value in (('scenario_id', scenario_id), ('source_id', source_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{name} must be a nonempty string')
        if (isinstance(maximum_age_s, bool) or not isinstance(maximum_age_s, (int, float))
                or not math.isfinite(maximum_age_s) or maximum_age_s <= 0):
            raise ValueError('maximum_age_s must be finite and positive')
        self.monitor = monitor
        self.template = template.model_copy(deep=True)
        self.release_resolver = release_resolver
        self.scenario_id = scenario_id
        self.source_id = source_id
        self.maximum_age_s = float(maximum_age_s)
        self.mapping_digest = mapping_digest
        self._condition = threading.Condition()
        self._closed = False
        self._pending = None
        self._running = None
        self._latest = None
        self._completion = None
        self._result = None
        self._sequence = 0
        self._superseded_pending_count = 0
        self._superseded_running_count = 0
        self._thread = threading.Thread(target=self._work, daemon=True,
                                        name=f'prism-{scenario_id}')
        self._thread.start()

    def submit(self, runtime_frame: Mapping, *, now_s: float) -> dict:
        """Validate/queue a newer frame and return without running physics.

        The receipt explicitly identifies a replaced pending update. Callers
        should retain receipts in their historian if every update needs an
        audit trail. Replacements do not represent executed physics.
        """
        submitted_at = time.perf_counter()
        frame = copy.deepcopy(dict(runtime_frame))
        normalized = service_state_from_runtime_frame(
            frame, now_s=now_s, mapping_digest=self.mapping_digest,
        )
        if frame['component_id'] != self.template.component_id:
            raise ValueError('runtime frame component differs from scenario template')
        if frame.get('source_id') != self.source_id:
            raise ValueError('runtime frame source differs from configured stream')
        if normalized['data_age_s'] > self.maximum_age_s:
            raise ValueError('runtime frame exceeds maximum_age_s')
        captured_at = float(frame['captured_at_s'])
        with self._condition:
            if self._closed:
                raise RuntimeError('async monitor is closed')
            if self._latest is not None and captured_at <= self._latest['captured_at_s']:
                raise ValueError('runtime frames must have strictly increasing capture times')
            self._sequence += 1
            job = dict(job_id=self._sequence, frame=frame, submitted_at=submitted_at,
                       now_s=float(now_s), captured_at_s=captured_at,
                       data_age_at_submission_s=float(normalized['data_age_s']))
            replaced = self._pending['job_id'] if self._pending is not None else None
            if replaced is not None:
                self._superseded_pending_count += 1
            self._pending = self._latest = job
            # An earlier result must disappear as soon as a newer state is accepted.
            self._result = None
            self._condition.notify()
            return dict(job_id=job['job_id'], status='QUEUED', scenario_id=self.scenario_id,
                        frame_digest=frame['frame_digest'], superseded_job_id=replaced,
                        submission_elapsed_ms=(time.perf_counter() - submitted_at) * 1000,
                        fresh_physics_executed=False)

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending is not None)
                if self._closed:
                    return
                job = self._pending
                self._pending = None
                self._running = job
            started = time.perf_counter()
            queue_s = started - job['submitted_at']
            result = None
            error = None
            if job['data_age_at_submission_s'] + queue_s > self.maximum_age_s:
                status = 'EXPIRED_BEFORE_EXECUTION'
            else:
                try:
                    result = self.monitor.update_from_runtime_frame(
                        self.template, job['frame'], now_s=job['now_s'] + queue_s,
                        release_resolver=self.release_resolver,
                        mapping_digest=self.mapping_digest,
                    )
                    status = 'READY'
                except Exception as exc:
                    status = 'FAILED'
                    error = dict(type=type(exc).__name__, message=str(exc))
            elapsed_s = time.perf_counter() - job['submitted_at']
            age_s = job['data_age_at_submission_s'] + elapsed_s
            deadline_met = elapsed_s <= self.monitor.deadline_s
            if result is not None:
                status = ('EXPIRED_AFTER_EXECUTION' if age_s > self.maximum_age_s
                          else 'READY' if deadline_met else 'READY_LATE')
                timing = result['realtime']
                timing['worker_update_elapsed_s'] = timing['update_elapsed_s']
                timing.update(
                    queue_elapsed_s=queue_s, update_elapsed_s=elapsed_s,
                    service_elapsed_s=elapsed_s, deadline_met=deadline_met,
                    deadline_status='MET' if deadline_met else 'MISSED',
                    timing_scope='submission + queue + normalization + provider + consequence + result assembly',
                )
                timing['mode_contract'].update(
                    deadline_met=deadline_met,
                    reported_mode=(timing['mode_contract']['evaluation_mode']
                                   if deadline_met else 'deadline_missed'),
                )
                result['telemetry_boundary']['data_age_at_output_s'] = age_s
            completion = dict(
                job_id=job['job_id'], frame_digest=job['frame']['frame_digest'],
                status=status, execution_status=status, error=error,
                queue_elapsed_s=queue_s, end_to_end_elapsed_s=elapsed_s,
                data_age_at_completion_s=age_s, deadline_met=deadline_met,
                deadline_s=self.monitor.deadline_s,
            )
            with self._condition:
                self._running = None
                if self._latest['job_id'] != job['job_id']:
                    completion['status'] = 'SUPERSEDED'
                    self._superseded_running_count += 1
                self._completion = completion
                self._result = (result if not self._closed
                                and completion['status'] in {'READY', 'READY_LATE'} else None)
                self._condition.notify_all()

    def poll(self) -> dict:
        """Return the latest job's result only while its source state is fresh."""
        with self._condition:
            age_s = (None if self._latest is None else
                     self._latest['data_age_at_submission_s']
                     + time.perf_counter() - self._latest['submitted_at'])
            current = (self._completion is not None and self._latest is not None
                       and self._completion['job_id'] == self._latest['job_id'])
            if self._closed:
                status = 'CLOSED'
            elif self._latest is None:
                status = 'IDLE'
            elif current:
                status = self._completion['status']
                if status in {'READY', 'READY_LATE'} and age_s > self.maximum_age_s:
                    status = 'EXPIRED_AFTER_EXECUTION'
            elif self._pending is not None:
                status = 'PENDING'
            else:
                status = 'RUNNING'
            return copy.deepcopy(dict(
                schema_version='prism.async_runtime_monitor.v1', status=status,
                scenario_id=self.scenario_id, component_id=self.template.component_id,
                source_id=self.source_id,
                latest_job_id=None if self._latest is None else self._latest['job_id'],
                running_job_id=None if self._running is None else self._running['job_id'],
                pending_job_id=None if self._pending is None else self._pending['job_id'],
                latest_data_age_s=age_s, maximum_age_s=self.maximum_age_s,
                completion=self._completion,
                result=self._result if status in {'READY', 'READY_LATE'} else None,
                superseded_pending_count=self._superseded_pending_count,
                superseded_running_count=self._superseded_running_count,
                policy=dict(max_running=1, max_pending=1, stale_fallback_used=False,
                            frequency_learning=False, release_inference=False,
                            realtime_fresh_physics_claim=False, facility_qra_claim=False),
            ))

    def close(self, *, wait=True) -> dict:
        """Reject new frames, cancel pending work, optionally await running work."""
        with self._condition:
            self._closed = True
            cancelled = self._pending['job_id'] if self._pending is not None else None
            self._pending = None
            self._result = None
            self._condition.notify_all()
        if wait:
            self._thread.join()
        return dict(status='CLOSED', cancelled_pending_job_id=cancelled,
                    worker_still_running=self._thread.is_alive())

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
