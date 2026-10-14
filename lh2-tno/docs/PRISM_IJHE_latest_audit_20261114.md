# PRISM v0.6.0 IJHE 최신 감사 기준 (2026-11-14)

## 권위 실행

대상은 일반 옥외 액화수소 시설이다. 검사센터 전용 설비명이나 현장 빈도 학습을 사용하지 않는다.

- union event 34개
- numerical case 44개
- risk atom 176개
- HAZOP event binding 34/34
- base native packet 24/24 exact
- state snapshot echo 24/24
- 조건부 IR/F-N 계산 경로 실행

권위 결과는 [`ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json`](../results/20261114/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json)이다.

## 감사 입력

| 입력 | 역할 | 현재 의미 |
|---|---|---|
| `campaign_result.json` | 설비 event·case·risk atom | 34 event, 44 case, 176 atom의 진단 연결 |
| `verification.json` (native packet catalog) | exact native packet 구조 | 24/24 exact, qualification 승격 아님 |
| `isolation_branch_audit.json` | 설비별 차단·zero-flow branch | 14개 `reviewed_isolation_success` |
| `slabx_lh2_validation_audit_recomputed.json` | SLABx-LH2 pool/dispersion 근거 | 제한 component evidence |
| `dynamiclh2poolx_evidence_audit.json` | JUEL hold-out·HSE Test 6 반경/질량수지 근거 | 소스 해시 변화가 기록된 제한 pool/spreading component evidence; 방출·대기확산·시설 QRA 검증 아님 |
| `validation_evidence_matrix_with_provider_intake.json` | 물리·관측·provider 검증근거 경계 | 시설 QRA 보류를 명시 |
| `external_provider_validation_intake.json` | 외부 방출·열역학 검증 자료 분류 | 8건 모두 provider 승격 차단 |
| `release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json` | 전체 union case별 방출 종료·차단·재고 승격 표 | 44 case 중 3개 국소 경계 통과, 41개 보류; 시설 QRA 승격 0 |
| `conditional_facility_risk_view_with_release_trace.json` | 조건부 시설 IR/F-N, case-keyed 방출→risk trace, 문헌 빈도 trace | 44 case·176 atom, 5개 빈도 시나리오·순위 안정성; diagnostic-only, promotion false |
| `hazop_provider_bound_integrated_risk.json` | 현재 모니터링·예측 상태의 HAZOP→provider·SLABx-LH2→시설 handoff | current 1건·forecast 1건 정량평가와 campaign handoff 연결 PASS; synthetic/provider-bound 진단 전용 |
| `support_center_hazop_operating_mode_evidence_audit.json` | 검사센터 운전순서에서 일반 모드·HAZOP 정성 근거 추출 | 52개 모드 행; 빈도·방출 생성 없음 |
| `support_center_reviewed_signal_unit_evidence.json` | 문서 anchor 기반 일부 PT/TT 단위 확인 | 부분 근거; 미검토 tag·calibration은 보류 |
| `inspection_center_observed_hazop_runtime_audit.json` | 실측 상태 + 명시적 운전 모드의 HAZOP 선택 | 3개 관측 설비 모드 선택; state-only |
| `inspection_center_observed_hazop_provider_event_binding.json` | 관측 HAZOP scenario와 문헌 event identity 연결 | 3/3 명시적 binding; 빈도 할당은 별도 |
| `inspection_center_observed_hazop_provider_consequence_chain_with_storage_vaporizer_isolation_success.json` | 관측 HAZOP→provider→SLABx-LH2 진단 chain | 3개 시나리오 실행; synthetic/provider-bound 진단 전용 |
| `observed_hazop_storage_isolation_branch_evidence.json` / `observed_hazop_vaporizer_isolation_branch_evidence.json` | 저장탱크·기화기 차단 성공 branch와 zero-flow evidence | explicit controls·branch probability·diagnostic gate 확인 |
| `facility_evidence_request.json` | case/family별 누락 증거 요청 | 44 case와 12 family를 추적 |
| `native_generic_scope_packet_evidence_qualification_readiness_v14.json` | provider qualification readiness | 24/24 `BLOCKED_REVIEW` |

## 재현 명령

