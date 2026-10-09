# PRISM v0.6.0 IJHE 검증 매트릭스 갱신

## 이번 갱신의 목적

PRISM의 액화수소 시설 chain은 설비 상태에서 방출, 지속시간·차단·재고 장부,
SLABx-LH2/SLABx 피해영향, 점화·기상·인구, 조건부 IR/F-N까지 이어진다. 이
문서의 목적은 이 chain을 구성하는 SLABx-LH2 근거를 통합 검증 매트릭스에서
찾을 수 있게 하는 것이다. 구성요소 검증을 시설 전체 검증으로 넓혀 쓰지 않도록
promotion gate는 계속 닫아 둔다.

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
  --vertical-handoff-result results/20261026/native_full_scope_union_assessment/vertical_handoff_rebound_result.json `
  --realtime-cache-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --native-scope-packet-catalog-verification results/20261027/native_generic_scope_packets_state_bound/verification.json `
  --slabx-validation-evidence results/20261024/slabx_lh2_validation_audit_v1.json
```

매트릭스 domain 추가와 함께 검증한 테스트는 `tests/test_validation_evidence_matrix.py`
7건이며, 전체 portable suite도 다시 실행해야 한다. 테스트가 통과해도 이는 코드
계약 검증이지 현장 시설 QRA 승인이라는 뜻은 아니다.

\n