# native 일반 LH2 + vertical handoff + inventory depletion union (2026-10-26)

기존 native 일반 LH2 캠페인은 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기의 24개 사건을 계산했지만 `vertical_handoff`와 별도 `inventory_depletion` 진단 장부는 시설 원장에 들어 있지 않았다. 이번 union 실행은 이미 계산된 수직 handoff all-bin 및 재고 소진 결과를 새로 물리 계산한 것으로 가장하지 않고, 현재 near-receptor 시설 namespace로 명시적으로 rebind한 뒤 세 장부를 병합했다.

## 재현

```powershell
python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261026/native_full_scope_frequency_assessment `
  --base-campaign results/20261027/native_generic_scope_packets_state_bound/campaign_assessment/campaign.json `
  --base-campaign-result results/20261027/native_generic_scope_packets_state_bound/campaign_assessment/campaign_result.json `
  --vertical-result results/20261020/vertical_vent_all_bins/campaign_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261009/equipment_inventory_campaign/campaign_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --state-snapshot-binding-audit results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json `
  --output-dir results/20261026/native_full_scope_union_assessment
```

union 결과에 검증근거와 실시간 처리 증거를 묶으려면 다음 단계를 실행한다. 이
명령은 새 provider 물리 계산을 만들지 않고, 기존 원장과 명시된 증거의 승격 게이트를
다시 검사한다.

```powershell
python scripts/benchmark_realtime_cache.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261026/native_full_scope_frequency_assessment/campaign.json `
  --backend-config results/20261009/backend_config_current.json `
  --repetitions 10 `
  --output results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json

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

## 연결 결과

| 항목 | 결과 |
|---|---:|
| 기존 native 사건 | 24개 |
| vertical handoff 사건 | 5개 |
| inventory depletion 추가 사건 | 5개 |
| 병합 사건 | 34개 |
| 병합 case | 44개 |
| 병합 risk atom | 176개 |
| 실제 수치 미계산 case | 0개 |
| 수치 실행 case | 44개 |
| qualified evidence 보류 case | 29개 (`EXECUTED_OPERATOR_LIMITED`) |
| vertical strict 상태 | `PARTIAL` |
| vertical 조건부 수치 상태 | `EXECUTED` |
| vertical 조건부 실행 case | 10개 |
| vertical operator-limited case | 10개 |
| qualified provider packet | 0개 |
| 시설 전체 IR/F-N | 보류 |
| 자동 증거 요청 | 12개 사고군·44개 case |

수직 결과의 event ID, provider packet identity, 설비 ID와 수용점 ID를 `generic-lh2-near-receptor-diagnostic/vertical-handoff/...` namespace로 함께 바꿨다. 사고범위 표에서도 `vertical_handoff`가 `NO_EVENT_GENERATED`에서 `PARTIAL`로 바뀌고, 조건부 chain은 10개 case 모두 숫자를 갖는다. 그러나 source history가 synthetic/operator-limited이고 전체 시설의 다른 사고군도 partial이므로 시설 전체 IR/F-N과 QRA gate는 계속 닫혀 있다.

재고 소진 결과는 `generic-lh2-full-scope-example/inventory-depletion/...`를 현재 시설 namespace로 옮겼다. 원래 `D-3ms-west`, `D-4ms-west`였던 기상·인구 조건 ID도 namespace 아래로 분리해 기존 native 조건과 충돌하지 않게 했고, 네 개의 synthetic 수용점을 현재 `worker-01`로 명시적으로 합쳤다. 수직 handoff branch도 같은 방식으로 조건 ID와 인구 수용점을 namespace·receptor map에 맞춰 변환했으며, 현재 population ledger는 `RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC`이고 mismatch가 0개다. 이 추가 branch의 10개 case는 모두 `inventory_depletion`으로 종료되며, 병합 사고군 표에서는 기존 native 재고 소진 branch와 합쳐져 `inventory_depletion` 23개 event·28개 case·조건부 28개 실행으로 보인다. 이는 기존 partial 사고군의 수치 연결을 넓히는 진단 회계이지, 현장 배관 빈도나 qualified packet을 새로 만든 것이 아니다.

