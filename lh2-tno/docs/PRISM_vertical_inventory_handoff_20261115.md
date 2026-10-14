# PRISM 수직 handoff 재고소진 연결 기록 (2026-11-15)

이번 기록은 기존 수직 벤트 계산의 `synthetic_diagnostic_horizon`을 늘려
해석한 것이 아니다. `results/20261009/equipment_inventory_campaign/`에 이미
저장된 provider 소유의 유한 재고·양의 소진 임계값 이력을 다섯 수직 area-bin
event에 정확히 재결합하고, 그 결과에 수직 출구와 수평 SLABx-LH2 handoff를
붙여 일반 PRISM 연쇄 계산을 다시 실행했다.

## 결과

| 항목 | 결과 |
|---|---:|
| 수직 event | 5 |
| 수직 weather case | 10 |
| 종료 기준 | 5개 모두 `inventory_depletion` |
| 전체 union event / case / risk atom | 34 / 44 / 176 |
| provider 종료 증거 catalog | 34 event row, 32 case 사용, 2 unsupported basis |
| 명시적 사고 포트 | 34/34, unbound 0, case/risk-atom mismatch 0 |
| 수직 numerical closure | 10/10 `NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED` |
| 시설 IR/F-N 승격 | 보류 |

각 수직 case는 provider의 초기 재고, 누적 방출, 잔여 재고, 임계값,
질량 잔차와 결과 digest를 보존한다. 잔여 재고를 0으로 치환하지 않았으며,
수직 자유제트와 수평 handoff의 물리 검증을 주장하지 않는다. `input_origin`은
계속 `synthetic`, case 상태는 `EXECUTED_OPERATOR_LIMITED`로 남는다.

## 재현 명령

```powershell
python scripts/run_vertical_inventory_handoff_campaign.py `
  --vertical-dir results/20261020/vertical_vent_all_bins `
  --inventory-dir results/20261009/equipment_inventory_campaign `
  --backend-config results/20261020/vertical_vent_all_bins/backend_config.json `
  --output-dir results/20261115/vertical_inventory_handoff_campaign

python scripts/rebind_vertical_handoff_campaign.py `
  --vertical-result results/20261115/vertical_inventory_handoff_campaign/campaign_result.json `
  --facility-id generic-lh2-full-scope-example `
  --namespace generic-lh2-full-scope-example/vertical-handoff `
  --asset-id vertical-handoff-vent `
  --component-id vertical-handoff-terminal-pipe-01 `
  --receptor-map near_worker=worker-01 `
  --receptor-map downwind_worker=worker-01 `
  --receptor-map side_worker=worker-01 `
  --receptor-map distant_worker=worker-01 `
  --output results/20261115/vertical_inventory_handoff_rebound_facility_result.json `
  --provenance-output results/20261115/vertical_inventory_handoff_rebound_facility.provenance.json

python scripts/bind_frequency_port_result.py `
  --campaign-result results/20261115/vertical_inventory_handoff_rebound_facility_result.json `
  --event-port-map results/20261115/vertical_inventory_handoff_event_port_map.json `
  --output results/20261115/vertical_inventory_handoff_rebound_facility_result_port_bound.json `
  --audit results/20261115/vertical_inventory_handoff_frequency_port_binding_audit.json

python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound `
  --base-campaign results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/campaign.json `
  --base-campaign-result results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/campaign_result.json `
  --vertical-result results/20261115/vertical_inventory_handoff_rebound_facility_result_port_bound.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261115/inventory_campaign_result_port_bound.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --state-snapshot-binding-audit results/20261114/base_state_snapshot_binding_audit_port_bound.json `
  --extension-state-snapshot-audit results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/extension_state_snapshot_coverage.json `
  --hazop-runtime-audit results/20261114/full_scope_hazop_runtime_audit_observed_runtime.json `
  --hazop-mode-binding results/20261114/hazop_extension_mode_binding_fullscope_hazop_port_bound/hazop_mode_binding_extension_bound.json `
  --output-dir results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound
```

종료 증거와 조건부 view는 다음 명령으로 재생성한다.

```powershell
python scripts/materialize_vertical_inventory_termination_evidence.py `
  --rebound-result results/20261115/vertical_inventory_handoff_rebound_facility_result_port_bound.json `
  --provider-responses results/20261009/equipment_inventory_campaign/provider_responses.json `
  --output-dir results/20261115/vertical_inventory_handoff_campaign/termination_evidence

python scripts/build_provider_termination_evidence_catalog.py `
  --storage-catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --additional-storage-catalog-dir results/20261115/vertical_inventory_handoff_campaign/termination_evidence `
  --inventory-provider-responses results/20261009/equipment_inventory_campaign/provider_responses.json `
  --inventory-resolved-releases results/20261009/equipment_inventory_campaign/resolved_releases.json `
  --output results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff.json

python scripts/audit_release_boundary_cases.py `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/facility_assessment.json `
  --facility-evidence-request results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/facility_evidence_request.json `
  --provider-termination-evidence results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff.json `
  --output results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff.json
```

## 해석 경계

이번 연결로 수직 방출의 **계산 경로와 수치 재고 장부**는 닫혔다. 그러나
운영자 제한 상태, synthetic provider 입력, 수직 자유제트·handoff 독립 검증
부재 때문에 시설 QRA나 실제 설비 인증 자료로 승격하지 않는다. 나머지 전체
union의 30개 case는 여전히 운영자 제한·도메인 절단·비상 방출·600초 horizon·양단
파열 등 별도의 증거 요청을 갖는다. 사고빈도는 문헌값을 그대로 사용했고 현장
빈도나 센서 역추론은 수행하지 않았다.

최신 권위 산출물은
`results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/`,
`results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff.json`,
`results/20261115/conditional_facility_risk_view_with_release_trace.json`,
`results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_port_bound.json`이다.
최신 IJHE 감사는 50개 검사 중 46개 `PASS`, 4개 `BLOCKED`, 상태
`INCOMPLETE_EVIDENCE`이다.
