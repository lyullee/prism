# PRISM v0.6.0 IJHE 검증 매트릭스 갱신

## 이번 갱신의 목적

PRISM의 액화수소 시설 chain은 설비 상태에서 방출, 지속시간·차단·재고 장부,
SLABx-LH2/SLABx 피해영향, 점화·기상·인구, 조건부 IR/F-N까지 이어진다. 이
문서의 목적은 이 chain을 구성하는 SLABx-LH2 근거를 통합 검증 매트릭스에서
찾을 수 있게 하는 것이다. 구성요소 검증을 시설 전체 검증으로 넓혀 쓰지 않도록
promotion gate는 계속 닫아 둔다.

## 현재 권위 기준 (2026-11-14)

이 문서의 아래쪽 실행 이력은 이전 개발 단계의 재현 기록이다. 현재 상태를
인용할 때는 [`PRISM_IJHE_latest_audit_20261114.md`](PRISM_IJHE_latest_audit_20261114.md)와
[`ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json`](../results/20261114/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json)을
사용한다. 최신 union은 일반 옥외 LH2 시설의 34개 event, 44개 case, 176개 risk atom과
HAZOP event binding 34/34를 포함한다. 완료 감사는 `INCOMPLETE_EVIDENCE`이며
42개 검사 중 38개 `PASS`, 4개 `BLOCKED`이다.

현재 네 strict blocker는 (1) 모든 선언 case의 provider 방출 종료·차단·재고 경계,
(2) 실제 시설용 qualified provider packet, (3) 사고범위 전체의 독립 물리검증,
(4) 시설 전체 IR/F-N 승격이다. JUEL hold-out과 HSE Test 6의
DynamicLH2PoolX 근거는 `results/20261014/dynamiclh2poolx_evidence_audit.json`에
연결되어 있지만, 소스 해시 변화가 있는 제한 pool/spreading 구성요소 evidence로만
사용한다. 문헌 빈도 불확실성·미계산 case·처리시간은 최신 감사에 기록되며,
현장 센서에서 빈도를 학습하지 않는다.

## 새로 기록한 domain

`validation_evidence_matrix.json`에 다음 domain을 추가했다.

```text
id: slabx_lh2_consequence_component
status: RESTRICTED_COMPONENT_EVIDENCE
```

이 domain은 `results/20261024/slabx_lh2_validation_audit_v1.json`의 감사 결과를
그대로 참조한다.

- SLABx-LH2 외부 분산·LFL 비교: 6건
- pool 반경 비교: 6건
- pool 반경 중앙 비율: 약 1.0305
- 최대 시나리오 질량 잔차: 약 1.77×10⁻¹² kg
- 반복 실행 재고 차이: 0 kg
- 원자료 감사와 모델 버전·해시: 통합 record에 보존

이 자료가 허용하는 표현은 “선언된 옥외 적용범위 안에서 SLABx-LH2 피해영향
구성요소에 제한된 비교·폐합 근거가 있다”이다.

## 운전 시나리오 근거 연결

준비도 원장은 `--scenario-evidence-audit`로 전달한 시나리오 screening summary도
`scenario_evidence` 블록에 보존한다. 현재 참조 파일은
`examples/inspection_center_scenario_evidence_reaudit_summary.json`이며, 52개
시나리오 행과 후보 사고군·감시 신호를 기록한다. 이 자료는 일반적인 옥외 LH2
설비의 사고군 후보와 후속 provider 자료 요청을 정리하는 데 사용한다.

시나리오 설명이나 압력·온도·유량·밸브 신호는 방출량, 종료시간, 개구 크기 또는
사고빈도를 역산하지 않는다. 따라서 원장 검증기는 시나리오 근거가 포함되어도
`candidate_only=true`, `frequency_assigned=false`,
`sensor_frequency_learning_used=false`, `facility_qra_claim=false`를 요구한다.
실제 설비별 방출 packet과 검토된 문헌 빈도가 들어오기 전에는 strict facility
QRA gate가 닫힌 상태로 유지된다.

## 계속 차단하는 주장

다음 결과는 새 domain으로도 열리지 않는다.

- 설비 사고 방출, 누출 구경, 차단 성공률, 지속시간 또는 재고 소진의 물리 검증
- initiating-event 빈도 추정 또는 센서 기반 빈도 학습
- 점화·화재·폭발·복사열·IR/F-N의 독립적인 전체 chain 검증
- qualified provider packet 승인
- 시설 전체 QRA 승격