```powershell
python scripts/build_ijhe_completion_audit.py `
  --current-status CURRENT_STATUS.json `
  --scope-matrix results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/scope_matrix.json `
  --campaign-result results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/campaign_result.json `
  --uncertainty-result results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json `
  --provider-worklist results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/provider_worklist.json `
  --facility-assessment results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json `
  --release-boundary-case-audit results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json `
  --conditional-facility-release-trace results/20261114/conditional_facility_risk_view_with_release_trace.json `
  --state-snapshot-binding-audit results/20261114/base_state_snapshot_binding_audit_port_bound.json `
  --native-scope-packet-catalog-verification results/20261111/native_generic_scope_packets_isolation/verification.json `
  --native-scope-isolation-branch-catalog-audit results/20261111/native_generic_scope_packets_isolation/isolation_branch_audit.json `
  --native-isolation-catalog-facility-chain-verification results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/verification.json `
  --validation-evidence-matrix results/20261114/validation_evidence_matrix_with_provider_intake.json `
  --slabx-validation-evidence results/20261106/slabx_lh2_validation_audit_recomputed.json `
  --facility-evidence-request results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_evidence_request.json `
  --diagnostic-worklist-evidence results/20261024/native_generic_scope_packet_evidence_qualification_readiness_v14.json `
  --hazop-integrated-risk results/20261014/hazop_provider_bound_integrated_risk.json `
  --hazop-operating-mode-evidence results/20261014/support_center_hazop_operating_mode_evidence_audit.json `
  --reviewed-signal-unit-evidence results/20261014/support_center_reviewed_signal_unit_evidence.json `
  --observed-hazop-runtime-audit results/20261110/inspection_center_observed_hazop_runtime_audit.json `
  --observed-hazop-provider-binding results/20261110/inspection_center_observed_hazop_provider_event_binding.json `
  --observed-hazop-provider-consequence-chain results/20261110/inspection_center_observed_hazop_provider_consequence_chain_with_storage_vaporizer_isolation_success.json `
  --observed-hazop-storage-isolation-branch-evidence results/20261110/observed_hazop_storage_isolation_branch_evidence.json `
  --observed-hazop-vaporizer-isolation-branch-evidence results/20261110/observed_hazop_vaporizer_isolation_branch_evidence.json `
  --hazop-selection-event-binding results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/hazop_selection_event_binding.json `
  --hazop-extension-mode-evidence-request results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/hazop_extension_mode_evidence_request.json `
  --output results/20261114/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json
