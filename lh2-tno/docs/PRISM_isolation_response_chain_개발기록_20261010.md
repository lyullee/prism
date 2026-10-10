# PRISM 차단 응답 방출 체인 개발 기록

작성일: 2026-10-10  
대상: PRISM v0.6.x LH2 설비 위험 분석 진단 경로

## 1. 이번 보완의 목적

기존 방출 계산에는 차단 성공·실패를 나타내는 종료 근거가 있었지만, 차단 명령과 그 뒤의 유량 응답이 실제 수치 campaign에 소비되었는지를 한 번에 검사하는 감사가 없었다. 이번 보완은 다음 연결을 확인한다.

```text
설비 차단 응답
  → 차단 전·후 유량과 잔차
  → 방출 종료 근거
  → LH2 방출 campaign case
  → source → pool → 근접장/확산 → cloud → 점화·피해
```

구현은 `src/lh2_tno/isolation_response_audit.py`의 `audit_isolation_response_campaign()`과 `scripts/audit_isolation_response.py`에 있다. 감사 결과는 `results/20261009/equipment_isolation_campaign/isolation_response_audit.json`에 저장한다.

## 2. 입력 자료와 현재 진단 범위

이번 입력은 기존 장비 차단 campaign의 합성 진단 자료다.

| 입력 | 내용 |
|---|---|
| `provider_response.json` | `AREA_0.01%`, `0.1%`, `1%`, `10%`, `100%`의 5개 개구 구간에 대해 success/failure 응답을 제공한다. |
| `campaign_result.json` | 두 기상 조건을 포함한 20개 case와 80개 risk atom을 보존한다. |
| release branch | `provider-isolation-success`, `provider-isolation-failure`를 사용한다. |
| 성공 종료 | `reviewed_isolation_success`, 차단 시각 0.25 s, 차단 후 최대 유량 0 kg/s를 사용한다. |
| 실패 종료 | `synthetic_diagnostic_horizon`, 차단 후 유량 0 확인을 선언하지 않고 진단 시계에서 멈춘다. |

각 provider branch는 위치와 branch ID를 이용해 campaign case를 찾는다. 위치가 다르거나 종료 근거가 branch와 다르면 감사가 차단된다. campaign의 모든 case는 `EXECUTED`여야 하고, 각 provider branch가 최소 한 개 이상의 case를 소비해야 한다.

## 3. 감사가 확인하는 항목

### 3.1 차단 성공

성공 branch에는 차단 전 양의 유량, 차단 시각과 방출 시계, 차단 후 관측 가능 여부, `isolation_flow_zero_confirmed=true`, `post_close_max_flow_kg_s=0.0`가 있어야 한다. 이 자료는 “차단 명령을 입력했다”는 사실만 확인하는 것이 아니라, provider가 차단 후 유량이 0이 되었다고 응답했는지를 확인한다.

### 3.2 차단 실패

실패 branch에는 차단 전 양의 유량이 있어야 하지만, 차단 후 유량 0과 관측 완료를 참으로 표시하면 안 된다. 이 branch는 실제 시설의 무한 방출을 뜻하지 않는다. 현재 구현에서는 `synthetic_diagnostic_horizon`을 사용해 계산을 제한된 진단 시계에서 끝내고, 재고 소진이나 실제 누출 지속시간을 임의로 만들지 않는다.

### 3.3 보존량과 chain 소비

각 branch의 `max_total_mass_residual_kg`와 `max_total_energy_residual_j`가 각각 허용오차 안에 있는지 확인한다. 이후 campaign case가 실제로 계산되었는지, risk atom이 만들어졌는지, source부터 최종 피해 단계까지의 backend chain이 닫혔는지는 기존 `consequence_backend_chain_audit`와 함께 확인한다. 이번 감사는 그 결과를 branch별로 다시 묶어 “차단 응답이 계산 입력으로 들어갔는가”를 확인하는 역할이다.

## 4. 현재 실행 결과

2026-10-10 기준 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| provider branch | 10개 (성공 5, 실패 5) |
| campaign case | 20개 |
| risk atom | 80개 |
| 성공 branch 차단 후 최대 유량 | 모두 0 kg/s |
| 실패 branch 종료 | 모두 `synthetic_diagnostic_horizon` |
| 질량·에너지 보존 감사 | 통과 |
| 시설 전체 QRA 승격 | 하지 않음 |
| 물리 검증 주장 | 하지 않음 |
| 빈도 추론 | 하지 않음 |

재현 명령:

```powershell
python scripts/audit_isolation_response.py `
  --provider-response results/20261009/equipment_isolation_campaign/provider_response.json `
  --campaign-result results/20261009/equipment_isolation_campaign/campaign_result.json `
  --output results/20261009/equipment_isolation_campaign/isolation_response_audit.json
```

단위 테스트는 `tests/test_isolation_response_audit.py`에서 성공 branch와 실패 branch를 각각 검사하고, 성공 branch의 차단 후 유량을 아주 작은 양수로 바꾸었을 때 fail-closed 되는지 확인한다.

## 5. 이 결과가 의미하는 것

이번 보완으로 “설비 상태 또는 차단 응답 → 방출 종료 → 피해 chain”을 별도의 진단 campaign에서 확인할 수 있다. 따라서 향후 실제 설비 provider가 같은 계약으로 차단 전·후 유량, 관측 시계, 잔차, 종료 근거를 제공하면 동일한 감사기를 사용할 수 있다. 설비별로 `asset_id`, 위치, branch ID, 요청 digest, 결과 digest를 함께 보존할 수 있어 여러 설비의 branch를 섞어 쓰는 오류도 줄어든다.

## 6. 아직 남은 제한과 다음 연결

현재 자료는 합성 장비 차단 campaign이다. `0.99`와 같은 차단 성공확률이 들어 있는 기존 campaign 값은 진단 계산을 위한 선언값이며, 현장 고장률·차단 신뢰도·요구시 실패확률로 승격하지 않는다. 또한 현재 44개 union facility case의 qualified provider packet coverage는 0/44이고, 시설 IR/F-N과 전체 QRA는 계속 보류한다.

다음에 실제 설비별로 연결하려면 provider가 최소한 다음을 내보내야 한다.

1. 설비·포트·방출 branch를 식별하는 ID와 원자료 digest
2. 차단 명령 시각, 실제 valve/actuator 응답 시각, 차단 전·후 유량
3. 차단 후 관측 지속시간과 zero-flow 판정 기준
4. 잔류 재고와 방출 종료 basis
5. 방출 이력과 보존량 계산의 질량·에너지 잔차
6. 동일 packet을 소비한 SLABx-LH2/피해 backend 결과 digest

이 자료가 실제 설비에서 확보되면 현재 감사는 provider packet 자격 심사와 시설 case coverage의 입력이 될 수 있다. 자료가 없을 때는 지금처럼 성공확률, 누출 지속시간, 빈도를 추정하지 않고 `OPEN_EVIDENCE_REQUEST` 또는 `UNCOMPUTED`로 남긴다.\n