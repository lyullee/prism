# PRISM v0.6.3 IJHE 최신 감사 기준 (2026-11-15)

현재 권위 union은 일반 옥외 액화수소 시설의 **34개 event, 44개 case,
176개 risk atom**이다. 설비 상태→HAZOP/운전 모드→문헌 빈도→provider 방출
경계→지속시간·재고·차단→SLABx-LH2/대기확산→점화·피해→조건부 시설 집계의
연결을 보존한다. 수직 handoff 다섯 event는 provider 소유 유한 재고 이력을
재결합했고, inventory-depletion 다섯 event와 함께 34/34 event에 명시적 사고
포트가 있다.

권위 감사 파일:

[`ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`](../results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json)

현재 공식 최신 결과는 **55개 검사 중 50개 PASS, 5개 BLOCKED, `INCOMPLETE_EVIDENCE`**다.
이번 기록에는 최신 release-boundary 재감사와 44개 facility case의 qualified-provider packet coverage 검사가 포함되어 있다. 또한 예측 상태 quantitative-evidence coverage와 fail-closed facility-campaign gate를 진단 검사로 포함한다. 차단 검사는 전체 방출 종료 경계, 실제 qualified provider packet, 선언 사고범위의 provider/독립 물리검증, 시설 전체 IR/F-N, 전체 case의 qualified packet coverage다.

## 최신 연결 결과

The latest audit consumes the inspection-center facility handoff as a diagnostic-only check. Its 12 structural checks pass; it does not alter the five strict gates.

| 확인 항목 | 결과 |
|---|---:|
| union event / case / risk atom | 34 / 44 / 176 |
| HAZOP event identity | 34/34 bound |
| frequency port binding | 34/34 scoped, unbound 0, mismatch 0 |
| release case frequency binding | 44/44 case rows bound to event/port literature metadata, unbound 0; 35/44 have event-level P05/P95 intervals |
| 수직 handoff | 5 event, 10 case, `inventory_depletion` 종료 |
| provider 종료 evidence | 35 provider row, 34 event ID, 42 case 사용, 2 invalid case |
| numerical closure | 42 closed, 29 operator-review, 2 open |
| strict boundary eligible | 13; 31 blocked |
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

The current authoritative union record is [`ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`](../results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json). It contains 55 checks: 50 PASS and 5 BLOCKED. The additional `diagnostic_forecast_facility_campaign_evidence_gate` check confirms that the two forecast requests are still withheld because quantitative evidence is missing; it does not open downstream facility aggregation. The separate receptor-geometry and inspection-center handoff records remain diagnostic-only inputs verified by the latest-audit pointer checker; they do not weaken the five strict gates. The earlier 49-check `..._with_receptor_geometry.json` record is retained as a historical supplement. See [`PRISM_IJHE_facility_handoff_audit_20261115.md`](PRISM_IJHE_facility_handoff_audit_20261115.md) for the detailed interpretation and reproduction path.

The release-boundary case rows now carry the copied literature frequency and source digest. All 44 rows are event/port-bound, while 35 rows also carry event-level P05/P95 metadata. The other 9 rows intentionally retain their published point rates without an invented interval; their uncertainty is represented only by the separate five-scenario sensitivity audit.

The provider-termination catalog and release-boundary ledger were refreshed
after the emergency-relief contract update. The VentStack G1 row now reaches
the current emergency-relief validator and is rejected specifically for its
missing provider setpoint, capacity, completion, and source-operator fields;
the bounded G2 row remains explicitly open as `inventory_over_600s`.

통합 감사 바인더는 이제 uncertainty ledger, provider worklist, adapter registry,
facility assessment, domain-recovery 기록을 모두 이름으로 전달한다. 긴 선택 인자
호출에서 provider worklist가 빈도 자료로 잘못 들어가는 회귀를 막기 위한 변경이며,
계약 테스트는 `tests/test_bind_native_full_scope_union_evidence.py`에 있다. union을
다시 만들 때는 `--domain-recovery-audit
results/20261024/domain_recovery_audit_flammability_gate_v2.json`을 함께 전달한다.
