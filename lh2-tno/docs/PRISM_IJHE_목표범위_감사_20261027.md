# PRISM IJHE 목표 범위 감사 (2026-10-27)

## 이 문서가 추가된 이유

기존 `ijhe_completion_audit.json`은 시설 전체 QRA를 안전하게 보류하는 **승격 감사**다. 그래서 방출부터 최종 피해까지 숫자 계산이 실행되어도 qualified provider packet, 독립 물리검증, 엄격한 사고범위가 없으면 `INCOMPLETE_EVIDENCE`로 남는다.

이번 문서는 그 결과를 “계산이 안 됐다”로 오해하지 않도록, 개발 목표를 두 묶음으로 나눠 보여주는 설명용 장부다.

1. **핵심 연결**: 설비 상태 → native 방출 → 지속시간·재고·차단 → SLABx-LH2/SLABx → 기상·점화·인구 → 조건부 IR/F-N.
2. **엄격한 승격 게이트**: qualified provider packet, 독립 물리검증, 완전한 시설 범위, 시설 전체 QRA.

핵심 연결이 닫혔다는 표시가 시설 전체 QRA가 완료됐다는 뜻은 아니다.

## 현재 결과

원장: [`ijhe_objective_coverage_audit.json`](../results/20261026/native_full_scope_union_assessment/ijhe_objective_coverage_audit.json)

현재 최종 상태는 `CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN`이다. 최신
fail-closed IJHE 감사는 35개 검사 중 30개 PASS·5개 BLOCKED로 재생성되었다.
24/24 native packet과 상태 snapshot 결합은 구조적 diagnostic coverage로 PASS가
되었지만, qualified provider packet은 0건이고 native catalog·SLABx-LH2 구성요소
검사는 계속 diagnostic-only다.

| 목표 | 상태 | 현재 근거 |
|---|---|---|
| 설비 상태 → native 방출 | PASS | 24/24 사건 exact packet, 상태 snapshot 24/24 `BOUND_AND_ECHOED` |
| 방출 → 최종 피해 | CONDITIONALLY_COMPLETE | native campaign 24/24 case 실행, union risk atom 176개 |
| SLABx-LH2 피해영향 구성요소 | CONDITIONALLY_COMPLETE | 6개 FFI·6개 FLACS 비교, 질량잔차 1.77×10⁻¹² kg, 반복 재고차 0 kg |
| 문헌 빈도 불확실성 | CONDITIONALLY_COMPLETE | 5개 문헌 시나리오(설비별 공유 3개 + 사건별 독립 p05/p95 2개), 9개 분위수 미제공 진단 사건은 fixed, 설비·사고군 상위순위 안정성 기록 |
| 기상·점화·인구 결합 | CONDITIONALLY_COMPLETE | 5개 연간조건, 20개 조건×방출×점화 cross-product, missing-dimension atom 0, receptor mismatch 0 |
| 일반 LH2 설비 범위 | CONDITIONALLY_COMPLETE | 탱크·배관·밸브·펌프·벤트·기화기·재액화기 범위 원장 |
| 실시간 처리 | CONDITIONALLY_COMPLETE | cache p95는 1 Hz 기준 이내, 새 물리 계산은 1 Hz 미충족으로 별도 표시 |
| 독립 물리검증 | BLOCKED_EVIDENCE | 제한 evidence matrix이며 physical validation claim=false |
| qualified provider packet | BLOCKED_EVIDENCE | qualified packet 0건; 현재 packet은 native diagnostic |
| 엄격한 시설 범위 | BLOCKED_EVIDENCE | 8개 family가 `EXECUTED_OPERATOR_LIMITED`라 PARTIAL |
| 시설 전체 상태 snapshot coverage | PASS | 기본 native 24/24와 union 확장 10/10을 합쳐 34/34 사건이 canonical state snapshot·provider echo·provider result digest까지 연결됨 |
| 시설 전체 IR/F-N 승격 | BLOCKED_EVIDENCE | 위 게이트가 닫히지 않아 `facility_total_risk_available=false` |

따라서 현재 결과에서 사용할 수 있는 표현은 “일반 옥외 LH2 시설의 조건부 진단 chain이 실행되었다”이다. “시설 전체 QRA가 완료되었다”, “현장 사고빈도를 학습했다”, “독립 물리검증을 마쳤다”라고 표현하지 않는다. 기상·점화·인구 연결은 `scenario_branch_accounting.cross_product_count=20`과 `missing_dimension_atom_count=0`을 함께 확인해야 한다.

