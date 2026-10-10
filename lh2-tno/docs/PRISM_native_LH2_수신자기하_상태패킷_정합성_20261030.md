# PRISM native LH2 수신자 기하·상태 패킷 정합성 보정 (2026-10-30)

## 발견한 문제

2026-10-27 상태 패킷 캠페인은 일반 시설 예시의 수용자 위치 `[20.0, 0.0, 1.0] m`에서 계산됐다.
통합 원장은 0.5 m 진단 수용자 시설을 사용하면서 결과의 `facility_id`만 바꿀 수 있었기 때문에,
상태 패킷 자체는 맞아도 피해 계산에 사용된 수용자 기하가 달라지는 문제가 있었다. 그 결과 최신
통합 원장에서 조건부 IR/F–N이 `0`으로 나타났지만, 이는 물리적 무피해 결론이 아니라 기하 불일치였다.

통합 스크립트는 이제 실행된 결과의 `facility_id`와 선택한 `base-dir/facility.json`의 ID가 다르면
즉시 실패한다. 계산 후 시설 이름을 바꾸어 수용자 기하를 대체하지 않는다.

## 보정 실행

동일한 상태 연결용 campaign과 문헌 빈도, backend pin을 사용하고,
`examples/generic_lh2_near_receptor_manifest.json`으로 수용자 기하만 명시적으로 선택해 새로
계산했다.

```powershell
python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261027/native_generic_scope_packets_state_bound/campaign_assessment/campaign.json `
  --backend-config results/20261009/backend_config_current.json `
  --output-dir results/20261030/native_near_receptor_scope_packets_state_bound
```

재계산 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| native 사건 | 24 |
| case | 24 |
| risk atom | 96 |
| provider packet identity | 24/24 보존 |
| qualified provider packet | 0 |
| 조건부 `worker-01` IR | `4.68×10⁻⁵/year` |
| 수용자 피해가 있는 atom | 1 |
| 시설 전체 QRA | 보류 |

이 결과를 vertical handoff와 inventory depletion 장부에 다시 결합했다.

```powershell
python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261026/native_full_scope_frequency_assessment `
  --base-campaign results/20261030/native_near_receptor_scope_packets_state_bound/campaign.json `
  --base-campaign-result results/20261030/native_near_receptor_scope_packets_state_bound/campaign_result.json `
  --vertical-result results/20261020/vertical_vent_all_bins/campaign_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261009/equipment_inventory_campaign/campaign_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --state-snapshot-binding-audit results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json `
  --output-dir results/20261026/native_full_scope_union_assessment
```

최종 통합 원장은 `34 events / 44 cases / 176 risk atoms`를 보존하고,
조건부 `worker-01` IR/F–N을 `4.68×10⁻⁵/year`로 기록한다. 실제 미계산 case는 0개이며,
수치가 생성됐지만 `EXECUTED_OPERATOR_LIMITED`라 적격 근거로 쓸 수 없는 case는 29개다.
문헌 빈도는 provider 방출 결과에서 역산하지 않았고, 현장 빈도나 센서 학습도 추가하지 않았다.

## 검증한 fail-closed 동작

20 m 시설에서 계산된 이전 state-bound `campaign_result.json`을 0.5 m 시설의 `base-dir`에
넣어 실행하면 다음 오류로 중단된다.

```text
base campaign result facility_id does not match base facility id; recompute the campaign with the selected facility geometry before union
```

따라서 이름만 바꾼 피해 결과가 통합 원장에 들어갈 수 없다. 새로 계산한 결과는 이 검사를 통과했고,
`results/20261026/native_full_scope_union_assessment/`의 `ijhe_completion_audit.json`과
`v060_readiness_report.json`도 다시 생성했다.

현재 준비도는 `CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN`이며, 다음 네 가지는 여전히
차단된다.

- qualified provider evidence
- independent physical validation
- strict facility accident scope
- strict facility QRA

따라서 이번 보정은 수치 chain의 기하 정합성과 재현성을 고친 것이며, 시설 전체 QRA 승인이나 현장
사고빈도 확보를 의미하지 않는다.
