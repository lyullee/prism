# 비동기 상태 평가와 전체 처리시간

## 이번에 바뀐 동작

설비 모델의 사고 방출 계산은 피해 계산보다 앞에서 실행된다. 기존 모니터의 마감시간 판정은 피해 계산 서비스의 시간만 사용했다. 이제 센서 정규화, 설비 provider 호출, 방출 packet 검증, 피해 계산과 결과 조립 시간을 모두 포함한다. `telemetry_boundary.data_age_at_output_s`에도 이 시간이 더해진다.

기존 `service.service_elapsed_ms`는 피해 계산/정확 캐시 조회 시간이라는 뜻을 유지한다. 전체 단일 업데이트 시간은 `realtime.update_elapsed_s`이고, `realtime.deadline_status`는 이 전체 시간을 기준으로 판정한다. `state_resolution_elapsed_s`와 `consequence_service_elapsed_s`로 비용을 구분할 수 있다. 시설의 기존 `total_service_elapsed_ms`는 여전히 피해 서비스 시간의 합이며 시설 전체 벽시계 시간이 아니다.

새 `AsyncRuntimeConsequenceMonitor`는 기존 `RealtimeConsequenceMonitor`를 별도 worker에서 실행한다. 입력 접수와 상태 조회가 물리 계산의 종료를 기다리지 않는다. 물리식, 문헌 빈도, 방출 종료조건을 바꾸거나 근사하지 않는다.

## 디지털트윈에 붙이는 위치

`현장값 + 운전 모드 → HAZOP 판단 → 선택된 사고 시나리오 → 비동기 상태 평가 → 관리자 표시`

비동기 객체 하나는 **하나의 설비·하나의 선택된 사고 시나리오·하나의 입력 스트림**을 담당한다. `release_resolver`는 그 시나리오와 입력 상태에 대해 외부 설비 모델을 호출하고 검증된 `ConsequenceRequest`를 반환해야 한다. 누출 개구, 차단시간, 재고와 방출 종료근거는 계속 provider가 소유한다. HAZOP 판단이나 운전 모드별 시나리오 선택 기능을 이번 변경에서 새로 구현한 것은 아니다.

```python
from lh2_tno.async_monitor import AsyncRuntimeConsequenceMonitor

# monitor: RealtimeConsequenceMonitor(ConsequenceService(pipeline))
# template: 이미 선택된 시나리오의 ConsequenceRequest
# release_resolver: 상태 → 외부 설비 사고 계산 → ConsequenceRequest
with AsyncRuntimeConsequenceMonitor(
    monitor,
    template,
    release_resolver=release_resolver,
    scenario_id="storage-shell-small-leak",
    source_id="storage-monitor",
    maximum_age_s=5.0,  # 적용 시설에서 정하는 입력 유효시간
) as async_monitor:
    receipt = async_monitor.submit(runtime_frame, now_s=application_time_s)
    # UI/모니터링 반복주기에서 호출한다.
    status = async_monitor.poll()
    if status["status"] in {"READY", "READY_LATE"}:
        result = status["result"]
        # READY_LATE는 1초 등 지정 deadline을 초과한 결과임을 표시한다.
```

`runtime_frame`은 기존 `prism.observed_state_runtime_frames.v1` 산출물의 개별 frame이다. component/source ID, 증가하는 capture time, frame/state digest를 검사한다. 정규화된 상태는 사고 빈도나 임의의 누출량을 포함할 수 없다. 같은 monitor/service를 다른 worker가 동시에 사용하지 않는다. 종료할 때는 비동기 객체를 먼저 닫고 backend를 닫는다. 실행 중인 solver의 종료 상한은 backend timeout이 담당하며 `close(wait=False)`가 solver를 강제 종료하는 것은 아니다.

## 대기열과 결과의 의미

| 상태 | 관리자/호출자가 받는 의미 |
|---|---|
| `PENDING` / `RUNNING` | 새 상태를 계산 중. `result=null` |
| `READY` | 최신 입력 결과이며 접수부터의 전체 시간이 deadline 이내 |
| `READY_LATE` | 최신 입력 결과지만 전체 deadline 초과. 지연을 표시해야 함 |
| `EXPIRED_BEFORE_EXECUTION` | 대기 중 입력 유효시간 초과. provider/피해 계산 생략, 결과 없음 |
| `EXPIRED_AFTER_EXECUTION` | 계산 중 또는 표시 전 유효시간 초과. 결과 없음 |
| `FAILED` | provider/검증/backend 실패. 오류를 보존하고 이전 결과로 대체하지 않음 |
| `CLOSED` | 접수 종료. 대기 요청 취소, 숫자 결과 없음 |