즉, SLABx-LH2 검증은 방출 packet의 출처나 문헌 빈도를 대신하지 않는다. 실제
설비 상태와 방출 packet은 설비 모델/provider가 명시적으로 제공해야 하며,
빈도는 문헌 frequency plan과 불확실성 시나리오에서만 입력한다.

## 재생된 현재 감사

다음 파일을 다시 만들었다.

- `results/20261026/native_full_scope_union_assessment/validation_evidence_matrix.json`
- `results/20261026/native_full_scope_union_assessment/ijhe_completion_audit.json`
- `results/20261026/native_full_scope_union_assessment/ijhe_objective_coverage_audit.json`
- `results/20261026/native_full_scope_union_assessment/verification.json`

현재 objective 상태는 다음과 같다.

```text
CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN
core blocking checks: 0
strict blocking checks: 4
```

남은 strict gate는 qualified provider evidence, 독립 물리검증, 엄격한 전체 사고범위,
시설 전체 QRA다. 조건부 진단 chain은 34개 사건·44개 case·176개 risk atom을
보존하지만, 증거가 없는 사고를 다른 사고로 대체하거나 0 위험으로 삭제하지 않는다.

## 재현 명령

통합 매트릭스 생성은 다음과 같이 실행한다.

```powershell
python scripts/bind_native_full_scope_union_evidence.py `
  --union-dir results/20261026/native_full_scope_union_assessment `
  --current-status CURRENT_STATUS.json `
  --pool-record results/20261009/validation_evidence/dynamiclh2poolx_stage_c_prism_record_git_blob.json `
  --equipment-audit results/20261009/validation_evidence/equipment_validation_audit_live.json `
  --native-contract results/20261022/lh2dt_native_contract_audit_native_catalog.json `
  --external-sweep examples/center_lh2_external_sweep_audit.json `
  --ijhe-audit-source results/20261026/native_full_scope_union_assessment/ijhe_completion_audit.json `
  --provider-worklist results/20261027/native_generic_scope_packets_state_bound/campaign_assessment/provider_worklist.json `
  --diagnostic-adapter-registry results/20261014/diagnostic_adapter_registry_audit_live.json `
  --diagnostic-worklist-evidence results/20261014/generic_lh2_provider_worklist_packet_evidence.json `
  --vertical-handoff-result results/20261020/vertical_vent_all_bins/verification.json `
  --realtime-cache-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --native-full-bore-result results/20261027/native_dynamic_pipe_full_bore_state_bound/verification.json `
  --state-snapshot-binding-audit results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json `
  --native-state-snapshot-campaign-ledger results/20261026/native_full_scope_union_assessment/native_state_snapshot_campaign_ledger.json `
  --native-scope-packet-catalog-verification results/20261027/native_generic_scope_packets_state_bound/verification.json `
  --native-model-contract-audit results/20261022/lh2dt_native_contract_audit_native_catalog.json `
  --frequency-provenance-report results/20261018/generic_lh2_frequency_provenance_current.json `
  --native-packet-campaign-ledger results/20261027/native_generic_scope_packets_state_bound/native_packet_campaign_ledger.json `
  --native-binding-reconciliation results/20261022/native_binding_reconciliation.json `
  --domain-recovery-audit results/20261024/domain_recovery_audit_flammability_gate_v2.json `
  --slabx-validation-evidence results/20261024/slabx_lh2_validation_audit_v1.json `
  --observed-state-evidence examples/inspection_center_observed_state_evidence.json
```

매트릭스 domain 추가와 함께 검증한 테스트는 `tests/test_validation_evidence_matrix.py`
7건이며, 전체 portable suite도 다시 실행해야 한다. 테스트가 통과해도 이는 코드
계약 검증이지 현장 시설 QRA 승인이라는 뜻은 아니다.

\n

## v0.6.0 준비도 원장

여러 감사 파일을 따로 열지 않고 현재 개발 상태를 검토할 수 있도록
[`v060_readiness_report.json`](../results/20261026/native_full_scope_union_assessment/v060_readiness_report.json)을
추가했다. 이 원장은 다음 정보를 한 파일에 모은다.

