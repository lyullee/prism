# PRISM v0.6.0 사고군 공백 매트릭스

이 문서는 **수치 계산이 안 된 사고**와 **수치 계산은 됐지만 자격화된 증거가 없는 사고**를 구분하기 위한 원장 설명서다.

## 현재 판정

- 사건 34개, 사례 44개
- 수치 결과가 있는 사례: 44개
- 수치 결과가 없는 사례: 0개
- 자격화 증거가 보류된 사례: 29개
- 사고군: 12개 (수치 공백 0개, 자격화 공백 8개, 완전 4개)

현재 원장은 수치 공백을 0건으로 기록한다. `PARTIAL`은 대부분 `EXECUTED_OPERATOR_LIMITED` 사례 때문에 발생하며, 이 결과를 qualified facility QRA로 승격하지 않는다.

사고군 행은 하나의 사례가 여러 사고군(예: 배관 홀과 액체 2상)에 동시에 포함될 수 있는 **중복 관점**이다. 행별 숫자를 더하지 말고, 전체 사례 수와 증거 보류 수는 위의 상위 장부 숫자를 사용한다.

## 사고군별 장부

| 사고군 | 공백 분류 | 사례 | 수치 실행 | 증거 보류 | 상태별 사례 수 |
|---|---|---:|---:|---:|---|
| `vessel_hole` | `QUALIFICATION_EVIDENCE_WITHHELD` | 5 | 5 | 5 | EXECUTED_OPERATOR_LIMITED=5 |
| `pipe_hole` | `QUALIFICATION_EVIDENCE_WITHHELD` | 25 | 25 | 15 | EXECUTED=10, EXECUTED_OPERATOR_LIMITED=15 |
| `valve_hole` | `QUALIFICATION_EVIDENCE_WITHHELD` | 5 | 5 | 5 | EXECUTED_OPERATOR_LIMITED=5 |
| `vent_hole` | `COMPLETE` | 1 | 1 | 0 | EXECUTED=1 |
| `pump_hole` | `QUALIFICATION_EVIDENCE_WITHHELD` | 2 | 2 | 2 | EXECUTED_OPERATOR_LIMITED=2 |
| `vaporizer_hole` | `COMPLETE` | 1 | 1 | 0 | EXECUTED=1 |
| `reliquefier_hole` | `COMPLETE` | 1 | 1 | 0 | EXECUTED=1 |
| `liquid_two_phase` | `QUALIFICATION_EVIDENCE_WITHHELD` | 17 | 17 | 17 | EXECUTED_OPERATOR_LIMITED=17 |
| `inventory_depletion` | `QUALIFICATION_EVIDENCE_WITHHELD` | 28 | 28 | 17 | EXECUTED=11, EXECUTED_OPERATOR_LIMITED=17 |
| `inventory_over_600s` | `COMPLETE` | 1 | 1 | 0 | EXECUTED=1 |
| `two_sided_rupture` | `QUALIFICATION_EVIDENCE_WITHHELD` | 2 | 2 | 2 | EXECUTED_OPERATOR_LIMITED=2 |
| `vertical_handoff` | `QUALIFICATION_EVIDENCE_WITHHELD` | 10 | 10 | 10 | EXECUTED_OPERATOR_LIMITED=10 |

## 분류 의미

- `COMPLETE`: 선언된 사고군의 사례가 모두 수치 실행됐고, 이 장부의 사례 수준에서 자격화 보류가 없다.
- `QUALIFICATION_EVIDENCE_WITHHELD`: 수치 결과는 있으나 운영자 제한·합성 경계·독립 검증 부족 때문에 시설 QRA 증거로 승격할 수 없다.
- `NUMERICAL_CASE_MISSING`: 방출·피해 수치가 없는 사례다. 시설 위험 합계에 넣지 않고, 상태 스냅샷과 provider 결과를 보충한 뒤 다시 계산해야 한다.

## 다음 단계

1. `QUALIFICATION_EVIDENCE_WITHHELD` 사고군에는 exact provider packet과 독립 물리검증 근거를 추가한다.
2. `NUMERICAL_CASE_MISSING` 사고군이 생기면 해당 사례를 시설 IR/F-N에 포함하지 않고 먼저 계산을 닫는다.
3. 모든 사고군의 `gap_class`가 `COMPLETE`가 되고, 독립 물리검증과 qualified provider gate가 통과될 때만 strict facility QRA로 승격한다.

원본 장부: `results/20261030/native_full_scope_union_assessment_state_atoms/scope_matrix.json`
