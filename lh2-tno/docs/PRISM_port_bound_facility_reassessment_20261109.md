# PRISM 포트 결합 후 일반 LH2 시설 재평가 (2026-11-09)

## 목적

최신 일반 액화수소시설 24개 사건 캠페인에 설비별 사고 포트를 명시적으로 결합하고, 그 결합이 방출 packet·risk atom·시설 IR/F-N 원장까지 보존되는지 다시 확인했다. 사건 이름이나 provider 출력만 보고 포트를 추정하지 않고, 분석자가 제공한 crosswalk와 설비 manifest가 정확히 일치할 때만 결합했다.

## 이번에 새로 닫힌 것

`examples/generic_lh2_frequency_port_crosswalk.json`을 사용해 다음을 실행했다.

```powershell
python scripts/bind_frequency_port_crosswalk.py `
  --campaign results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff.json `
  --crosswalk examples/generic_lh2_frequency_port_crosswalk.json `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --output results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound.json `
  --audit results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound_audit.json
```

그 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| 생성 사건 | 24 |
| 명시적 사고 포트가 있는 사건 | 24 |
| 포트 미결합 사건 | 0 |
| provider 요청 포트 불일치 | 0 |
| 빈도 추론 | 수행하지 않음 |
| provider packet 승격 | 수행하지 않음 |
| facility QRA 승격 | 수행하지 않음 |

재실행된 24개 fresh physics case에서도 포트 결합을 유지했다. 시설 평가의 `frequency_port_binding`은 `ALIGNED`, 사건·case·risk atom 포트 mismatch는 모두 0건이다. 따라서 이전의 “시설 사건 원장에 명시적 빈도 포트가 없다”는 차단은 이 진단 캠페인에서는 제거됐다.

## 방출부터 시설 위험까지의 현재 결과

```text
설비 상태/사고 사건
  → 명시적 사고 포트 crosswalk
  → provider 방출 packet
  → 방출 지속시간·차단·재고 질량 장부
  → pool/rainout 및 SLABx-LH2/SLABx 확산
  → 점화·화재·폭발 피해
  → TNO 인체피해
  → risk atom
  → 설비별 기여도
  → 시설 IR/F-N
```

이번 재실행 결과는 `PARTIAL_FACILITY_SCOPE`이다. worker-01의 조건부 진단 IR은 `6.08e-05/yr`로 저장·재합산됐고, 24개 사건·96개 risk atom이 있다. 문헌 빈도 5개 시나리오도 새 ledger에 대해 다시 계산했으며, 빈도 추론이나 시설 credible interval은 만들지 않았다.

| 처리시간 지표 | 값 |
|---|---:|
| 사건 수 | 24 |
| case 중앙값 | 4,744.94 ms |
| case p95 | 18,988.05 ms |
| case p99 | 22,080.23 ms |
| 가장 긴 case | 22,903.58 ms |
| 전체 campaign | 164,593.08 ms |

이 시간은 한 번의 campaign에서 관찰한 값이며, 반복 실행 기반 SLA나 fresh physics 1 Hz 보장을 뜻하지 않는다.

## 독립 감사

다음 감사는 새 port-bound facility ledger에서 모두 통과했다.

- 방출 packet → 피해 → 시설 IR/F-N chain: `PARTIAL_DIAGNOSTIC_CHAIN_CLOSED`, 24/24
- 시설 IR/F-N 재합산: `FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC`, mismatch 0
- 설비 기여도·순위 재합산: `FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC`, mismatch 0
- 문헌 빈도 불확실성 재계산: `FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC`, mismatch 0
- 포트 결합: `FREQUENCY_PORT_CROSSWALK_BOUND` 및 시설 평가 `ALIGNED`

이 감사들은 저장 원장의 연결성과 산술을 닫는다. 합성 manifest와 screening provider를 실제 시설의 qualified release 근거로 바꾸지는 않는다.

## 아직 엄격 QRA를 열지 않은 이유

최신 IJHE 완료 감사는 24개 검사 중 19개 통과, 5개 차단인 `INCOMPLETE_EVIDENCE`다. 남은 차단은 다음 다섯 가지다.

1. 선언한 모든 사건의 방출 종료·차단·재고 경계가 qualified evidence로 닫히지 않았다.
2. 현재 provider 방출은 합성 또는 screening 범위이며 qualified packet이 0개다.
3. provider worklist에 exact packet 또는 완전한 구조 진단 catalog가 없는 항목이 남아 있다.
4. 선언한 주요 사고군 중 일부가 부분 범위 또는 증거 제한 상태다.
5. 위 조건 때문에 시설 전체 IR/F-N은 여전히 보류한다.

따라서 이번 단계의 정확한 표현은 **“사건별 빈도 포트 결합을 명시적으로 닫고, 포트가 보존된 방출→피해→시설 IR/F-N 진단 원장을 재계산했다. 합성 provider·미완료 방출경계·독립 물리검증·사고범위 증거 때문에 엄격 시설 QRA 승격은 아직 보류한다.”**이다.

## 산출물

- 포트 결합 캠페인: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound.json`
- 포트 결합 감사: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound_audit.json`
- 포트 결합 후 fresh physics 결과: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound_result.json`
- 포트 결합 후 시설 평가: `results/20261109/generic_scope_closure_rebound_facility_port_bound_assessment.json`
- 조건부 위험 view: `results/20261109/generic_scope_closure_rebound_facility_port_bound_conditional_risk_view.json`
- chain 감사: `results/20261109/generic_scope_closure_rebound_facility_port_bound_chain_closure_audit.json`
- IR/F-N 감사: `results/20261109/generic_scope_closure_rebound_facility_port_bound_aggregate_audit.json`
- 설비 기여 감사: `results/20261109/generic_scope_closure_rebound_facility_port_bound_component_audit.json`
- 빈도 불확실성 감사: `results/20261109/generic_scope_closure_rebound_facility_port_bound_frequency_uncertainty_audit.json`
- IJHE 완료 감사: `results/20261109/ijhe_completion_audit_conditional_facility_port_bound_with_hazop_multiequipment.json`