- 설비 component별 상태, 사건·case·위험 원자 수, qualified evidence 보류 수
- 12개 사고 family의 조건부 계산 상태와 엄격 승격 상태
- 문헌 빈도 시나리오·순위 안정성 및 센서 기반 빈도 학습 제외 선언
- cache와 fresh physics 처리시간, campaign p95/p99
- SLABx-LH2를 포함한 검증 domain과 제한된 주장 범위
- 조건부 chain 완료 기준 A~E와 시설 전체 QRA 승격을 막는 strict gate
- 현재 provider 증거 요청 장부의 상태, 44개 case 요청·12개 사고군·9개 설비 요약
- 입력 감사 파일 8개의 저장 경로와 SHA-256 digest

원장은 계산을 다시 수행하거나 부족한 증거를 추정하지 않는다. 따라서 현재
`CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN` 및
`INCOMPLETE_EVIDENCE` 상태를 그대로 보존하며, qualified provider evidence,
독립 물리검증, 엄격한 시설 범위, 시설 전체 QRA의 네 gate가 열려 있음을
명시한다.

기존 `CURRENT_STATUS.json`에도 이 원장을
`v060_current_readiness_report`로 가리키는 최신 포인터를 추가했다. 파일의
오래된 개발 이력 필드는 보존되지만, 2026-10-26 통합 결과를 인용할 때는 이
포인터와 원장의 SHA-256 입력 기록을 사용한다.

생성기는 원장을 저장하기 전에 case 수 보존, 사고 family 수, 조건부 실행 회계,
센서 빈도 학습 제외, strict gate가 남아 있을 때의 승격 플래그를 자동 검사한다.
검사에 실패하면 결과 파일을 정상 원장으로 쓰지 않는다.

`evidence_request` 블록은 `facility_evidence_request.json`을 요약한 것이다. 이
블록은 “현재 어떤 자료를 받아야 하는가”를 보여주지만, 요청이 존재한다는 이유로
provider packet을 qualified로 바꾸거나 시설 IR/F-N을 열지 않는다. 실제 packet을
받으면 같은 event/component/port와 source/result digest를 exact-match한 뒤 별도의
qualification gate를 다시 통과해야 한다.

재생 명령은 다음과 같다.

```powershell
python scripts/build_v060_readiness_report.py `
  --objective-audit results/20261026/native_full_scope_union_assessment/ijhe_objective_coverage_audit.json `
  --union-verification results/20261026/native_full_scope_union_assessment/verification.json `
  --scope-matrix results/20261026/native_full_scope_union_assessment/scope_matrix.json `
  --facility-assessment results/20261026/native_full_scope_union_assessment/facility_assessment.json `
  --completion-audit results/20261026/native_full_scope_union_assessment/ijhe_completion_audit.json `
  --validation-matrix results/20261026/native_full_scope_union_assessment/validation_evidence_matrix.json `
  --realtime-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --facility-evidence-request results/20261026/native_full_scope_union_assessment/facility_evidence_request.json `
  --scenario-evidence-audit examples/inspection_center_scenario_evidence_reaudit_summary.json `
  --risk-atom-chain-audit results/20261026/native_full_scope_union_assessment/risk_atom_chain_audit.json `
  --equipment-state-release-audit results/20261026/native_full_scope_union_assessment/equipment_state_release_audit.json `
  --external-equipment-model-audit results/20261104/external_equipment_model_audit_current.json `
  --equipment-scenario-coverage-audit results/20261104/equipment_scenario_coverage_audit_current.json `
  --equipment-frequency-binding-audit results/20261104/equipment_frequency_binding_audit_current.json `
  --output results/20261026/native_full_scope_union_assessment/v060_readiness_report.json
```

현재 completion audit는 39개 검사 중 34개 PASS·5개 BLOCKED다. `risk_atom_chain_audit.json`은
44개 case·176개 risk atom의 구조적 방출→최종피해 연결을, `equipment_state_release_audit.json`은
44개 case·9개 component의 설비 상태→방출 packet identity를 readiness report에 함께
기록한다. 네이티브
catalog가 확인한 24/24 exact packet은 구조적 worklist coverage를 PASS로 만들지만,
이는 합성 진단 packet의 exact-match일 뿐 qualified provider evidence가 아니다.
따라서 실제 provider packet 0건, 엄격한 사고범위 차단, 시설 전체 IR/F-N 보류는
그대로 readiness report에 남는다.

