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
| `validation_evidence_matrix_with_dynamiclh2poolx.json` | 물리·관측·interface 증거 경계 | 시설 QRA 보류를 명시 |
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
  --state-snapshot-binding-audit results/20261114/base_state_snapshot_binding_audit_port_bound.json `
  --native-scope-packet-catalog-verification results/20261111/native_generic_scope_packets_isolation/verification.json `
  --native-scope-isolation-branch-catalog-audit results/20261111/native_generic_scope_packets_isolation/isolation_branch_audit.json `
  --native-isolation-catalog-facility-chain-verification results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/verification.json `
  --validation-evidence-matrix results/20261014/validation_evidence_matrix_with_dynamiclh2poolx.json `
  --slabx-validation-evidence results/20261106/slabx_lh2_validation_audit_recomputed.json `
  --facility-evidence-request results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_evidence_request.json `
  --diagnostic-worklist-evidence results/20261024/native_generic_scope_packet_evidence_qualification_readiness_v14.json `
  --hazop-selection-event-binding results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/hazop_selection_event_binding.json `
  --hazop-extension-mode-evidence-request results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/hazop_extension_mode_evidence_request.json `
  --output results/20261114/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json
```

## 판정

현재 결과는 30개 검사 중 26개 `PASS`, 4개 `BLOCKED`, 전체 상태 `INCOMPLETE_EVIDENCE`이다.

통과한 진단 연결은 다음을 뜻한다.

- 설비 상태 snapshot이 event와 case로 전달된다.
- 방출량·지속시간·차단·재고 장부가 피해계산 입력으로 전달된다.
- SLABx-LH2 확산·pool 결과가 점화·피해 risk atom으로 전달된다.
- 문헌 빈도 불확실성과 처리시간이 별도 장부로 기록된다.
- HAZOP 운전 모드는 명시적 입력으로만 선택된다.

차단된 strict gate는 다음과 같다.

1. 모든 case의 provider 소유 방출 종료·차단·재고 경계
2. 실제 시설용 qualified provider packet과 sidecar
3. 선언한 사고범위 전체의 독립 물리검증
4. 위 증거를 사용한 시설 전체 IR/F-N 승격

진단 계산 결과를 시설 QRA로 승격하기 위해 빈도·방출·차단·물리검증을 임의로 보충하지 않는다. 지원되지 않은 사고 family는 다른 family로 대체하지 않고 `PARTIAL`, `BLOCKED_REVIEW`, `UNCOMPUTED` 또는 명시적 evidence request로 남긴다.