빈도는 수직 또는 재고 소진 결과에서 역산하지 않았다. 기존 문헌 시나리오에 `vertical-handoff-vent`와 `inventory-depletion-pipe` 자산을 `published`로 명시해 저장된 risk atom만 재가중했다. 추가로 문헌 p05/p95가 있는 사건은 사건별 독립 경계 시나리오를 만들고, 수직 handoff·재고 소진처럼 공개 분위수가 없는 9개 진단 사건은 `fixed` 선언값을 유지했다. 따라서 5개 시나리오에서 설비별 공유 분위수와 독립 사건 경계를 비교할 수 있지만, 시설 credible interval이나 빈도 추론은 아니다. 이 union은 사고군 누락을 줄인 범위 회계와 조건부 진단이며 현장 빈도, qualified packet, 독립 물리검증, 1 Hz 신규 물리 계산을 주장하지 않는다.

`scope_matrix.json`의 예전 `uncomputed_case_count`는 operator-limited 행도 엄격한
보류 증거로 보존한다. 실제 미계산은 `not_numerically_executed_case_count`, 계산됐지만
적격 근거로 쓸 수 없는 행은 `qualified_evidence_withheld_case_count`, 숫자를 만든
행은 `numerically_executed_case_count`로 읽는다. 시설 ledger·family row·component
coverage·IJHE 감사가 같은 세 필드를 전달하므로 “미계산 29건”으로 잘못 해석하지 않는다.

산출물은 `results/20261026/native_full_scope_union_assessment/` 아래에 있다.

- `campaign_result.json`: 34개 사건·44개 case·176개 risk atom 병합 원장
- `vertical_handoff_rebound_result.json`: namespace rebind provenance가 포함된 5개 vertical 사건 원장
- `inventory_depletion_rebound_result.json`: 재고 소진 branch·조건 ID namespace rebind provenance가 포함된 5개 사건 원장
- `scope_matrix.json`: 12개 주요 사고군의 병합 상태
- `facility_assessment.json`: 조건부 IR/F-N과 시설 QRA gate
- `facility_evidence_request.json`: 각 사고군·case의 provider packet·물리검증·종료/재고 증거 요구
- `verification.json`: 병합 수·상태·제한 자동 검사
- `native_state_snapshot_campaign_ledger.json`: 새로 실행한 기본 24개 native 사건의
  상태 snapshot, component ID, provider result digest 대조. 24/24가 일치한다.
  `extension_state_snapshot_coverage.json`도 수직 handoff·inventory depletion 확장
  10개 사건의 입력 snapshot·provider echo를 10/10으로 확인한다.
- `validation_evidence_matrix.json`: 6개 근거 영역을 제한 상태로 묶은 통합 장부 (`FACILITY_QRA_WITHHELD`)
- `realtime_cache_benchmark.json`: fresh physics와 동일 요청 cache 처리시간을 분리한 실행 기록
- `state_snapshot_binding_audit.json`: native 24개 packet exporter의 원문·digest·provider echo를
  대조한다. union 전체의 상태 연결은 기본 24개 ledger와
  `extension_state_snapshot_coverage.json`의 확장 10개 event를 함께 확인하며,
  현재 34/34 event가 `BOUND_AND_ECHOED`이다.
- `ijhe_completion_audit.json`: 최신 재생은 30개 검사 중 27개 PASS·3개 BLOCKED다. `diagnostic_native_scope_packet_catalog_coverage`는 24/24 exact native packet과 상태 snapshot 결합을 확인하고, 구조적 `provider_worklist_coverage`도 PASS로 기록하지만 둘 다 diagnostic-only다. `diagnostic_observed_equipment_state_evidence`는 검사센터 Excel 3개에서 읽은 8,955개 상태 sample과 3개 component를 보존하지만 상태 증거만 기록한다. `diagnostic_slabx_lh2_validation_evidence`는 6개 FFI·6개 FLACS 비교와 질량/반복성 장부를 확인하지만 qualified provider·시설 IR/F-N을 열지 않는다. `diagnostic_native_full_bore_chain`과 `diagnostic_equipment_state_snapshot_binding`도 같은 승격 제한을 유지한다.

이번 benchmark에서는 fresh physics가 약 2.73초로 1 Hz를 충족하지 않았고, 동일 요청
cache는 10/10 hit·p95 약 23.3 ms였다. 따라서 cache 조회만 1 Hz 진단 경로로 기록되며,
상태 변화가 있는 fresh physics의 1 Hz 운영 보장은 하지 않는다. 검증 매트릭스도
풀 spreading·정상운전 관측·native 계약·조건부 시설진단·외부 sweep을 각각 제한 근거로
보존하며 독립 전체 물리검증이나 시설 전체 QRA를 열지 않는다.
