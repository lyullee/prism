# PRISM warm worker 실시간 진단 개발 기록 (2026-10-27)

## 목적

PRISM의 디지털트윈 모니터는 같은 입력을 반복해서 받으면 exact cache를 사용할 수 있다. 그러나 압력·기상·밸브 상태가 바뀌면 새 SLABx-LH2 물리 계산이 필요하다. 기존 `IsolatedBackend`는 요청마다 별도 Python worker를 시작했기 때문에, 모델 import와 프로세스 시작 시간이 모든 요청에 반복됐다.

이번 변경은 물리식을 줄이거나 결과를 재사용해 새 계산처럼 보이게 만드는 방식이 아니다. `PersistentIsolatedBackend`가 같은 pinned worker를 유지하고, 요청마다 다음 검사를 계속 수행한다.

1. 선언된 외부 모델 source tree의 SHA-256 pin 확인
2. PRISM worker adapter의 source digest 확인
3. 변경된 JSON 요청만 worker에 전달
4. worker가 반환한 새 결과와 오류를 그대로 기록
5. timeout·프로세스 종료·invalid JSON을 숫자 결과로 바꾸지 않음

`IsolatedBackend`의 일회성 격리 실행도 그대로 남겨 두었다. 따라서 재현성·감사 목적의 cold run과 반복 모니터링 목적의 warm run을 선택할 수 있다.

## 실제 측정

`results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json`에서 같은 일반 LH2 near-receptor 진단 요청을 사용했다.

| 경로 | 측정값 | 의미 |
|---|---:|---|
| cold fresh physics | 약 2,663 ms | 새 프로세스를 포함한 한 번의 새 계산 |
| warm fresh physics 첫 요청 | 약 2,722 ms | worker 시작 시간이 포함된 첫 요청 |
| warm fresh physics 후속 9건 | p50 1,864 ms / p95 2,043 ms / p99 2,043 ms | 매번 풍속을 바꾼 새 계산이며 cache hit가 아님 |
| warm steady p50/p95/p99 | 1,864 / 2,043 / 2,043 ms | 세 분위수 모두 1 Hz 미충족 |
| exact cache p95 | 약 61.3 ms | 동일 요청 반복 조회는 1 Hz 진단 기준 충족 |

따라서 이번 개발의 결론은 **warm worker가 반복 interpreter 시작 비용을 없애고 상태가 바뀐 fresh 계산을 계속 실행할 수 있게 했지만, 현재 SLABx-LH2 계산은 fresh physics 1 Hz를 아직 충족하지 않는다**는 것이다. 1 Hz를 충족한다고 기록한 경로는 동일 요청 exact cache뿐이다.

## 실행 방법

```powershell
python scripts/benchmark_realtime_cache.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261026/native_full_scope_frequency_assessment/campaign.json `
  --backend-config results/20261009/backend_config_current.json `
  --repetitions 10 `
  --persistent-fresh-repetitions 10 `
  --output results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json
```

`--persistent-fresh-repetitions`는 요청마다 풍속을 조금씩 변경해 exact cache를 우회한다. 이 값은 실험용 입력 변경이며, 센서에서 누출 크기나 고장 빈도를 추정하는 기능이 아니다.

## 적용 범위와 다음 단계

warm worker는 설비 상태→provider 방출 packet→SLABx-LH2/SLABx→점화·피해 연결의 실행 경계를 바꾸지 않는다. 실제 설비 provider packet 자격, 독립 물리검증, 완전한 시설 IR/F-N 범위가 확보되기 전에는 이 기능을 시설 전체 QRA나 운영 SLA로 승격하지 않는다.

현재 다음 성능 개선 후보는 물리 모델을 유지한 상태에서의 계산 예산 관리, 선택된 설비·사건만 갱신하는 scheduling, 검증된 surrogate의 별도 비교이다. 이 후보들은 별도 검증 없이는 1 Hz 주장으로 연결하지 않는다.
