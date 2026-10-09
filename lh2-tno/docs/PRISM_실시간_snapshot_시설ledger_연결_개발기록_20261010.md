# PRISM 실시간 snapshot → 시설 risk ledger 연결 개발기록

작성일: 2026-10-10

## 목적

`FacilityRealtimeConsequenceMonitor`는 디지털트윈의 한 시점 상태를 검사한다.
설비 상태, provider가 계산한 방출경로, 현재 기상에서의 수용점 피해, 처리시간을
한 번의 snapshot에 보존한다. 이 결과만으로는 시설 연간 위험도를 계산할 수 없다.
현재 snapshot에는 다음이 없기 때문이다.

- 어떤 연간 기상조건에 속하는지와 그 확률
- 어떤 차단·방출 branch인지와 그 확률
- 직접 화염·지연 flash·지연 폭발·무점화 branch별 피해
- branch별 피해로 계산한 기대 사망수의 폐합

이 차이를 해결하기 위해 `realtime_campaign.py`에 명시적 어댑터를 추가했다.
어댑터는 빠진 값을 추정하지 않고, 사용자가 검토한 시나리오 계약을 모두 전달한
경우에만 기존 `merge_facility_campaign_results()`가 읽을 수 있는 조건부 campaign
결과를 만든다.

## 연결 흐름

```text
설비 frame
  ↓
FacilityRealtimeConsequenceMonitor
  ├─ process state / telemetry digest
  ├─ provider release path (duration, isolation, inventory)
  ├─ current-weather receptor harm
  └─ explicit literature frequency
  ↓
build_realtime_facility_risk_handoff()
  ↓  (연간조건·방출branch·점화branch·branch 피해를 자동 생성하지 않음)
build_realtime_facility_campaign_result()
  ↓  (호출자가 명시한 scenario binding 검증)
merge_facility_campaign_results()
  ↓
조건부 시설 IR/F-N 기여 + 보류 사유
```

`slabx-lh2` 또는 LH2 공정 모델은 provider release path와 consequence 결과를
생성하는 앞단에 놓인다. 이 개발기록의 어댑터가 SLABx 입력을 대신 만들거나
누출 크기를 역추정하지는 않는다.

## 입력 계약

### `annual_conditions`

각 행에는 `id`, `annual_probability`, `weather`, `population`, `provenance`가
필수다. 확률의 합은 1이어야 하며 모든 조건은 동일한 receptor ID 집합을 가져야
한다. population 행에는 `receptor_id`, `persons`, `presence_probability`,
`provenance`가 필요하다. 인구가 빠진 조건은 만들지 않는다.

### `scenario_bindings`

설비마다 하나의 명시적 binding을 둔다.

- `component_id`, `event_id`, `asset_id`
- `annual_condition_id`
- `release_branch_id`, `release_branch_probability`
- 네 가지 `ignition_branch_probabilities`
- 수용점별 네 가지 `branch_harm_low_high`
- 하나 이상의 `scenario_families`

점화확률은 다음 네 branch를 모두 포함하고 합이 1이어야 한다.

```text
direct_fire
delayed_flash_fire
delayed_explosion
no_ignition
```

`no_ignition` 피해는 `[0, 0]`이어야 하며 low endpoint가 high endpoint보다 클 수
없다. 각 수용점의 branch 피해를 점화확률로 가중한 값은 realtime snapshot의
`harm_given_observed_release_low_high`와 수치적으로 같아야 한다.

\[
 H_{observed,r,k} = \sum_b P(b) H_{r,k,b}
\]

이 폐합이 맞지 않으면 어댑터는 `RealtimeCampaignBindingError`를 발생시킨다.
이 검사는 하나의 관측 피해를 임의로 branch별로 나누는 일을 막는다.

## 방출경로와 빈도

개시빈도는 `RealtimeFrequencyBinding`에서 복사한다. 센서 frame으로 빈도를 배우지
않는다. provider release path가 `AVAILABLE_PROVIDER_RELEASE_PATH`가 아니면
그 case는 `UNCOMPUTED`이고 risk atom을 만들지 않는다. 그러므로 방출경로가
없을 때 0 kg 방출이나 정상 차단으로 바뀌지 않는다.

