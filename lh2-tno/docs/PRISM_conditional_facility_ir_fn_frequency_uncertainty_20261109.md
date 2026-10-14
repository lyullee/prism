# PRISM 조건부 시설 IR/F-N 연결 및 빈도 불확실성 결과 (2026-11-09)

## 이번 단계에서 닫힌 연결

최신 24개 일반 LH2 사건 캠페인을 시설 원장에 넣어 다음 계산을 한 번의 평가 문서로 묶었다.

`설비별 방출 패킷` → `방출 종료·질량 장부` → `풀/rainout` → `SLABx-LH2/SLABx 확산` → `점화 분기` → `화재·폭발 피해` → `TNO 인체피해` → `risk atom` → `시설 IR/F-N`.

이번 원장에는 24개 사건, 24개 case, 96개 risk atom이 있다. 기상과 인구는 하나의 명시적 조건(`synthetic-generic-worker-west-3ms`, worker-01)으로 계산했고, 점화는 `direct_fire`, `delayed_flash_fire`, `delayed_explosion`, `no_ignition` 네 분기를 모두 기록했다.

## 계산 결과

| 항목 | 결과 |
|---|---:|
| 평가 상태 | `PARTIAL_FACILITY_SCOPE` |
| 조건부 시설 IR/F-N | 계산됨 |
| 엄격한 시설 전체 IR/F-N | 보류 |
| 조건부 IR (worker-01) | `6.08e-05/yr` |
| F/N 기준 | `N ≥ 1` expected death |
| F/N 곡선 | `CURVE_AVAILABLE` |
| 수치 실행 사건 | 24 / 24 |
| 조건부 계산 사건 | 24 / 24 |
| 엄격 미인정 사건 | 20 |
| 공급자 적격 packet | 0 / 24 |
| 시설 QRA 승격 | `false` |

조건부 IR/F-N은 코드가 저장된 risk atom을 합산해 보여주는 **진단값**이다. 엄격 미인정 사건 20건을 실제 위험이 0이라고 처리하지 않고, 계산값과 증거 상태를 분리해 보존한다.

## 설비별 진단 순위

| 순위 | 설비 | 조건부 peak IR | 엄격 미인정 case |
|---:|---|---:|---:|
| 1 | `storage-tank-01` | 4.68e-05/yr | 5 |
| 2 | `ambient-vaporizer-01` | 1.4e-05/yr | 1 |
| 3 | `liquid-transfer-line-01` | 0/yr | 5 |
| 4 | `liquid-transfer-pump-01` | 0/yr | 2 |
| 5 | `pressure-relief-vent-01` | 0/yr | 0 |
| 6 | `reliquefier-01` | 0/yr | 2 |
| 7 | `transfer-valve-01` | 0/yr | 5 |

현재 합성 조건에서 저장탱크와 기화기가 양의 worker-01 IR 기여를 보였다. 이 순위는 방호 우선순위를 정하는 진단용이며, 실제 시설 형상·수신기·인구·공정 상태를 대체하지 않는다.

## 문헌 빈도 불확실성

물리 계산을 다시 실행하지 않고, 저장된 risk atom에 문헌 중앙값·p05·p95 시나리오를 재가중했다. 빈도를 센서에서 학습하거나 새 사고빈도를 만들지 않았다.

| 시나리오 | worker-01 조건부 IR | 저장탱크 순위 | 기화기 순위 |
|---|---:|---:|---:|
| `generic-lh2-published-central` | 6.08e-05/yr | 1 | 2 |
| `generic-lh2-literature-low` | 1.66916e-05/yr | 2 | 1 |
| `generic-lh2-literature-high` | 0.000827801/yr | 1 | 2 |
| `generic-lh2-independent-low` | 1.66916e-05/yr | 2 | 1 |
| `generic-lh2-independent-high` | 0.000827801/yr | 1 | 2 |