2026-11-04부터 최신 readiness 원장에는 외부 설비 모델과 P&ID 보조 원장도 선택
입력으로 보존한다. 최신 결과는
[`v060_readiness_report_with_external_equipment_model.json`](../results/20261104/v060_readiness_report_with_external_equipment_model.json)이다.
이 원장은 34개 event·44개 case·176개 risk atom의 기존 조건부 연결을 유지하면서,
외부 설비 12개 중 상태모델 입력 준비 2개, P&ID ID 겹침 9개, confirmed/candidate
포트 매핑 14/13개, 활성 component edge 0/27개를 별도 `chain` 항목으로 기록한다.
일반 시설용 asset identity가 해소된 설비는 0개이고 12개 사고 family가 아직
`UNCOMPUTED`이므로 문헌 빈도·provider 방출·시설 IR/F-N gate는 그대로 닫혀 있다.
즉 외부 설비 자료가 readiness 원장에 연결됐다는 것과 시설 QRA가 완료됐다는 것은
서로 다른 상태다.

일반 시설 모듈 자체의 계약도 같은 readiness 원장에 별도로 연결했다. [`v060_readiness_report_with_generic_equipment_model.json`](../results/20261105/v060_readiness_report_with_generic_equipment_model.json)은 합성 facility-neutral manifest의 7개 설비와 12개 사고 family를 기록하고, 문헌 빈도 24개 중 24개를 유효하게 설비에 바인딩한다. 이 24개 사건은 검토된 사고 포트에도 24/24로 연결되고 포트 미지정·불일치는 0건이다. `vertical_handoff`는 provider handoff 자료가 없어 미계산이며, 사고 방출·빈도 추론·시설 QRA 승격은 계속 false다. 이 항목은 액화수소검사지원센터 자료의 identity 공백과 분리된 일반 모듈 검증이다.

2026-11-06에는 같은 일반 설비 24개 사건의 진단 packet 캠페인 결합도 별도 감사했다. [`generic_lh2_diagnostic_campaign_binding_current.json`](../results/20261106/generic_lh2_diagnostic_campaign_binding_current.json)은 packet event 24개가 campaign event 24개, case 24개, risk atom 96개로 빠짐없이 도달했음을 확인한다. provider source/result digest는 24/24, 방출 지속시간·available mass·누적 방출량·termination ledger 값은 24/24로 대조되어 소비되었다. 다만 19개 case는 `EXECUTED_OPERATOR_LIMITED`, 5개는 `EXECUTED`인 진단 실행이며, qualified provider packet 0개·provider 빈도 사용 false·물리검증 false·시설 QRA false를 보존한다. 따라서 이 감사는 방출값 전달의 구조적 결합을 닫았지만 현장 packet 자격이나 시설 위험도 승격을 의미하지 않는다.

같은 campaign에 [`generic_lh2_chain_closure_current.json`](../results/20261106/generic_lh2_chain_closure_current.json)도 적용했다. 24개 packet event 모두 종료·재고 ledger, risk atom의 최종 피해 필드, 독립 IR 재집계와 F/N 재집계까지 폐합되었다(`PARTIAL_DIAGNOSTIC_CHAIN_CLOSED`). 여기서 `partial`은 계산 연결이 빠졌다는 뜻이 아니라 provider qualification·물리검증·시설 QRA 승격이 아직 열리지 않았다는 뜻이다. 특히 19개 case는 provider가 잔여 재고 또는 물리 closure를 완전히 입증하지 않아 operator-limited로 남아 있으며, 이 상태를 qualified packet으로 바꾸지 않는다.

같은 원장의 `timing.runtime_profile`은 디지털 트윈에서 사용할 계산 경로를 세 가지로 구분한다. 최신 benchmark에서 저장된 피해 결과를 재사용하는 `cached_diagnostic_1hz`는 p95 24.54 ms로 1 Hz 진단 모니터링에 사용할 수 있다. 새 설비 상태로 SLABx-LH2를 다시 계산하는 fresh physics는 2614.51 ms로 1 Hz 조건을 만족하지 않는다. persistent worker의 변경입력 fresh physics도 steady p50/p95/p99가 1869/2104/2104 ms로 1 Hz를 만족하지 않는다. 전체 44-case campaign은 온라인 루프가 아니라 오프라인 평가와 빈도 민감도 분석에 사용한다. 이 프로파일은 처리시간을 기록할 뿐이며 시설 QRA의 실시간 승격을 주장하지 않는다.

