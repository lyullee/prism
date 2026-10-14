# PRISM 일반 LH2 범위와 수직 벤트 확장 결합 재검증 (2026-11-10)

최신 native 일반 LH2 24개 사건 원장에 기존 `vertical_handoff`와 `inventory_depletion` 진단 캠페인을 별도 이름공간으로 결합했다. 이 작업은 수직 벤트 결과를 새로 계산했다고 주장하지 않고, 기존 provider 결과를 현재 시설 ID·수용점·설비 ID에 맞춰 재결합한 것이다.

## 실행

```powershell
python scripts/bind_native_campaign_state_snapshots.py `
  --campaign results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor/campaign.json `
  --packet-root results/20261110/native_generic_scope_packets_latest2 `
  --output results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor/campaign_state_bound.json `
  --audit-output results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor/state_snapshot_binding_audit.json

python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor `
  --base-campaign results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor/campaign_state_bound.json `
  --base-campaign-result results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor/campaign_result.json `
  --vertical-result results/20261020/vertical_vent_all_bins/campaign_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261009/equipment_inventory_campaign/campaign_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --state-snapshot-binding-audit results/20261110/native_full_scope_frequency_assessment_latest2_near_receptor/state_snapshot_binding_audit.json `
  --extension-state-snapshot-audit results/20261031/native_full_scope_union_pipefix_state_bound/extension_state_snapshot_coverage.json `
  --output-dir results/20261110/native_full_scope_union_assessment_latest2_near_vertical
```

## 결합 결과

| 항목 | 결과 |
|---|---:|
| 기본 native 사건 | 24개 |
| 수직 handoff 확장 사건 | 5개 |
| 재고 소진 확장 사건 | 5개 |
| 결합 사건 | 34개 |
| 결합 case | 44개 |
| 결합 risk atom | 176개 |
| 수직 handoff 상태 | `PARTIAL` |
| 재고 소진 상태 | `PARTIAL` |
| 기본 packet 상태 결합 | 24/24 |
| 확장 상태 snapshot/provider echo | 10/10 |
| 적격 provider packet | 0개 |
| 시설 전체 IR/F-N 승격 | 보류 |

수직 사건은 `generic-lh2-near-receptor-diagnostic/vertical-handoff/...`로, 재고 소진 사건은 `generic-lh2-near-receptor-diagnostic/inventory-depletion/...`로 분리했다. 따라서 기존 배관 hole 사건과 수직 handoff를 같은 사건으로 합치거나 빈도를 중복 적용하지 않는다. 사고군 표에서 `vertical_handoff`는 이제 `NO_EVENT_GENERATED`가 아니라 `PARTIAL`로 보인다.

## 방출부터 피해까지의 연결

결합 원장의 각 case는 설비 상태·provider 방출 경계·종료/재고 장부·SLABx-LH2 또는 확산 계산·cloud 관측·점화·화재/폭발 피해·수용점 집계 순서를 유지한다. 기본 24개 사건은 최신 native packet catalog와 연결되고, 수직·재고 확장은 기존 진단 결과의 provider identity와 종료 원장을 보존한다. `facility_chain_closure_audit.json`은 기본 packet 부분에 대해 24/24 event를 닫고 IR/F-N aggregate 불일치 0건을 확인한다. 확장 10개는 별도 `extension_state_snapshot_coverage`에서 10/10 `BOUND_AND_ECHOED`로 확인한다.

이 결과는 계산 경로가 연결됐다는 뜻이다. 수직·재고 확장 원본이 synthetic/operator-limited이고 qualified provider packet이 없으므로 현장 전체 위험도나 인증용 QRA로 해석하지 않는다.

## 최신 IJHE 감사 해석

`results/20261110/native_full_scope_union_assessment_latest2_near_vertical/ijhe_completion_audit_latest2_union.json`은 32개 검사를 수행했다. 수직 handoff 진단은 병합된 범위 행과 5개 사건·10개 case를 확인하지만, 다음 gate는 계속 차단된다.

- 모든 설비의 실제 provider 방출 packet과 독립 물리검증이 아직 없다.
- 일부 사고군은 수치 결과가 있어도 provider qualification 또는 종료 경계 증거가 부족하다.
- 시설 전체 IR/F-N은 부분·합성 범위이므로 보류된다.
- fresh physics 처리시간은 1 Hz를 보장하지 않으며, exact cache 경로만 진단적으로 1 Hz 조건을 만족한다.

따라서 최신 상태는 `INCOMPLETE_EVIDENCE`이며, 이 결합은 `vertical_handoff` 누락을 줄인 개발 단계의 증거다. 최종 승격에는 실제 설비별 packet, 독립 SLABx-LH2/실증 비교, 실제 수용점·기상·인구자료, 그리고 모든 선언 사고군의 release-boundary 폐합이 추가로 필요하다.

## 사고 포트 결합 재검증

확장 사건의 빈도 포트가 비어 있던 문제를 기존 명시적 crosswalk로 보완했다. 수직 handoff 5개와 재고 소진 5개 사건에 각각 `terminal_pipe.out`을 검토된 빈도 포트로 지정하고, provider가 내보낸 출구 포트를 빈도 근거로 추정하지 않았다.

```powershell
python scripts/bind_frequency_port_result.py `
  --campaign-result results/20261020/vertical_vent_all_bins/campaign_result.json `
  --event-port-map results/20261014/goal_continuation_port_bound/vertical_event_port_map.json `
  --output results/20261110/native_full_scope_union_assessment_latest2_near_vertical/vertical_campaign_result_port_bound.json `
  --audit results/20261110/native_full_scope_union_assessment_latest2_near_vertical/vertical_frequency_port_binding_audit.json

