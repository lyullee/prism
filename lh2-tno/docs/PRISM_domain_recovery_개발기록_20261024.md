# PRISM 계산영역·가연성 경계 감사 기록 (2026-10-24)

## 목적

LH2가 새어 나온 뒤 계산 격자 밖에 수소가 남으면, 그 질량을 그대로 0으로 만들 수 없다. 그렇게 하면 화재·폭발 위험을 작게 보이게 할 수 있기 때문이다. PRISM은 방출 질량과 계산영역 밖 질량을 별도로 기록하고, 밖의 수소가 가연성 농도에 도달할 수 있는지 보수적으로 확인한다.

이번 실행은 기존 generic LH2 24개 사건을 같은 packet·문헌 빈도·SLABx-LH2 backend로 다시 계산하고, 계산영역을 넓힌 뒤 **outside-LFL proof**를 추가한 것이다.

| 항목 | 기준 실행 | 확장 실행 |
| --- | --- | --- |
| 풍하측 범위 | -2 m ~ 80 m | -2 m ~ 160 m |
| 횡풍 범위 | -10 m ~ 10 m | -20 m ~ 20 m |
| 높이 범위 | 0 m ~ 12 m | 0 m ~ 20 m |
| 셀 크기 | 0.5 m | 1.0 m |
| 사건 수 | 24 | 24 |
| `EXECUTED_DOMAIN_INCOMPLETE` 사건 | 6 | 0 |
| 회복 사건 | - | 6 |
| 보수적 outside-LFL 증명 | 별도 없음 | 22/24 사건 |

## 무엇을 새로 확인했나

대표 사건 `storage-shell/AREA_0.1%`를 원시 consequence 결과로 재실행해 각 packet이 어느 축에서 격자 밖으로 나가는지 기록했다. `chain_worker.py`는 이제 전체 밖 질량과 함께 풍하측·횡풍·높이별 marginal outside mass, packet 지지경계, SLABx provider의 half-length·속도를 보존한다. 축별 값은 겹칠 수 있으므로 합산하지 않고, 전체 밖 질량은 union 질량 장부의 값을 사용한다.

점화 시각 1 s의 대표 사건은 전체 밖 수소 `5.3358×10⁻⁵ kg`가 풍하측에서만 발생했다. PRISM packet의 최대 길이는 약 `426,324 m`, SLABx provider half-length는 약 `213,531 m`였다. 즉 긴 지지영역은 PRISM이 임의로 만든 값이 아니라 provider가 반환한 finite-puff 기하를 반영한다.

밖의 임의 packet이 서로 겹친다고 가정해도 농도가 LFL에 도달할 수 있는지 보수적으로 계산했다. representative case의 outside-domain mole-fraction upper bound는 `5.09375×10⁻⁵`, 수소 LFL은 `0.04`다. 따라서 이 사건에서는 격자 밖 수소가 남아 있다는 사실은 보존하되, 그 밖의 질량만으로 화재·폭발 LFL을 넘는다고 증명되지 않았으므로 fire/explosion branch의 계산영역 차단 표지는 해제했다. 큰 영역 재실행에서도 outside mass는 사실상 0으로 수렴했다.

## 결과를 어떻게 읽어야 하나

확장 campaign은 24건 모두 `EXECUTED` 또는 `EXECUTED_OPERATOR_LIMITED`로 실행됐고, 이전 6건의 domain-incomplete 표지는 회복됐다. 22건은 outside-LFL proof가 있었고, 나머지 2건은 reliquefier 운전 사건으로 cloud observation이 생성되지 않아 해당 proof가 필요하지 않았다. 이 결과는 **화재·폭발 계산영역 gate를 진단 범위 안에서 닫았다는 뜻**이다.

다음 항목은 여전히 별도 장부로 남아 있다.

- 계산영역 밖 inventory는 0으로 대체하지 않고 event row와 explosion row에 남긴다.
- provider geometry가 시설 전체 공간을 실제로 대표한다는 현장 자격은 확인하지 않았다.
- 19건은 source operator 또는 모델 범위가 제한된 `EXECUTED_OPERATOR_LIMITED`다.
- qualified provider packet은 0건이며, 시설 전체 IR/F-N과 QRA는 계속 보류한다.
- 이 proof는 asphyxiation, 실내 거동, 폭굉, 도미노를 닫지 않는다.

따라서 이 개발은 “영역 밖 수소를 삭제해서 위험을 숨긴 것”이 아니라, **밖의 질량을 기록한 채 선언한 fire/explosion branch에 대해 보수적인 LFL 경계를 추가한 것**이다.

상세 표준영역 진단은 [`cloud_support_standard_domain_probe_area_0_1_v1.json`](../results/20261024/cloud_support_standard_domain_probe_area_0_1_v1.json), 큰 영역 민감도는 [`cloud_support_large_domain_probe_area_0_1_v1.json`](../results/20261024/cloud_support_large_domain_probe_area_0_1_v1.json), 대표 provider geometry 요약은 [`cloud_support_diagnostic_area_0_1_v1.json`](../results/20261024/cloud_support_diagnostic_area_0_1_v1.json)에 저장했다. 전체 24건 재실행 결과는 [`native_generic_scope_campaign_flammability_gate_result_v2.json`](../results/20261024/native_generic_scope_campaign_flammability_gate_result_v2.json), event별 회복 감사는 [`domain_recovery_audit_flammability_gate_v2.json`](../results/20261024/domain_recovery_audit_flammability_gate_v2.json)에 저장했다.

## 재현 명령

```powershell
python scripts/audit_domain_recovery.py `
  --baseline-campaign results/20261023/native_generic_scope_campaign_result_v12.json `
  --recovery-campaign results/20261024/native_generic_scope_campaign_flammability_gate_result_v2.json `
  --baseline-defaults examples/provider_request_defaults.json `
  --recovery-defaults results/20261024/provider_request_defaults_domain_recovery_v1.json `
  --output results/20261024/domain_recovery_audit_flammability_gate_v2.json
```

## 다음 개발 기준

다음 단계는 이 진단 gate를 시설 전체 QRA로 승격하는 것이 아니다. 우선 실제 설비 provider가 방출 envelope와 사고 packet의 자격 증거를 제공하고, 현장 형상·장애물·수신기·인구와 독립 물리검증을 연결해야 한다. 그 전까지 PRISM은 밖의 inventory ledger, operator-limited 사건, 미계산 사고 범위, 시설 IR/F-N 보류를 계속 표시한다.