실행기 자체도 `prism.realtime_mode_contract.v1`을 반환한다. 동일 요청은
`cached_diagnostic_1hz`, 변경 요청의 새 SLABx-LH2 계산은 `fresh_physics_background`,
deadline 초과는 `deadline_missed`로 표시된다. 계약에는 `fresh_physics_1hz_claim=false`와
`stale_fallback_used=false`가 포함되므로, 캐시가 빠르다는 이유로 새 물리계산 1 Hz나
오래된 결과 대체를 주장할 수 없다. 시설 batch는 이 mode를 설비별로 집계하고, 누락·잘못된
mode 계약은 별도 invalid component으로 남긴다.

`chain.isolation_union_extension`에는 별도 차단 응답 진단도 연결했다. 기존 34-event·44-case 원장에 5개 isolation event와 20개 case를 이름공간으로 결합해, 차단 성공 10건과 실패 10건을 각각 보존한다. 20개 모두 설비 상태 snapshot이 연결되고 provider response가 소비됐지만, 이는 합성 barrier branch 진단이다. 차단 성공률을 현장 빈도로 바꾸지 않으며, qualified provider packet과 시설 QRA 승격은 계속 false다. 근거 파일은 [`isolation extension verification`](../results/20261026/native_full_scope_union_assessment/isolation_extension/verification.json)이다.

이번 갱신에는 [`release_closure_worklist.json`](../results/20261106/release_closure_worklist.json)도 연결했다. 이 원장은 44개 방출 case를 하나씩 펼쳐서 종료기준, 격리상태, provider 재고잔량, end-to-end 질량잔차를 별도로 기록한다. 현재 44개 모두 격리 상태가 `not_declared`이고, 24개는 `synthetic_diagnostic_horizon`에서 끝나며, `inventory_depletion`으로 표시된 16개 중 15개는 provider 종료시점에 재고 잔량이 남아 있다. 전체 피해 계산의 질량잔차가 허용범위를 벗어난 case는 0개지만, provider 재고 잔량과 end-to-end 질량잔차는 서로 다른 검사이므로 provider qualification이나 시설 QRA가 열리지는 않는다. 각 case에는 필요한 provider 자료와 blocking reason이 함께 들어 있어 현장자료 수집용 fail-closed 목록으로 사용할 수 있다.

최신 readiness 원장에 이 worklist를 함께 넣으려면 다음 인자를 추가한다.

```powershell
python scripts/build_v060_readiness_report.py `
  ...기존 인자... `
  --release-closure-worklist results/20261106/release_closure_worklist.json `
  --output results/20261105/v060_readiness_report_with_generic_equipment_model.json
```

`chain.release_closure_worklist`의 모든 승격 플래그는 의도적으로 `false`이며, 이는 종료근거가 채워질 때까지 빈도추론·시설 IR/F-N·물리검증 주장을 막는다.

IJHE 목표 감사에도 같은 원장을 선택 입력으로 연결할 수 있다.

```powershell
python scripts/build_ijhe_objective_coverage_audit.py `
  ...기존 objective audit 인자... `
  --release-closure-worklist results/20261106/release_closure_worklist.json `
  --output results/20261106/ijhe_objective_coverage_audit_with_release_closure.json
```

출력의 `diagnostic_release_closure_worklist` 행은 종료·격리·재고·질량잔차 closure가 열려 있으면 `BLOCKED_EVIDENCE`로 표시하고, 모든 case가 닫힌 경우에만 `PASS`가 된다. generic provider closure audit를 함께 전달하면 `diagnostic_generic_provider_release_closure` 행이 사건별 종료 상태 집계와 packet 수를 직접 검증한다. 열린 사건이 있어도 집계와 승격 차단 플래그가 일관되면 이 진단 행은 `PASS`가 될 수 있으며, 이는 자료 수집 원장이 정합하다는 뜻이다. 두 행은 기존 core/strict blocker 목록과 분리된 진단 행이다. 따라서 worklist나 closure audit가 닫혀도 qualified provider evidence, 독립 물리검증, 시설 QRA 승격은 별도 gate를 통과해야 한다.