path가 있더라도 현재 adapter는 provider qualification이나 독립 물리검증을
수행하지 않는다. case는 `EXECUTED_OPERATOR_LIMITED`로 기록하고, 종료 basis,
duration, cumulative mass, residual mass를 case ledger에 보존한다. synthetic
diagnostic horizon은 `synthetic_release_horizon_present=true`로 남아 시설 전체
합계를 막는다.

## 시설 ledger 변환

하나의 realtime component는 네 점화 branch risk atom으로 변환된다.

```text
conditional_weight
  = annual_condition_probability
  × release_branch_probability
  × ignition_branch_probability
```

개시빈도는 atom에 그대로 남고, 시설 IR 산술은
`initiating_frequency × conditional_weight × receptor_harm`으로 수행된다. 인구와
재실확률을 사용한 기대 사망수는 atom에
`expected_deaths_basis="population_weighted"`와 함께 기록한다. 시설 ledger는
해당 annual condition의 인구 장부를 찾아 다음을 재확인한다.

```text
expected_deaths[k]
  = Σ(persons[r] × presence_probability[r] × harm[r][k])
```

기존 저장 ledger와의 호환을 위해 이 표시는 명시적으로 opt-in이다. 표시가 없는
기존 atom은 기존 receptor-harm 합계 규칙을 유지한다.

## 결과 상태 해석

정상적으로 연결된 예도 다음 상태를 가진다.

| 필드 | 값 | 의미 |
|---|---|---|
| `schema_version` | `prism.realtime_facility_campaign_result.v1` | 실시간 adapter 결과 |
| case status | `EXECUTED_OPERATOR_LIMITED` | 수치 결과는 있으나 운영·검증 범위 제한 |
| `conditional_diagnostic_facility_risk_available` | `true` (merge 결과) | 전달된 atom의 조건부 IR/F-N 기여 계산 가능 |
| `facility_total_risk_available` | `false` | 전체 설비·사고범위가 닫히지 않음 |
| `qualified_facility_qra_available` | `false` | qualified provider 증거 없음 |
| `physical_validation_claim` | `false` | 독립 물리검증을 주장하지 않음 |

누락 설비가 있으면 coverage에 `MISSING_COVERAGE`가 남는다. path가 없으면
`UNCOMPUTED` case가 남는다. branch 폐합 오류, 잘못된 receptor 집합, 확률 합 오류는
입력 오류로 즉시 중단한다.

## 확인한 테스트

`tests/test_realtime_campaign.py`가 다음을 검증한다.

1. provider release path + 문헌 빈도 + 명시 annual condition을 네 점화 atom으로
   변환하고 기존 facility ledger에 연결한다.
2. 인구 10명 조건에서 population-weighted expected deaths가 ledger에서 폐합된다.
3. branch별 피해가 관측 피해와 다르면 즉시 거절한다.
4. provider release path가 없으면 위험 0으로 바꾸지 않고 명확한 오류로 보류한다.

이 테스트는 합성 provider와 합성 피해를 사용한다. 따라서 통과 자체가 실제
액화수소 시설의 qualified QRA 또는 독립 물리검증을 뜻하지 않는다.

## 남은 작업

- 설비별 LH2 공정 모델·SLABx-LH2 출력의 실제 provider packet 연결
- 선언된 일반 액화수소 시설 사고 family 전체에 대한 누락 branch 정리
- qualified provider evidence와 독립 실험·실증 물리검증 연결
- 다중 설비·다중 annual condition에서의 중복 asset/event 검사
- 문헌 빈도 p05/p95 및 사고범위 누락에 대한 시설 순위 민감도 보고
- IJHE 제출용 계산 정확도와 처리시간 데이터셋 작성

현 단계의 목표는 “실시간 결과를 시설 ledger에 전달할 수 있는 검증된 중간 연결부”
이며 “완전한 시설 연간 위험도”가 아니다.
