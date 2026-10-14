# PRISM native 문헌 빈도–격리 branch 시설 union 재결합 기록 (2026-11-15)

이번 재실행은 `LH2_VESSEL AREA_0.01%` 문헌 빈도 행을 현재 외부 `lh2dt_models`의
`LayeredTank` 사고 exporter로 계산하고, provider가 선언한 짧은 격리 성공 경계를 기존
일반 액화수소시설 원장에 다시 결합한 기록이다. 단일 사례만 확인한 것이 아니라 기존
24개 기본 사건, 수직 handoff 5개, 재고소진 5개를 같은 시설 namespace에서 다시 합쳤다.

## 결과

| 항목 | 결과 |
|---|---:|
| 기본 사건 / 수직 handoff / 재고소진 | 24 / 5 / 5 |
| 병합 사건 / case / risk atom | 34 / 44 / 176 |
| 대상 사건 | `generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%` |
| 대상 빈도 | 문헌 campaign 행에서 직접 바인딩 (`0.00065 1/yr`) |
| 대상 방출 종료 | provider `reviewed_isolation_success` |
| 격리 시각 / 관찰 지연 | `0.00005 s / 0.00005 s` |
| provider 초기·최종 질량 | `71.7644005715 kg → 71.7643992311 kg` |
| provider 질량 잔차 | `0 kg` |
| native export / 전체 chain | 약 `155.7 ms / 146.1 s` |
| 최종 상태 | `NATIVE_FULL_SCOPE_UNION_DIAGNOSTIC` |
| 시설 IR/F-N 승격 | `false` |

대상 사건은 문헌 개구면적과 native provider 개구가 일치하고, 방출 포트가
`tank-accident-out`으로 결합된다. 방출 packet은 PRISM의 SLABx-LH2/풀·확산·점화·피해
단계를 거쳐 risk atom으로 들어간다. 그 뒤 수직 handoff와 재고소진 확장 사건도 같은
facility ledger에서 보존된다.

## 재현 명령

```powershell
python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261115/native_lh2dt_frequency_case_isolation_current/campaign.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output-dir results/20261115/native_full_scope_frequency_assessment_isolation_current

python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261115/native_full_scope_frequency_assessment_isolation_current `
  --base-campaign results/20261115/native_full_scope_frequency_assessment_isolation_current/campaign.json `
  --base-campaign-result results/20261115/native_full_scope_frequency_assessment_isolation_current/campaign_result.json `
  --vertical-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/vertical_handoff_rebound_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/inventory_depletion_rebound_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --extension-state-snapshot-audit results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/extension_state_snapshot_coverage.json `
  --output-dir results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current
```

## 해석 경계

이번 작업으로 **문헌 빈도 → native 설비 방출 → 격리 종료 → SLABx-LH2 피해 → 기존
시설 ledger**의 재결합은 확인됐다. 그러나 이것은 실제 현장 빈도나 적격 provider packet을
만든 것이 아니다. provider는 현재 외부 source worktree의 model-prediction packet이고,
시설 전체 12개 사고군의 독립 검증과 모든 방출 종료 경계가 닫히지 않았다. 따라서
`facility_total_risk_available=false`, `qualified_provider_packet_count=0`,
`physical_validation_claim=false`, `complete_facility_qra_claim=false`를 유지한다.
짧은 격리 branch는 계산 경계가 닫힌 한 사례를 보여주는 진단용 결과이며, 탱크 전체
재고 소진이나 장시간 사고를 의미하지 않는다.

권위 산출물은 이 디렉터리의 `verification.json`, `campaign_result.json`,
`facility_assessment.json`이다.