이 연결을 적용한 현재 원장은 [`ijhe_objective_coverage_audit_with_release_closure.json`](../results/20261106/ijhe_objective_coverage_audit_with_release_closure.json)과 [`v060_readiness_report_with_release_closure_objective.json`](../results/20261106/v060_readiness_report_with_release_closure_objective.json)이다. 전자는 25개 objective 행 중 일반 시설 설비·사고군·문헌빈도 행과 관측 정상상태 모델 binding 행을 진단 `PASS`로 기록하고, 종료 closure 행은 `BLOCKED_EVIDENCE`로 기록한다. 관측 모델 binding은 3/3 component·3개 진단 adapter를 확인한다. 후자는 기존 readiness invariant 13개와 strict blocker 4개를 그대로 통과시킨다.

일반 시설 연결은 `diagnostic_generic_equipment_scenario_coverage`와 `diagnostic_generic_equipment_frequency_binding` 두 행으로 보존한다. 합성 옥외 manifest의 7개 설비가 12개 사고군에 명시적으로 매핑되고, 문헌빈도 event 24개가 7개 설비에 연결되며, 1개 미계산 family도 숨기지 않는다. 이 빈도는 현장 학습 빈도가 아니고 정상 센서에서 추정한 값도 아니다. provider 방출 packet이 제출되기 전에는 지속시간·차단·재고 소진·질량수지와 결합하지 않으며, 시설 IR/F-N을 열지 않는다.

objective 원장의 `completion_criteria`는 `A_equipment_state_and_release`부터 `E_validation_and_processing_time`까지 다섯 단계의 조건부 상태와 근거 경로를 기록하고, 각 단계의 `strict_gate_ids`와 `open_strict_gate_ids`를 함께 보존한다. 예를 들어 시설 IR/F-N 단계에는 `strict_facility_scope`·`strict_facility_qra`, 검증·처리시간 단계에는 `independent_physical_validation`이 표시된다. `explicit_exclusions`에는 이번 v0.6.0 필수범위 밖인 현장 사고빈도 수집, 센서 빈도 학습, 실내 방출·밀폐, 폭굉/DDT, 전체 도미노 확대를 고정한다. 따라서 모든 단계가 `CONDITIONAL_PASS`여도 열려 있는 strict gate를 무시하고 완성으로 해석하지 않는다.

`diagnostic_observed_state_model_binding`은 `results/20261026/native_full_scope_union_assessment/observed_state_model_binding_audit.json`을 읽는다. 현재 intake tank·storage vent·supply vaporizer의 3개 관측 component는 facility-neutral normal-state model 입력에 연결되고, 각 진단 adapter도 별도로 확인된다. 그러나 시설 component identity는 0/3, qualified provider packet은 0건이며 사고 방출·빈도·IR/F-N 승격은 계속 차단된다. 정상 운전 신호가 사고 release나 빈도를 자동으로 만든다고 해석하지 않기 위한 진단 행이다.

readiness validator는 이제 `open_case_count = case_count - READY_FOR_STRICT_REVIEW`, 각 closure gap 집계와 요약 필드의 일치까지 검사한다. 따라서 원장의 case 수와 개별 gap 수가 서로 다른 상태로 저장되면 `VALID`가 되지 않는다.

실제 provider packet을 받을 때는 [`audit_provider_release_closure.py`](../scripts/audit_provider_release_closure.py)를 먼저 실행한다. `prism.provider_release_closure_audit.v1`은 `reviewed_isolation_success`의 격리 성공·작동시각, `inventory_depletion`의 최종 재고와 provider 수지, 종료 provenance를 각각 검사한다. 이 감사가 `CLOSURE_READY_FOR_QUALIFICATION`을 반환해도 qualified provider 증거와 독립 물리검증이 자동으로 충족되는 것은 아니다.

2026-11-08에는 저장소 밖 `DocuData` 전체를 다시 훑어 `resolved_release*.json` 14개 파일·28개 방출 행을 [`external_release_artifact_intake.json`](../results/20261108/external_release_artifact_intake.json)에 기록했다. 이 자료는 설비·포트·방출 shape·종료 필드·source/result digest를 찾는 inventory이며, qualified actual 행이나 exact qualification sidecar를 의미하지 않는다. 현재 21개는 schema-unqualified, 7개는 closure evidence open, closure-ready는 0개다. 이 intake는 [`ijhe_objective_coverage_audit_full_evidence_with_external_release_intake.json`](../results/20261108/ijhe_objective_coverage_audit_full_evidence_with_external_release_intake.json)의 `diagnostic_external_release_artifact_intake` 행으로 연결되지만, 핵심/엄격 gate의 위치를 바꾸지 않는다. 이 분리를 통해 검색된 파일이 있다는 사실과 실제 사고 방출 근거가 확보됐다는 사실을 혼동하지 않는다.