실행 중인 요청 한 건과 대기 요청 한 건만 보관한다. 같은 시나리오의 새 상태가 들어오면 대기 중이던 상태를 교체하고 접수증의 `superseded_job_id`에 남긴다. 이미 실행 중인 이전 상태는 계산을 마쳐도 최신 결과로 게시하지 않으며 `SUPERSEDED`로 기록한다. 입력 접수증을 historian에 보관하면 생략된 요청도 추적할 수 있다.

이 정책은 이미 선택된 시나리오의 현재 상태 재평가용이다. 별도 사고 시나리오, 모드 변경, HAZOP 경보 이력을 같은 큐에서 생략해서는 안 된다. 시나리오별 객체와 외부 경보 이력을 유지해야 한다. 현재 예측 시점의 모든 결과가 필요한 시뮬레이션 캠페인은 기존 순차 캠페인 경로를 사용한다.

## 실행 확인

`tests/test_async_monitor.py`의 10개 검사는 동작 중 새 입력, 대기 요청 교체, 오래된 결과 차단, provider 오류, 잘못된 ID/digest/시각, 대기·계산·표시 중 유효시간 만료, 종료, provider/정규화 시간 포함을 확인한다. 전체 패키지 검사는 **942 passed**였다. 물리 실험 검증을 의미하지 않는다.

추가로 현재 외부 SLABx-LH2/풀/피해 backend를 사용해 실제 피해 계산을 세 번 새로 실행했다. 원래 상태 snapshot과 방출 packet을 그대로 재생했으므로 **설비 solver를 새로 실행한 전체 체인 성능 측정은 아니다.** 캐시는 매회 비운 상태였고 세 계산 모두 `fresh_physics_this_update=true`, `exact_cache_hit=false`였다.

| 실행 | 입력 접수 | 접수부터 결과 완료 | 계산 중 상태 조회 최대 |
|---|---:|---:|---:|
| 첫 worker 계산 | 0.347 ms | 2.711 s (`READY_LATE`) | 0.061 ms |
| 후속 새 피해 계산 1 | 0.179 ms | 0.740 s | 0.132 ms |
| 후속 새 피해 계산 2 | 0.179 ms | 0.802 s | 0.077 ms |

세 표본은 비동기 입력/조회가 작동한다는 진단이다. 모든 설비 상태와 시나리오가 1초 안에 새로 계산된다는 보장은 아니다. 기존 2.6초 benchmark와는 입력 snapshot, 실행 환경 및 코드 시점이 다르므로 속도 개선 비율을 주장하지 않는다.

재현 명령:

```powershell
python scripts/benchmark_async_runtime.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261031/native_full_scope_frequency_pipefix_state_bound/campaign.json `
  --backend-config results/20261009/backend_config_current.json `
  --repetitions 3 `
  --output results/runtime_async_current/benchmark.json
```

위 backend config에는 개발 PC의 외부 모델 경로가 있다. benchmark는 현재 source hash를 측정해 실제 사용한 pin과 입력 해시를 결과에 남긴다. 파일은 [`benchmark.json`](../results/runtime_async_current/benchmark.json), 검사는 [`pytest.xml`](../results/runtime_async_current/pytest.xml)에 보존한다.

## 완료 기준과 남은 연결

이번 범위의 완료 기준은 입력 접수/조회와 물리 실행의 분리, 큐 크기 제한, 최신성·유효시간·실패 표시, 전체 업데이트의 deadline 및 데이터 나이 산정이다. 코드·회귀 검사·실제 피해 backend 진단으로 확인했다.

IJHE 전체 목표는 계속 진행 중이다. 실제 provider 실행을 포함한 여러 설비의 부하 측정, 검토된 차단·재고 종료근거, 독립 물리검증, 시설 전체 사고범위의 미계산 항목이 남아 있다. 이번 추가로 provider qualification, 시설 QRA, 센서 기반 빈도 학습을 승인하지 않는다.
