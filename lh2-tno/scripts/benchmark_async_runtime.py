"""Measure async responsiveness with a recorded state/packet and fresh physics.

This diagnostic replays one immutable provider packet with its original state
snapshot. It does not measure a fresh equipment solver or alter the snapshot.
All consequence results are freshly calculated using the configured backend.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from benchmark_realtime_cache import _backend_config
from lh2_tno.async_monitor import AsyncRuntimeConsequenceMonitor
from lh2_tno.backend import PersistentIsolatedBackend
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import canonical_digest
from lh2_tno.equipment_manifest import EquipmentManifest
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.service import ConsequenceService, RealtimeConsequenceMonitor


def run(manifest_path, campaign_path, backend_path, *, repetitions=3):
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError('repetitions must be a positive integer')
    facility = EquipmentManifest.from_json(manifest_path).to_facility()
    campaign = RiskCampaign.model_validate_json(campaign_path.read_text(encoding='utf-8'))
    request = next(
        branch.request for route in campaign.event_routes for branch in route.branches
        if branch.request is not None and branch.request.state_snapshot is not None
    )
    state = request.state_snapshot.model_dump(mode='json')
    frame = dict(
        source_id='recorded-provider-state-benchmark', component_id=request.component_id,
        captured_at_s=state['captured_at_s'], origin=state['origin'], quality=state['quality'],
        state_snapshot=state, state_snapshot_digest=request.state_snapshot_digest,
        source_sha256=state['source_digest'],
        values={name: dict(row, component_id=request.component_id)
                for name, row in state['measurements'].items()},
    )
    frame['frame_digest'] = canonical_digest(frame)
    backend_config = _backend_config(backend_path)
    rows = []
    with PersistentIsolatedBackend(backend_config) as backend:
        for index in range(repetitions):
            # New empty cache per run; same exact provider state, no rebinding.
            service = ConsequenceService(ResearchPipeline(facility, backend))
            sync = RealtimeConsequenceMonitor(service, deadline_s=1.0)
            with AsyncRuntimeConsequenceMonitor(
                sync, request, release_resolver=lambda *_: request,
                scenario_id='recorded-state-physics-benchmark', source_id=frame['source_id'],
                maximum_age_s=backend_config.timeout_s + 30,
            ) as queue:
                receipt = queue.submit(frame, now_s=frame['captured_at_s'])
                pending_polls = []
                while True:
                    started = time.perf_counter()
                    output = queue.poll()
                    poll_ms = (time.perf_counter() - started) * 1000
                    if output['completion'] is not None:
                        break
                    pending_polls.append(poll_ms)
                    time.sleep(0.02)
                result = output['result']
                rows.append(dict(
                    index=index, receipt=receipt, status=output['status'],
                    completion=output['completion'],
                    poll_count_while_computing=len(pending_polls),
                    max_pending_poll_ms=max(pending_polls, default=None),
                    service=result.get('service') if result else None,
                    realtime=result.get('realtime') if result else None,
                    telemetry_boundary=result.get('telemetry_boundary') if result else None,
                    consequence_result_digest=canonical_digest(result) if result else None,
                    adapter_source_digest=result.get('adapter_source_digest') if result else None,
                    receptor_count=len(result.get('data', {}).get('receptors', [])) if result else 0,
                ))
    successful = all(row['service'] and row['service']['fresh_physics_this_update']
                     and not row['service']['exact_cache_hit'] for row in rows)
    return dict(
        schema_version='prism.async_runtime_benchmark.v1',
        status='FRESH_CONSEQUENCE_ASYNC_DIAGNOSTIC' if successful else 'INCOMPLETE',
        provider_mode='recorded_packet_replay_with_original_state_snapshot',
        provider_solver_reexecuted=False, state_snapshot_digest=request.state_snapshot_digest,
        request_digest=request.digest(), frame_digest=frame['frame_digest'], rows=rows,
        startup_included_in_first_physics_sample=True,
        backend_config_used=backend_config.model_dump(mode='json'),
        inputs=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                for path in (manifest_path, campaign_path, backend_path)],
        claims=dict(fresh_equipment_to_damage_latency_measured=False,
                    fresh_consequence_latency_measured=successful,
                    fresh_physics_1hz_claim=False, facility_qra_claim=False,
                    independent_physical_validation_claim=False),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'campaign', 'backend-config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    report = run(args.manifest, args.campaign, args.backend_config, repetitions=args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], samples=[dict(
        status=row['status'], submission_ms=row['receipt']['submission_elapsed_ms'],
        total_s=row['completion']['end_to_end_elapsed_s'], poll_max_ms=row['max_pending_poll_ms'],
        error=row['completion']['error'],
    ) for row in report['rows']]), ensure_ascii=False))
    return 0 if report['status'] == 'FRESH_CONSEQUENCE_ASYNC_DIAGNOSTIC' else 1


if __name__ == '__main__':
    raise SystemExit(main())
