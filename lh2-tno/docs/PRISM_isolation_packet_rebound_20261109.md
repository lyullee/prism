# PRISM isolation-success packet 재결합 진단 (2026-11-09)

## 목적

기존 일반 LH2 24개 사건 캠페인에는 배관·밸브·펌프의 `reviewed_isolation_success` packet이 별도 보관되어 있었지만, 전체 시설 캠페인에는 `synthetic_diagnostic_horizon` packet이 연결되어 있었다. 이번 단계에서는 기존 packet을 새로 만들거나 현장 차단확률을 추정하지 않고, event ID·설비 ID·사고 포트가 정확히 일치하는 12개 packet만 전체 캠페인에 재결합했다.

대상은 다음과 같다.

- 이송배관 누출 5개: `AREA_0.01%`부터 `AREA_100%`
- 이송밸브 누출 5개: `AREA_0.01%`부터 `AREA_100%`
- 이송펌프 누출 2개: `G1`, `G2`

재결합은 `scripts/build_isolation_packet_evidence_overlay.py`가 수행한다. packet event ID, component ID, 사고 port ID, provider schema를 확인하지 못하면 즉시 중단한다.

## 확인된 종료 경계

| 사고군 | 기존 종료근거 | 재결합 후 종료근거 |
|---|---|---|
| 이송배관 5건 | `synthetic_diagnostic_horizon` | `reviewed_isolation_success` |
| 이송밸브 5건 | `synthetic_diagnostic_horizon` | `reviewed_isolation_success` |
| 이송펌프 2건 | `synthetic_diagnostic_horizon` | `reviewed_isolation_success` |
| 나머지 12건 | 기존 packet 유지 | 기존 packet 유지 |

재결합 후 시설 ledger의 종료근거 집계는 다음과 같다.

- `reviewed_isolation_success`: 12건
- `inventory_depletion`: 8건
- `inventory_over_600s`: 1건
- `emergency_relief_discharge`: 1건
- `two_sided_rupture`: 2건
- `synthetic_diagnostic_horizon`: 0건

따라서 전체 ledger에는 이제 고정 진단시계만 있는 것이 아니라, provider가 명시한 차단 성공·관찰시간과 질량 장부가 함께 전달된다.

## 결과와 제한

새 campaign은 24개 case·96개 risk atom을 다시 계산했다. 포트 결합은 24/24로 유지됐고, 시설 조건부 IR은 이전과 같은 `6.08e-05/yr`였다. case 상태는 `EXECUTED` 4건, `EXECUTED_OPERATOR_LIMITED` 20건이다.

여기서 12개 종료근거가 바뀌었는데도 operator-limited 수가 줄지 않은 이유는 명확하다. 해당 packet의 source provenance가 합성 또는 screening 상태이며, 현장 차단 신뢰도·실제 actuator 응답·독립 물리검증을 제공하지 않기 때문이다. 따라서 `reviewed_isolation_success`는 provider가 계산한 진단 종료 경계이지, 현장 요구시 성공확률이나 qualified provider 증거로 해석하지 않는다.

이번 결과는 다음 연결을 검증한다.

```text
문헌 사고빈도
  → 명시적 사고 포트
  → isolation-success provider packet
  → 차단 후 0 유량 관찰
  → 방출 지속시간·질량 장부
  → SLABx-LH2/SLABx 피해영향
  → 시설 IR/F-N 원장
```

IJHE 완료 감사는 24개 검사 중 19개 통과·5개 차단인 `INCOMPLETE_EVIDENCE`로 남았다. 남은 차단은 qualified provider packet, 전체 방출경계의 독립 증거, 주요 사고군 범위, 독립 물리검증, 엄격 시설 IR/F-N 승격이다.

## 산출물

- overlay 도구: `scripts/build_isolation_packet_evidence_overlay.py`
- overlay 입력: `examples/generic_lh2_isolation_packet_overlay.json`
- overlay evidence: `results/20261109/generic_scope_packet_evidence_source_state_closure_rebound_isolation_overlay.json`
- 재결합 campaign: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound_isolation_rebound_port_bound.json`
- 재결합 provenance: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound_isolation_rebound.provenance.json`
- 재계산 결과: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_port_bound_isolation_rebound_result.json`
- 시설 평가: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_assessment.json`
- 조건부 위험 view: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_conditional_risk_view.json`
- chain 감사: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_chain_closure_audit.json`
- IR/F-N 감사: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_aggregate_audit.json`
- 설비 기여 감사: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_component_audit.json`
- 빈도 불확실성 감사: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_frequency_uncertainty_audit.json`
- IJHE 완료 감사: `results/20261109/ijhe_completion_audit_conditional_facility_isolation_rebound_with_hazop_multiequipment.json`

정확한 결론은 **“12개 isolation-success provider packet을 전체 시설 계산에 연결해 종료·차단·질량 장부의 전달을 확인했지만, packet의 합성 provenance 때문에 엄격 시설 QRA를 승격하지 않았다”**이다.

## 다음 증거 수집용 장부

이번 isolation-rebound assessment에서 생성한 `facility_evidence_request`는 12개 사고군과 24개 strict case를 event ID 기준으로 펼친다. 각 요청에는 정확한 component·port·opening·position, provider 소스/결과 digest, provider-owned 시간 이력, 종료근거, 재고·에너지 잔차, 차단 관찰, 독립 검증 자료가 필요한 이유가 들어 있다.

- 증거 요청 장부: `results/20261109/generic_scope_closure_rebound_facility_isolation_rebound_evidence_request.json`
- 상태: `OPEN_EVIDENCE_REQUEST`
- strict case 요청: 24개
- 현 단계에서 자동 빈도 추론: 금지
- 현장 차단확률·provider 적격성 자동 생성: 금지

이 장부가 다음 외부 데이터 연결의 입력 목록이며, 현재 합성 packet을 실제 설비 자료로 대체하기 전에는 시설 QRA 승격을 허용하지 않는다.
