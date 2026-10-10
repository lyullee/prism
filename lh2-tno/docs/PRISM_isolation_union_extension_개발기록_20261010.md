# PRISM 격리 응답 시설 원장 확장 개발 기록

작성일: 2026-10-10
대상: PRISM v0.6.x 일반 옥외 액화수소시설 진단 경로

## 1. 이번 개발의 목적

기존 시설 원장은 34개 event, 44개 case, 176개 risk atom을 보유하고 있었다. 별도
`equipment_isolation_campaign`에는 차단 성공·실패를 실제 피해 chain에 소비한 5개 event,
20개 case, 80개 risk atom이 있었지만, 두 원장이 서로 다른 이름공간에 있어 한 시설 원장으로
동시에 검사할 수 없었다.

이번 확장은 기존 원장을 바꾸지 않고 `isolation-response` 이름공간을 추가한다.

```text
기존 LH2 시설 원장 34 event / 44 case / 176 atom
        +
격리 성공·실패 확장 5 event / 20 case / 80 atom
        ↓
진단용 결합 원장 39 event / 64 case / 256 atom
```

구현은 `src/lh2_tno/isolation_extension.py`의
`build_isolation_union_extension()`과
`scripts/build_isolation_extension_assessment.py`에 있다.

## 2. 성공·실패 branch가 어떻게 결합되는가

격리 campaign은 5개 개구 구간마다 성공과 실패 branch를 만들고, 두 기상 조건을 각각
계산한다. 따라서 성공 10 case와 실패 10 case가 생긴다. 확장기는 다음 작업을 한다.

1. 독립 campaign의 event·condition ID에 `generic-lh2-near-receptor-diagnostic/isolation-response/`
   접두어를 붙여 기존 ID 충돌을 막는다.
2. `terminal_pipe_asset`와 `terminal_pipe`를 일반 시설의
   `isolation-response-pipe`와 `isolation-response-pipe-01`로 rebinding한다.
3. 성공 branch의 `reviewed_isolation_success`와 실패 branch의
   `synthetic_diagnostic_horizon` 종료 근거를 그대로 보존한다.
4. 성공확률을 현장 장벽 신뢰도로 바꾸지 않고 provider packet 수를 0으로 유지한다.
5. 기존 facility merger로 IR/F-N 원장, 사고군 범위, 설비별 기여도를 다시 계산한다.

case에는 오래된 isolation campaign이 내보내지 않았던 domain marker와 진단용 provider identity
shim을 명시한다. 이것은 risk atom chain의 case 연결을 검사하기 위한 표식이며, 상태 snapshot이나
적격 provider packet을 대신하지 않는다.

## 3. 현재 실행 결과

출력 위치: `results/20261026/native_full_scope_union_assessment/isolation_extension/`

| 검사 | 결과 |
|---|---|
| 결합 원장 | 39 event / 64 case / 256 risk atom |
| 성공·실패 case | 10 / 10 |
| 방출→피해 risk atom chain | `FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC` (64/64) |
| 시설 IR/F-N 재집계 | `FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC` |
| 설비별 기여도 재집계 | `FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC` |
| 설비 상태→방출 증거 | `FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC` (64/64) |
| 적격 provider packet | 0/64 case |
| 시설 전체 위험/QRA 승격 | 하지 않음 |

44개 기존 case는 canonical equipment state snapshot과 provider echo가 있어 상태 release 감사가
닫힌다. 새 isolation 20개 case는 provider 응답의 첫 상류 상태 행에서 압력·온도·재고를 복사해
`prism.equipment_state_snapshot.v1`로 만들고, adapter/worker digest와 snapshot digest echo를
결합했다. 이 변환은 방출량에서 상태를 역산하지 않으며 `model_prediction` 진단 origin과
`diagnostic_state_snapshot_derivation`을 보존한다. 따라서 구조적 상태→방출 identity 감사는
64/64로 닫히지만, 적격 provider packet이나 현장 물리검증으로 승격되지는 않는다.

## 4. 재현 명령

```powershell
python scripts/build_isolation_extension_assessment.py `
  --base-result results/20261026/native_full_scope_union_assessment/campaign_result.json `
  --base-scope-matrix results/20261026/native_full_scope_union_assessment/scope_matrix.json `
  --isolation-result results/20261009/equipment_isolation_campaign/campaign_result.json `
  --isolation-provider-response results/20261009/equipment_isolation_campaign/provider_response.json `
  --output-dir results/20261026/native_full_scope_union_assessment/isolation_extension
```

`verification.json`은 논문용 검토자가 먼저 확인할 요약이고, 나머지 파일은 결합 원장·범위표·
상태 release 감사·IR/F-N 감사·설비 기여도 감사의 원자료다. 전체 테스트에서 이 확장 전용
검사는 2건을 추가한다.

## 5. 해석과 다음 개발 입력

이번 단계에서 “격리 응답 → 방출 종료 → SLABx-LH2/피해 → 시설 IR/F-N 회계”의 결합 구조는
재현된다. 그러나 실제 시설의 차단 신뢰도나 사고 빈도를 산출한 것은 아니다. 다음 provider
export는 각 isolation case에 아래 계약을 추가해야 상태 release gate가 닫힌다.

- 실제 설비 provider가 확인한 `prism.equipment_state_snapshot.v1`와 `state_snapshot_digest`
- 상태 snapshot digest의 provider echo와 포트 ID
- provider source/result digest의 원자료 추적성
- 차단 전·후 유량, 실제 종료 시각, 잔류 재고
- 종료 basis를 provider packet에 다시 기록한 termination echo
- 방출 이력의 질량·에너지 폐합과 독립 검증 자료

현재 확장은 문헌 빈도, 장벽 확률, 물리검증 자료를 새로 추정하지 않는다. 따라서 결합 원장의
조건부 IR/F-N은 계산 회계로만 제공하며, qualified facility QRA는 계속 보류한다.