- 낮은 문헌 시나리오: `1.66916e-05/yr`
- 중앙 시나리오: `6.08e-05/yr`
- 높은 문헌 시나리오: `0.000827801/yr`
- 자산 순위 안정성: 계산됨. 중앙·높은 경우 저장탱크가 1위이고, 낮은 경우 기화기가 1위다.
- 시설 credible interval: 만들지 않음(`facility_credible_interval=false`). 독립 사건·자산 상관과 실제 적용 가능성 자료가 없기 때문이다.

## 독립 재계산 감사

| 감사 | 결과 |
|---|---|
| 24개 사건 packet chain | `PARTIAL_DIAGNOSTIC_CHAIN_CLOSED` (24/24) |
| 시설 IR/F/N 재합산 | `FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC`; IR mismatch 0, F/N mismatch 0 |
| 설비 기여·순위 재합산 | `FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC`; mismatch 0 |
| 빈도 불확실성 재계산 | `FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC`; mismatch 0 |

이 네 가지 감사는 저장된 결과가 서로 맞는지 확인한다. 감사 통과는 공급자 모델이 실제 설비를 대표한다는 뜻이 아니며, 독립 실험 검증이나 시설 QRA 자격을 부여하지 않는다.

## 파일

- 시설 평가: `results/20261109/generic_scope_closure_rebound_facility_assessment.json`
- 조건부 위험 요약: `results/20261109/generic_scope_closure_rebound_conditional_risk_view.json`
- 방출→피해→시설 chain 감사: `results/20261109/generic_scope_closure_rebound_chain_closure_audit.json`
- IR/F-N 독립 감사: `results/20261109/generic_scope_closure_rebound_aggregate_audit.json`
- 설비 기여 독립 감사: `results/20261109/generic_scope_closure_rebound_component_audit.json`
- 빈도 불확실성 독립 감사: `results/20261109/generic_scope_closure_rebound_frequency_uncertainty_audit.json`
- 빈도 시나리오 장부: `examples/generic_lh2_mixed_frequency_scenarios_no_inference.json`

## 아직 남은 엄격한 조건

1. 20개 operator-limited 사건에 대해 실제 설비의 종료·차단·재고 경계와 공급자 적격 sidecar를 확보한다.
2. 각 사고가 실제 시설의 사고 포트·좌표·공정상태에 맞는지 검토한다.
3. SLABx-LH2와 근접장에 대한 독립 hold-out 물리검증을 추가한다.
4. 실제 연간 기상·인구·장애물·수신기 자료를 연결한다.
5. 위 조건이 충족된 뒤에만 `facility_total_risk_available`와 시설 IR/F-N 승격을 허용한다.

따라서 이번 단계의 정확한 표현은 **“조건부 시설 IR/F-N과 문헌 빈도 민감도까지 연결·독립 재계산했으며, 엄격한 시설 QRA 승격은 증거 부족으로 보류”**이다.


## 이번 단계의 IJHE 완료 감사

이번 시설 평가를 최신 완료 감사기에 넣은 결과는 `INCOMPLETE_EVIDENCE`이며 23개 검사를 수행했다.

통과한 핵심 진단은 방출→최종피해 체인 연결, 조건부 시설 IR/F-N, IR/F-N 독립 재합산, 설비별 기여도 독립 재합산, 문헌 빈도 불확실성 독립 재계산, 처리시간 기록이다. 남은 차단 항목은 시설 빈도 포트의 명시적 검토 연결, 20개 operator-limited 방출경계, 실제 qualified provider packet, 일부 선언 사고군의 엄격한 범위, 엄격한 시설 IR/F-N 승격이다.

- 완료 감사: `results/20261109/ijhe_completion_audit_conditional_facility_rebound.json`
- 감사 상태: `INCOMPLETE_EVIDENCE`
- 차단 검사는 자동으로 0위험으로 바꾸지 않고, 증거 요청과 함께 보존한다.
