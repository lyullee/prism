# PRISM worklist packet 증거 감사 기록

이 기록은 2026-10-14에 만든 일반 액화수소시설 worklist 24개를, 프로젝트 폴더에 저장된 외부 모델 결과와 다시 대조한 결과를 남긴다. 목적은 “파일이 있다”는 사실과 “설비·사고 포트·개구·방출 종료를 확인한 사고 packet이 있다”는 사실을 구분하는 것이다. 이 감사는 provider packet을 적격으로 승격하지 않으며 빈도를 새로 만들지 않는다.

## 실행 방법

```powershell
python scripts/audit_provider_worklist_packet_evidence.py `
  --provider-worklist results/20261014/generic_lh2_provider_release_worklist_diagnostic_adapter.json `
  --results-root results `
  --output results/20261014/generic_lh2_provider_worklist_packet_evidence.json
```

스캐너는 `results` 아래 `provider_response*.json`을 찾고 다음 순서로 확인한다.

1. 외부 response의 `event_id`와 `component_id`가 worklist와 같은지 확인한다.
2. response와 같은 폴더의 `resolved_release*.json` 또는 release set에서 사고 포트가 일치하는지 확인한다. 양단 파열은 두 endpoint가 모두 있어야 한다.
3. `failure_opening_diameter_m`가 worklist의 요구 개구와 허용오차 안에서 같은지 확인한다.
4. strict release schema, 방출 step, 지속시간, 질량, 종료 근거와 property basis가 있는지 확인한다.
5. 같은 폴더의 `verification.json`이 실행되었고 `provider_packet_promoted=false`, `frequency_inference=false`, `facility_qra_claim=false`를 유지하는지 확인한다.
6. 저장된 consequence chain의 `request.json`과 `verification.json`에서 같은 사건이 최종 chain까지 갔는지 별도로 센다.

정확히 일치한 결과의 상태는 `EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC`이다. 이 이름은 연결 시험이 실행되었다는 뜻이며, 현장 provider의 적격 사고 이력이라는 뜻이 아니다. 스캐너는 항상 `qualified_provider_packet_count=0`, `frequency_bound=false`, `facility_qra_claim=false`, `physical_validation_claim=false`를 출력한다.

## 현재 결과

| 항목 | 결과 |
|---|---:|
| 전체 worklist 사건 | 24 |
| 외부 response 후보가 있는 사건 | 24 |
| event/component/port/opening과 strict packet까지 맞은 사건 | 24 |
| 최종 consequence-chain 기록까지 있는 사건 | 15 |
| 적격 provider packet | 0 |
| 빈도 자동 연결 | 없음 |
| 시설 IR/F-N 승격 | 없음 |
| 독립 물리검증 승격 | 없음 |

설비별로는 storage-tank 5건, transfer-line 5건, transfer-valve 5건, pressure-relief-vent 1건, transfer-pump 2건, ambient-vaporizer 3건, reliquefier 3건이 진단 packet 증거를 가진다. storage-tank 5건은 외부 LayeredTank export 명령에 worklist의 event·port·개구를 전달해 생성했다. `AREA_100%`는 외부 모델의 양수 cell-mass 조건으로 더 작은 진단 시간 간격을 사용했다. 이 조정은 numerical stability를 기록한 것이며 현장 모델 보정이나 물리 검증으로 해석하지 않는다.

`candidate_event_count=24`는 모든 worklist 사건에 후보가 있다는 의미다. transfer-pump G2, ambient-vaporizer G1, reliquefier G4/G5처럼 후보 파일이 둘 이상인 경우에도, exact identity·endpoint·개구·strict schema·verification을 모두 만족하는 후보만 선택한다. 따라서 파일 수를 packet 수로 세지 않는다.

## IJHE 감사와의 관계

다음 명령은 위 결과를 전체 완료 감사에 넣는다.

```powershell
python scripts/build_ijhe_completion_audit.py `
  --current-status CURRENT_STATUS.json `
  --scope-matrix results/20261014/generic_mixed_accident_scope_matrix_refined_pool.json `
  --campaign-result results/20261014/generic_mixed_provider_campaign_refined_pool_result.json `
  --uncertainty-result results/20261014/generic_lh2_mixed_facility_assessment_refined_pool.json `
  --facility-assessment results/20261014/generic_lh2_mixed_facility_assessment_refined_pool.json `
  --provider-worklist results/20261014/generic_lh2_provider_release_worklist_diagnostic_adapter.json `
  --diagnostic-adapter-registry results/20261014/diagnostic_adapter_registry_audit_live.json `
  --diagnostic-adapter-execution results/20261014/diagnostic_adapter_runner_worklist_storage_001.json `
  --diagnostic-worklist-evidence results/20261014/generic_lh2_provider_worklist_packet_evidence.json `
  --output results/20261014/ijhe_completion_audit_live_with_worklist_evidence.json
```

현재 감사 결과는 `INCOMPLETE_EVIDENCE`이며 15개 검사 중 7개가 차단된다. 새 `diagnostic_worklist_packet_coverage_evidence` 검사는 24/24 coverage를 PASS로 기록하지만 `diagnostic_only=true`이고 차단 이유를 제거하지 않는다. 24개가 모두 구조적으로 연결되었다는 뜻과, 24개가 실제·적격 provider packet이라는 뜻을 혼동하지 않는다. `diagnostic_conditional_facility_risk_evidence`도 24개 event·24개 case·96개 risk atom에서 조건부 시설 IR/F-N 계산을 PASS로 기록하지만, qualified total은 계속 보류한다. 실제 설비 모델의 적격 사고방출 export, 12개 주요 사고 가족의 완결, 시설 IR/F-N, 독립 물리검증과 시설 전체 빈도 불확실성이 추가로 필요하다.

## 개발 판단

이번 결과로 “방출→피해 chain을 여러 설비 유형에서 연결하는 코드 경로가 실행된다”는 진단 증거는 넓어졌다. 24개 worklist 모두에서 구조적 packet 증거를 찾았고 15개는 consequence-chain 기록까지 만들었다. 그러나 이것은 합성 또는 operator-limited 진단이며, 시설 위험도가 완성된 것은 아니다. 논문에서는 이를 설비별 연결·증거 감사 결과로만 제시하고, 실제 시설 QRA나 현장 사고빈도 검증으로 표현하지 않는다.

관련 코드와 예시는 다음과 같다.

- `src/lh2_tno/provider_worklist_evidence.py`: evidence-only 스캐너
- `scripts/audit_provider_worklist_packet_evidence.py`: 재현 명령
- `tests/test_provider_worklist_evidence.py`: endpoint, 중복 후보, chain 판정 시험
- `examples/generic_lh2_provider_worklist_packet_evidence.json`: 재현 가능한 요약 결과
- `results/20261014/generic_lh2_provider_worklist_packet_evidence.json`: 실행 결과 원본(ignored local result)