### 미계산과 증거 제한의 분리

시설 원장의 이전 `uncomputed_case_count`는 엄격한 승격을 막기 위해
`EXECUTED_OPERATOR_LIMITED` 행도 함께 보존했다. 그래서 그 숫자만 보면 계산되지 않은
사건이 29건처럼 보일 수 있다. 현재 union의 실제 수치 회계는 다음과 같다.

| 원장 필드 | 값 | 뜻 |
|---|---:|---|
| `numerically_executed_case_count` | 44 | 방출부터 조건부 피해 원자까지 숫자가 생성된 case |
| `not_numerically_executed_case_count` | 0 | `UNCOMPUTED` 또는 `FAILED`로 실제 수치가 없는 case |
| `qualified_evidence_withheld_case_count` | 29 | 계산은 되었지만 operator-limited라 qualified 근거로 보류한 case |
| 기존 `uncomputed_case_count` | 29 | 위 제한 행을 엄격한 범위 장부에 보존한 호환 필드 |

따라서 현재 결과는 “44개 case의 조건부 chain 계산 완료, 29개 case의 적격 근거 승격 보류,
실제 수치 미계산 0개”로 읽어야 한다. 이 구분은 시설 전체 QRA gate를 열지 않으며,
문헌 빈도나 독립 물리검증을 새로 만들지도 않는다.

## 재현 명령

```powershell
python scripts/build_ijhe_objective_coverage_audit.py `
  --union-verification results/20261026/native_full_scope_union_assessment/verification.json `
  --completion-audit results/20261026/native_full_scope_union_assessment/ijhe_completion_audit.json `
  --scope-matrix results/20261026/native_full_scope_union_assessment/scope_matrix.json `
  --facility-assessment results/20261026/native_full_scope_union_assessment/facility_assessment.json `
  --native-catalog-verification results/20261027/native_generic_scope_packets_state_bound/verification.json `
  --state-snapshot-audit results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json `
  --native-packet-evidence results/20261027/native_generic_scope_packets_state_bound/packet_evidence.json `
  --native-packet-campaign-ledger results/20261027/native_generic_scope_packets_state_bound/native_packet_campaign_ledger.json `
  --slabx-validation-evidence results/20261024/slabx_lh2_validation_audit_v1.json `
  --validation-evidence-matrix results/20261026/native_full_scope_union_assessment/validation_evidence_matrix.json `
  --realtime-cache-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --native-state-snapshot-campaign-ledger results/20261026/native_full_scope_union_assessment/native_state_snapshot_campaign_ledger.json `
  --extension-state-snapshot-coverage results/20261026/native_full_scope_union_assessment/extension_state_snapshot_coverage.json `
  --output results/20261026/native_full_scope_union_assessment/ijhe_objective_coverage_audit.json
```

이 명령은 계산을 새로 실행하지 않는다. 저장된 원장과 digest·count·상태를 대조하고, 누락되거나 승격할 수 없는 근거를 `BLOCKED_EVIDENCE`로 남긴다. 확장 상태 장부의 사건별 목록은 [`extension_state_snapshot_coverage.json`](../results/20261026/native_full_scope_union_assessment/extension_state_snapshot_coverage.json)에서 확인한다. 현재 10개 확장 사건은 provider가 원래 사용한 합성 model-prediction 입력에서 만든 canonical snapshot과 echo digest를 보존해 모두 `BOUND_AND_ECHOED`이다.

## 다음 개발 기준

IJHE 논문에 수치 결과를 넣을 때는 먼저 이 장부에서 해당 행의 상태와 `evidence_paths`를 확인한다. 조건부 행은 계산 구조와 민감도 설명에 사용할 수 있고, BLOCKED 행은 한계와 후속 검증 항목으로 제시한다. 시설 전체 IR/F-N을 승격하려면 남아 있는 네 개의 엄격한 행을 실제 자료로 닫고, 기존 fail-closed completion audit도 함께 통과해야 한다. 특히 union에 추가된 모든 설비·사고 사건이 상태 snapshot과 provider result digest까지 일대일로 연결되어야 하며, 현재 34개 사건의 state gate는 이 기준을 통과했다. 남은 4개 strict gate는 독립 물리검증·qualified provider·엄격한 사고범위·시설 전체 QRA 승격이다.