배치 manifest를 사용하는 경우에는 `scripts/audit_provider_packet_inputs.py --require-release-closure`를 사용한다. 이 옵션은 qualification sidecar가 맞더라도 종료·격리·재고 closure가 열린 packet을 `NO_PROVIDER_PACKET_INPUT`으로 남긴다. 기본 모드는 기존 packet identity 감사와의 호환성을 위해 closure 결과를 함께 기록하되 packet을 자동 승격하지 않는다.

최신 외부 설비 결합 원장은 다음 명령으로 재현할 수 있다.

```powershell
python scripts/build_v060_readiness_report.py `
  --objective-audit results/20261104/ijhe_objective_coverage_audit_with_external_equipment_model.json `
  --union-verification results/20261031/native_full_scope_union_pipefix_state_bound/verification.json `
  --scope-matrix results/20261031/native_full_scope_union_pipefix_state_bound/scope_matrix.json `
  --facility-assessment results/20261031/native_full_scope_union_pipefix_state_bound/facility_assessment.json `
  --completion-audit results/20261031/native_full_scope_union_pipefix_state_bound/ijhe_completion_audit.json `
  --validation-matrix results/20261026/native_full_scope_union_assessment/validation_evidence_matrix.json `
  --realtime-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --facility-evidence-request results/20261031/native_full_scope_union_pipefix_state_bound/facility_evidence_request.json `
  --scenario-evidence-audit examples/inspection_center_scenario_evidence_reaudit_summary.json `
  --risk-atom-chain-audit results/20261031/native_full_scope_union_pipefix_state_bound/risk_atom_chain_audit.json `
  --equipment-state-release-audit results/20261031/native_full_scope_union_pipefix_state_bound/equipment_state_release_audit.json `
  --facility-aggregate-closure-audit results/20261031/native_full_scope_union_pipefix_state_bound/facility_aggregate_closure_audit.json `
  --facility-component-contribution-audit results/20261031/native_full_scope_union_pipefix_state_bound/facility_component_contribution_audit.json `
  --facility-frequency-uncertainty-audit results/20261031/native_full_scope_union_pipefix_state_bound/facility_frequency_uncertainty_audit.json `
  --external-equipment-model-audit results/20261104/external_equipment_model_audit_current.json `
  --equipment-scenario-coverage-audit results/20261104/equipment_scenario_coverage_audit_current.json `
  --equipment-frequency-binding-audit results/20261104/equipment_frequency_binding_audit_current.json `
  --generic-equipment-scenario-coverage-audit results/20261105/generic_lh2_full_scope_equipment_scenario_coverage.json `
  --generic-equipment-frequency-binding-audit results/20261105/generic_lh2_full_scope_equipment_frequency_binding.json `
  --isolation-union-extension-verification results/20261026/native_full_scope_union_assessment/isolation_extension/verification.json `
  --output results/20261105/v060_readiness_report_with_generic_equipment_model.json
```


### 시설 IR/F/N 독립 집계 감사 (2026-10-30 갱신)

`facility_aggregate_closure_audit.json`은 저장된 176개 risk atom의 `개시빈도 × 조건부 가중치 × 수용점 피해`를 다시 합산하고, N≥1 기준 F/N 곡선을 다시 만든다. 공식 조건부 시설 값과 비교한 결과는 `FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC`, IR 불일치 0건, F/N 불일치 0건이다. `facility_component_contribution_audit.json`은 같은 원자를 9개 설비별로 재결합하고 진단 순위를 다시 계산해 불일치 0건을 확인한다. `facility_frequency_uncertainty_audit.json`은 5개 문헌 빈도 시나리오의 IR/F-N 재가중을 독립 재현해 불일치 0건을 확인한다. 이 검사는 계산 집계의 재현성만 닫으며, qualified provider·독립 전체 물리검증·완전 사고범위·시설 QRA 승격을 열지 않는다.\n