```

## 판정

현재 결과는 42개 검사 중 38개 `PASS`, 4개 `BLOCKED`, 전체 상태 `INCOMPLETE_EVIDENCE`이다.

`dynamiclh2poolx_evidence_audit.json`은 JUEL water Trial 4와 aluminium Trial 6의 hold-out 반경 비교(각 100% video-band coverage), HSE Test 6의 종료 반경·건조 시점·질량수지 잔차를 보존한다. 현재 소스와 외부 evidence snapshot의 해시가 달라 `CURRENT_SOURCE_REPLAY_WITH_EXTERNAL_EVIDENCE_DRIFT`로 기록되며, 이 근거는 pool/spreading 구성요소의 제한 검증만 지지한다. 설비 사고 방출, 차단·재고 소진, 대기 농도/LFL, 점화·IR/F-N의 독립 검증으로 확장하지 않는다.

통과한 진단 연결은 다음을 뜻한다.

- 설비 상태 snapshot이 event와 case로 전달된다.
- 방출량·지속시간·차단·재고 장부가 피해계산 입력으로 전달된다.
- SLABx-LH2 확산·pool 결과가 점화·피해 risk atom으로 전달된다.
- 문헌 빈도 불확실성과 처리시간이 별도 장부로 기록된다.
- 조건부 view가 5개 문헌 빈도 시나리오, 분위수 출처, 상관 가정, 설비·사고군
  순위 안정성, 명시적 포트 결합과 빈도 추론 금지를 전달한다.
- 각 빈도 시나리오에서 30개 미충족·불완전 case 행과 29개 고유 case key를
  상태별로 보존한다. `EXECUTED_OPERATOR_LIMITED`와
  `EXECUTED_DOMAIN_INCOMPLETE`를 `UNCOMPUTED`로 뭉뚱그리지 않는다.
- HAZOP 운전 모드는 명시적 입력으로만 선택된다.
- 검사센터 실측 상태와 운전 모드가 HAZOP 선택·provider binding·격리 branch 진단에 연결된다.
- 조건부 시설 view에서 44개 case의 방출 지속시간·재고·종료 상태와 176개 risk atom의
  연결을 같은 case key로 추적한다.

차단된 strict gate는 다음과 같다.

1. 모든 case의 provider 소유 방출 종료·차단·재고 경계
2. 실제 시설용 qualified provider packet과 sidecar
3. 선언한 사고범위 전체의 독립 물리검증
4. 위 증거를 사용한 시설 전체 IR/F-N 승격

진단 계산 결과를 시설 QRA로 승격하기 위해 빈도·방출·차단·물리검증을 임의로 보충하지 않는다. 지원되지 않은 사고 family는 다른 family로 대체하지 않고 `PARTIAL`, `BLOCKED_REVIEW`, `UNCOMPUTED` 또는 명시적 evidence request로 남긴다.

케이스별 방출 경계 표는 전체 union 44개 case에 대해 위 원칙을 방출 종료 시점에서 다시 확인하며, 완료 감사의
`diagnostic_release_boundary_case_audit` 항목으로 재검증한다. `ELIGIBLE`은
개별 행의 종료 기준과 질량 장부가 닫혔다는 뜻만 가지며, 실제 provider packet,
독립 물리검증, 문헌 빈도 적용, 시설 IR/F-N을 승인하지 않는다. 현재 3개 행도
`model_prediction` 원점이어서 `facility_qra_promotion_eligible=false`이다. 상세
해석은 [`케이스별 방출 경계 승격 표`](PRISM_release_boundary_case_audit_20261114.md)에
기록되어 있다.

방출 경계 표는 이제 strict 결과와 수치 종료를 분리한다. 44개 case 중 15개가
`numerical_release_closed=true`이고, 그중 12개는 운영자 제한으로 인해
`NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED`이다. 이 보조 분류는 방출 시간·초기
재고·누적 방출·잔여 재고·잔여율을 함께 보존해 방출 장부가 피해영향 모델로 전달된
경로를 확인하게 하지만, provider 자격·독립 물리검증·시설 QRA 승격 조건을 낮추지
않는다.

`diagnostic_conditional_facility_release_trace` 검사는 이 view가 시설 평가의 44개
case·176개 risk atom과 일치하고 각 행에 case key, 방출 종료 메타데이터, risk atom
accounting을 갖는지 확인한다. 이 검사는 디지털트윈 전달 경로의 구조를 검증하는
진단 검사이며, qualified provider 또는 시설 IR/F-N 승격 검사는 아니다.

`diagnostic_conditional_facility_frequency_trace` 검사는 같은 view의 5개 문헌 빈도
시나리오가 고유 ID, 분위수 출처, 상관 가정, 조건부 IR/F-N, 순위 안정성 및 포트
결합 상태를 갖는지 확인한다. `frequency_inference_allowed=false`,
`facility_credible_interval=false`, `complete_facility_qra_claim=false`를 함께
검사하므로 이 결과는 빈도 민감도 장부이지 현장 빈도 학습이나 시설 전체 QRA가 아니다.
미충족·불완전 case 요약도 시나리오별 count, 고유 key count, 중복 행 count와 상태별
분포를 함께 검사해 누락 사고를 0위험으로 숨기지 않는다.

`diagnostic_conditional_facility_promotion_gates` 검사는 방출경계, provider 자격,
독립 물리검증, 시설 IR/F-N의 네 단계를 각각 `BLOCKED` 또는
`PASS_DIAGNOSTIC_ONLY`로 표시한다. 네 단계가 모두 닫혀도 현재 view의
`promotion_allowed`는 별도 승인을 거치기 전까지 `false`로 유지된다.

## 현재 신규 계산 처리시간

처리시간은 권위 시설평가 파일
[`facility_assessment.json`](../results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json)의 동일 캠페인 기록을 사용한다. 44개 fresh physics case를 별도 설비 캠페인으로 계산한 결과, case별 소요시간은 중앙값 **3,033.9 ms**, p95 **10,739.6 ms**, p99 **17,026.0 ms**, 최대 **18,322.3 ms**였다. 캠페인 전체 경과시간은 **203,388.1 ms(약 203.4초)**였다.

가장 큰 구간은 `near_field_and_dispersion`으로 p95 **9,353.1 ms**였고, source p95는 **722.5 ms**, pool p95는 **280.3 ms**, fire/explosion/damage risk p95는 **107.2 ms**였다. 이 수치는 한 번의 44-case 캠페인 분포이며 반복 실행 지연시간이나 1 Hz 신규 물리계산 성능을 의미하지 않는다. 따라서 현재 목표는 모니터링 경로에서 검증된 결과를 신속히 조회하고, fresh physics·예측 계산은 백그라운드/위험조건 도달 시 수행하는 구조로 기록한다. 상태 파일에도 `facility_fresh_physics_1hz_claim=false`를 명시했다.

