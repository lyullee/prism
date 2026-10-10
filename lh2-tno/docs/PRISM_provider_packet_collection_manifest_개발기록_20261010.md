# PRISM provider packet 수집 manifest 개발 기록

## 목적

현재 PRISM은 44개 액화수소 시설 case를 계산 경로에 넣었지만, 실제 시설에서
검토된 provider 방출 packet과 qualification sidecar는 0건입니다. 기존
`facility_evidence_request.json`은 필요한 증거를 설명하지만, 담당자가 한 행씩
채워 갈 수 있는 수집용 표는 아니었습니다.

`provider_packet_collection_manifest.json`은 이 빈틈을 채우는 intake worksheet입니다.
시설 증거 요청을 한 행씩 복사해 사건·설비·방출 경로·조건·필수 증거를 고정하고,
실제 파일을 받은 뒤에 어느 행을 검토해야 하는지 보여줍니다. 이 파일 자체는
provider packet이나 사고빈도가 아니며, 위험도와 시설 IR/F-N을 만들지 않습니다.

## 현재 결과

현재 union 결과는 다음과 같습니다.

- 요청 행: 44개
- `OPEN` 수: 44개
- qualified provider packet: 0개
- 상태: `OPEN_PROVIDER_PACKET_COLLECTION`
- 시설 IR/F-N 승격: 금지

모든 행의 `release_path`와 `qualification_path`는 비어 있습니다. 따라서 기존
합성·모델예측 결과를 실제 자료처럼 자동 승격할 수 없습니다.

## 행의 의미

각 행은 다음 식별자를 함께 보존합니다.

- `event_id`: 사고 사건의 고유 ID
- `asset_id`, `component_id`: 설비와 실제 방출 경계의 ID
- `release_branch_id`: 차단 성공·실패, 양단 출구 같은 방출 branch
- `annual_condition_id`: 기상·노출 조건
- `scenario_families`: 누출·재고 소진·수직 handoff 등 사고군
- `exact_match_required`: port와 provider source/result digest를 포함한 정확 일치 조건
- `required_provider_evidence`: 실제 공급자가 제출해야 하는 자료 목록
- `current_release_boundary`, `current_boundary_gaps`: 현재 진단 결과와 남은 제한
- `release_path`, `qualification_path`: 자료가 접수된 뒤에만 채우는 파일 경로

행의 `OPEN`은 “계산을 안 했다”는 뜻이 아니라 “실제 provider 자료를 접수하고
검토하기 전”이라는 뜻입니다. `current_case_status`가 `EXECUTED`여도
`qualification_required=true`이면 수집 행은 계속 열려 있습니다.

## 생성 방법

```powershell
python scripts/build_provider_packet_collection_manifest.py `
  --evidence-request results/20261026/native_full_scope_union_assessment/facility_evidence_request.json `
  --output results/20261026/native_full_scope_union_assessment/provider_packet_collection_manifest.json
```

입력은 `prism.facility_evidence_request.v1`이어야 합니다. 사건 ID나 설비 ID가
없거나 중복된 case identity가 있으면 상태가
`INVALID_PROVIDER_PACKET_COLLECTION_MANIFEST`로 바뀌고, 자료를 받기 전에 중지할
수 있도록 차단 사유를 남깁니다.

## 실제 자료를 받은 뒤의 순서

1. 운영자·설비 문서·provider와 함께 해당 행의 event/component/port/조건을 확인합니다.
2. provider가 내보낸 release packet과 qualification sidecar를 저장합니다.
3. 확인된 파일의 경로를 행의 `release_path`와 `qualification_path`에 넣습니다.
4. `scripts/audit_provider_packet_inputs.py`로 실제 packet과 sidecar의 출처,
   SHA-256, 상태, 종료·질량 폐합을 검사합니다.
5. `audit_facility_case_packet_coverage.py`로 44개 행의 exact case identity와
   qualified packet이 맞는지 확인합니다.
6. 독립 물리검증과 시설 전체범위가 별도로 충족된 경우에만 readiness gate를 다시
   평가합니다.

수집 manifest의 행이 채워졌다는 사실만으로 packet을 qualified로 만들지 않습니다.
provider 감사와 case coverage가 통과하지 않으면 빈도와 IR/F-N은 계속 보류됩니다.

## 상태 일관성 연결

`scripts/audit_status_consistency.py`에
`--provider-packet-collection-manifest`를 주면 현재 상태 장부가 같은 manifest를
가리키는지 확인합니다.

```powershell
python scripts/audit_status_consistency.py `
  --current-status CURRENT_STATUS.json `
  --development-goal DEVELOPMENT_GOAL.json `
  --audit results/20261026/native_full_scope_union_assessment/ijhe_completion_audit.json `
  --assessment results/20261026/native_full_scope_union_assessment/facility_assessment.json `
  --evidence-request results/20261026/native_full_scope_union_assessment/facility_evidence_request.json `
  --ledger results/20261026/native_full_scope_union_assessment/campaign_result.json `
  --coverage results/20261026/native_full_scope_union_assessment/facility_case_packet_coverage.json `
  --provider-packet-input-audit results/20261026/native_full_scope_union_assessment/provider_packet_input_audit.json `
  --observed-state-release-binding-audit results/20261026/native_full_scope_union_assessment/observed_state_release_binding_audit.json `
  --observed-component-mapping-audit results/20261026/native_full_scope_union_assessment/observed_component_mapping_audit.json `
  --consequence-backend-chain-audit results/20261026/native_full_scope_union_assessment/consequence_backend_chain_audit.json `
  --provider-packet-collection-manifest results/20261026/native_full_scope_union_assessment/provider_packet_collection_manifest.json `
  --output results/20261026/native_full_scope_union_assessment/status_consistency_current.json
```

현재 일관성 결과는 24개 검사 통과입니다. 이 검사는 수집 준비 상태를 확인할 뿐,
자료가 없는데도 facility QRA를 열지 않습니다.
