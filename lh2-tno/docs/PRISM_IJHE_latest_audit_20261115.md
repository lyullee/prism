# PRISM v0.6.2 IJHE 최신 감사 기준 (2026-11-15)

현재 권위 union은 일반 옥외 액화수소 시설의 **34개 event, 44개 case,
176개 risk atom**이다. 설비 상태→HAZOP/운전 모드→문헌 빈도→provider 방출
경계→지속시간·재고·차단→SLABx-LH2/대기확산→점화·피해→조건부 시설 집계의
연결을 보존한다. 수직 handoff 다섯 event는 provider 소유 유한 재고 이력을
재결합했고, inventory-depletion 다섯 event와 함께 34/34 event에 명시적 사고
포트가 있다.

권위 감사 파일:

[`ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`](../results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json)

현재 결과는 **53개 검사 중 48개 PASS, 5개 BLOCKED, `INCOMPLETE_EVIDENCE`**다.
차단 검사에는 전체 방출 종료 경계, 실제 qualified provider packet, 선언 사고범위의 독립 물리검증, 시설 전체 IR/F-N, 44개 case의 exact qualified packet coverage가 포함된다.

## 최신 연결 결과

| 확인 항목 | 결과 |
|---|---:|
| union event / case / risk atom | 34 / 44 / 176 |
| HAZOP event identity | 34/34 bound |
| frequency port binding | 34/34 scoped, unbound 0, mismatch 0 |
| 수직 handoff | 5 event, 10 case, `inventory_depletion` 종료 |
| provider 종료 evidence | 35 provider row, 34 event ID, 32 case 사용, 2 invalid case |
| numerical closure | 32 closed, 29 operator-review, 12 open |
| strict boundary eligible | 3; 41 blocked |
| 시설 IR/F-N 승격 | `false` |

`NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED`는 방출 시간·초기/누적/잔여
재고·질량 잔차가 수치상 닫혔다는 뜻이다. 운영자 제한과 synthetic provider
입력은 남아 있으므로 qualified release 또는 시설 QRA를 뜻하지 않는다.

## 주요 산출물

- [최신 union 시설평가](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json)
- [케이스별 방출 경계 감사](../results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json)
- [조건부 시설 risk view](../results/20261115/conditional_facility_risk_view_with_release_trace.json)
- [provider 종료 증거 catalog](../results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff_isolation_current.json)
- [provider replay 추적성 기록](PRISM_provider_termination_variant_replay_20261115.md)
- [수직 종료 증거 검색](../results/20261115/vertical_inventory_handoff_termination_evidence_search.json)
- [수직 handoff 개발 기록](PRISM_vertical_inventory_handoff_20261115.md)

## 재현 및 해석

전체 재현 명령은 [수직 handoff 재고소진 연결 기록](PRISM_vertical_inventory_handoff_20261115.md)에 모았다.
공급자 source tree 지문은 실행 시점에 새로 계산해 오래된 backend artifact가
현재 provider 코드를 잘못 승인하지 않도록 했다. 수직 handoff 자체는
`synthetic provider vertical-to-horizontal handoff; not independently validated`
로 남긴다.

현재 범위에서 현장 사고빈도 수집·센서 기반 빈도 학습·실내·폭굉·전체 도미노는
수행하지 않는다. 지원되지 않은 사고는 다른 사고군으로 대체하지 않고
`PARTIAL`, `BLOCKED_REVIEW`, `UNCOMPUTED` 또는 증거요청으로 보존한다.

## 2026-11-15 facility-handoff supplement

The full audit was rerun with the reconstructed inspection-center facility handoff as an optional diagnostic input. The resulting record is [`ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound_with_inspection_center_handoff.json`](../results/20261115/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound_with_inspection_center_handoff.json). It contains 45 checks: 41 PASS and 4 BLOCKED. The new `diagnostic_inspection_center_facility_ijhe_handoff` check is PASS and diagnostic-only; it does not weaken the four strict qualification gates. See [`PRISM_IJHE_facility_handoff_audit_20261115.md`](PRISM_IJHE_facility_handoff_audit_20261115.md) for the detailed interpretation and reproduction path.
