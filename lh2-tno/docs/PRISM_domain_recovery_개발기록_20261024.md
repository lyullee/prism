# PRISM 계산영역 회복 감사 기록 (2026-10-24)

## 목적

LH2 방출 뒤의 가연성 구름을 계산할 때, 계산영역 밖에 남은 수소는 피해와 폭발 기여를 계산할 수 없다. 이 값을 0으로 바꾸면 위험을 숨기게 되므로 PRISM은 해당 case를 `EXECUTED_DOMAIN_INCOMPLETE`로 보류한다.

이번 개발에서는 기존 generic 24개 사건을 같은 packet·빈도·backend로 다시 계산하되, 공간영역만 넓혔다.

| 항목 | 기준 실행 | 확장 실행 |
| --- | --- | --- |
| 풍하측 범위 | -2 m ~ 80 m | -2 m ~ 160 m |
| 횡풍 범위 | -10 m ~ 10 m | -20 m ~ 20 m |
| 높이 범위 | 0 m ~ 12 m | 0 m ~ 20 m |
| 셀 크기 | 0.5 m | 1.0 m |
| 사건 수 | 24 | 24 |
| domain-incomplete 사건 | 6 | 6 |
| 회복 사건 | - | 0 |

## 결과 해석

영역을 넓혀도 저장탱크 `AREA_0.1%`, `AREA_1%`, `AREA_10%`, `AREA_100%`와 이송배관 `AREA_10%`, `AREA_100%`의 6개 사건은 계속 영역 밖 가연성 질량 표지를 남겼다. 따라서 이 문제는 단순히 격자를 크게 만드는 문제로 해결되지 않는다. SLABx 전이영역, 유한 방출 구름 관측 연산자, 또는 provider가 제공하는 영역 완결 증거를 추가로 닫아야 한다.

### 원인 추적 결과

한 대표 사건(`storage-shell/AREA_0.1%`)을 원시 consequence 결과로 다시 실행하고, 각 직육면체 packet이 어느 축에서 잘리는지 별도로 기록했다. `chain_worker.py`는 이제 전체 밖 질량과 함께 **풍하측·횡풍·높이별 marginal outside mass**를 기록한다. 이 세 값은 서로 겹칠 수 있으므로 합산해 전체 밖 질량으로 사용하지 않고, 실제 전체 밖 질량은 기존 질량 장부의 union 값만 사용한다. packet 전체 지지경계와 최대 길이·수소 질량분율도 함께 남긴다.

대표 사건의 점화 시각(1 s)에는 전체 밖 수소 `5.3358×10⁻⁵ kg`가 풍하측 축에서만 발생했고, 횡풍·높이 축의 marginal outside mass는 0이었다. 그런데 유한 top-hat packet 지지 길이는 약 `426,324 m`였고, 선언한 풍하측 영역은 `-2~160 m`였다. 같은 풍하측 clipping은 `1 μs` 첫 관측부터 시작했다. 따라서 이번 보류는 단순한 80 m/160 m 경계 부족보다, 작은 액체 pool 방출에서 SLABx carrier의 매우 작은 수소 질량분율을 유한 방출량에 맞추는 과정이 거대한 직육면체 packet을 만드는 관측 연산자 문제로 분류한다.

상세 진단은 [`cloud_support_diagnostic_area_0_1_v1.json`](../results/20261024/cloud_support_diagnostic_area_0_1_v1.json)에 저장했다. 이 결과는 원인 진단일 뿐이며, 밖의 질량을 0으로 만들거나 flammable mass·폭발·시설 QRA를 승격하지 않는다. 다음 구현은 provider가 제공하는 공간 envelope 또는 검증된 liquid-pool observation operator를 추가하는 것이며, 그 전까지 6개 사건은 계속 보류한다.

비교 결과는 [`domain_recovery_audit_v1.json`](../results/20261024/domain_recovery_audit_v1.json)에 저장했다. 감사기는 event ID를 맞춰 기준·확장 상태를 비교하고, 회복된 사건과 지속 보류 사건을 분리한다. 이 결과는 provider 자격, 빈도, 시설 IR/F-N을 승격하지 않는다.

재현 명령:

```powershell
python scripts/audit_domain_recovery.py `
  --baseline-campaign results/20261023/native_generic_scope_campaign_result_v12.json `
  --recovery-campaign results/20261024/native_generic_scope_campaign_domain_recovery_result_v1.json `
  --baseline-defaults examples/provider_request_defaults.json `
  --recovery-defaults results/20261024/provider_request_defaults_domain_recovery_v1.json `
  --output results/20261024/domain_recovery_audit_v1.json
```

## 다음 개발 기준

다음 단계는 계산영역을 무조건 키우는 방식이 아니라, 방출별 구름 외곽 경계와 SLABx handoff의 질량 보존을 검증하는 것이다. 영역 밖 질량이 남아 있으면 위험 원자는 계속 보류하고, 영역 회복 민감도 자체만 진단 근거로 사용한다.
