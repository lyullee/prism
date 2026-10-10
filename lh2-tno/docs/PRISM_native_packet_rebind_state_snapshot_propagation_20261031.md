# PRISM native packet rebind 상태 snapshot 재결합 (2026-10-31)

## 발견한 연결 결함

native 설비 exporter는 사고 packet(`resolved_release.json`)과 상태 전용
`verification.json`을 분리해 저장합니다. 기존 packet rebind는 사고 packet만
campaign 요청에 넣었기 때문에, packet 자체에는 provider 결과가 있었어도
통합 원장에서는 요청의 canonical `EquipmentStateSnapshot`이 비어 있을 수
있었습니다. 이 상태에서는 방출 계산은 실행되지만 “어떤 설비 상태에서 이
방출이 만들어졌는가”를 시설 case까지 재현할 수 없습니다.

## 코드 보완

`src/lh2_tno/campaign_packet_rebind.py`의 rebind 단계가 선택된 packet 옆의
`verification.json`을 읽고 다음을 수행합니다.

1. canonical `prism.equipment_state_snapshot.v1`을 엄격히 검증합니다.
2. packet component와 snapshot component가 같은지 확인합니다.
3. canonical snapshot digest와 provider echo digest를 비교합니다.
4. 검증된 snapshot, `state_snapshot_digest`,
   `provider_state_snapshot_digest`, `provider_state_snapshot_digests`를
   새 campaign request에 함께 기록합니다.

검증 sidecar가 없는 오래된 테스트 fixture는 기존 동작을 유지하지만,
worklist evidence가 `BOUND_AND_ECHOED`인 native packet에는 상태 snapshot을
누락시키지 않습니다. 빈도는 여전히 PRISM 문헌 catalogue에서만 가져오며,
상태 snapshot으로 빈도를 추정하지 않습니다.

## 재실행 결과

```powershell
python scripts/rebind_campaign_to_worklist_packets.py `
  --campaign results/20261027/native_generic_scope_packets_state_bound/campaign_assessment/campaign.json `
  --packet-evidence results/20261031/native_generic_scope_packets_pipefix/packet_evidence.json `
  --packet-root results/20261031/native_generic_scope_packets_pipefix `
  --output results/20261031/native_generic_scope_packets_pipefix/campaign_rebound_state_bound.json

python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261031/native_generic_scope_packets_pipefix/campaign_rebound_state_bound.json `
  --backend-config results/20261009/backend_config_current.json `
  --output-dir results/20261031/native_full_scope_frequency_pipefix_state_bound

python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261026/native_full_scope_frequency_assessment `
  --base-campaign results/20261031/native_generic_scope_packets_pipefix/campaign_rebound_state_bound.json `
  --base-campaign-result results/20261031/native_full_scope_frequency_pipefix_state_bound/campaign_result.json `
  --vertical-result results/20261020/vertical_vent_all_bins/campaign_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261009/equipment_inventory_campaign/campaign_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --state-snapshot-binding-audit results/20261031/native_generic_scope_packets_pipefix/state_snapshot_binding_audit.json `
  --extension-state-snapshot-audit results/20261026/native_full_scope_union_assessment/extension_state_snapshot_coverage.json `
  --output-dir results/20261031/native_full_scope_union_pipefix_state_bound
```

새 원장은 34 events, 44 cases, 176 risk atoms를 보존합니다. 상태→방출
감사에서 44/44 case가 complete이고, provider termination echo gap과
상태 digest mismatch는 각각 0건입니다. IJHE completion audit는 42개 검사
중 37개를 통과하고 5개를 차단합니다. 차단 항목은 qualified provider
evidence, 독립 물리검증, 선언 사고범위 완결, 시설 전체 IR/F-N, 시설 case별
qualified packet coverage입니다. 따라서 이번 수정은 chain 연결과 재현성을
완성한 것이며, synthetic/operator-limited 결과를 현장 QRA로 승격하지
않습니다.

## 회귀 확인

- PRISM: `770 passed, 1 skipped`
- 외부 `lh2dt`: `1494 passed, 0 failed, 0 skipped`
- native generic catalog: 24/24 exact packet, 0 uncomputed
- 상태 snapshot: 24/24 bound and echoed
- facility state→release audit: 44/44 complete

자세한 현재 상태는 [`results/20261031/native_full_scope_union_pipefix_state_bound/ijhe_completion_audit.json`](../results/20261031/native_full_scope_union_pipefix_state_bound/ijhe_completion_audit.json)과 [`v060_readiness_report.json`](../results/20261031/native_full_scope_union_pipefix_state_bound/v060_readiness_report.json)에 기록합니다.