python scripts/bind_frequency_port_result.py `
  --campaign-result results/20261009/equipment_inventory_campaign/campaign_result.json `
  --event-port-map results/20261014/goal_continuation_port_bound/inventory_event_port_map.json `
  --output results/20261110/native_full_scope_union_assessment_latest2_near_vertical/inventory_campaign_result_port_bound.json `
  --audit results/20261110/native_full_scope_union_assessment_latest2_near_vertical/inventory_frequency_port_binding_audit.json
```

포트 결합 후 시설 평가의 `frequency_port_binding`은 34/34 port-scoped event, 0 unbound, 0 case mismatch, 0 risk-atom mismatch, `ALIGNED`다. 이 검사는 빈도와 사고 포트의 장부 정합성만 확인하며 빈도를 새로 추정하거나 provider packet을 적격으로 승격하지 않는다.

최신 결합 감사 `results/20261110/native_full_scope_union_assessment_latest2_near_vertical_port_bound/ijhe_completion_audit_latest5_restricted_component.json`은 34개 검사 중 30개를 통과하고 4개를 차단한다. 포트 결합, 설비 모델→사고 방출 인터페이스, SLABx-LH2 제한 구성요소 물리근거 검사는 통과했다. 제한 근거는 pool·실외 확산 구성요소에만 적용되며, 실제 provider packet·모든 방출 종료경계·완전한 사고범위·시설 전체 IR/F-N을 대신하지 않는다.

## 실시간 처리 계약 재검증

최신 service 코드로 cache·fresh physics·persistent worker를 다시 측정했다. 결과는 `results/20261110/native_full_scope_union_assessment_latest2_near_vertical_port_bound/realtime_cache_benchmark_latest.json`에 저장했다.

| 측정 | 결과 |
|---|---:|
| exact cache hit | 20/20 |
| cache p95 | 약 38.9 ms |
| fresh physics | 약 3.0 s |
| persistent fresh steady p50 | 약 1.89 s |
| persistent fresh steady p95/p99 | 약 1.97 s / 1.97 s |
| fresh physics 1 Hz | 불충족 |
| cache 1 Hz 진단 | 충족 |

mode contract는 `fresh_physics_background`와 `cached_diagnostic_1hz`를 구분하고, stale fallback·빈도 학습·방출 추론을 모두 `false`로 기록한다. 작은 표본에서 p95가 p50보다 작게 기록되던 분위수 계산 오류도 수정해 `scripts/benchmark_realtime_cache.py`와 회귀 테스트에 반영했다.

이 자료를 반영한 목표 감사 `results/20261110/native_full_scope_union_assessment_latest2_near_vertical_port_bound/ijhe_objective_coverage_audit_latest_realtime.json`의 상태는 `CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN`이다. 즉 설비 상태→방출→피해→조건부 IR/F-N, 문헌 빈도, 포트, mode contract, 제한 SLABx 근거의 핵심 연결은 확인됐고, 적격 provider·엄격 범위·시설 QRA 승격 gate만 남아 있다.
