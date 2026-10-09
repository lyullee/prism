# PRISM 방출 집계값 → 시설 ledger 소비 감사 (2026-10-24)

## 목적

provider packet이 시설 campaign에 연결되었다는 사실만으로는 방출 지속시간과
재고값이 실제로 피해 계산 입력으로 사용되었다고 말할 수 없다. 이번 감사는
저장된 `prism.resolved_release.v1` packet의 집계값과 campaign case의
`provider_packet_identity`, `termination`, `mass_ledger`를 event별로 대조한다.

이 감사는 provider를 적격으로 승격하지 않는다. `qualified_provider_packet_count`,
물리검증, 시설 IR/F-N gate는 그대로 별도 판단한다.

## 비교한 값

각 endpoint에 대해 다음 값을 digest 순서로 비교한다.

- `duration_s`
- `termination_basis`와 `termination_provenance`
- `available_mass_kg`
- `cumulative_mass_out_kg`
- case의 `termination.time_s`와 provider duration
- case의 `mass_ledger.released_kg`와 endpoint 누적 방출량 합

값이 하나라도 다르면 해당 event는 `packet_value_mismatch_event_ids`에 남고
`packet_subset_value_consumed=false`가 된다. 모든 값이 맞아도 provider의 모든
시간 단계가 downstream solver에서 독립적으로 재생됐다고 주장하지 않는다.

## 현재 generic 전체범위 진단

재현 명령:

```powershell
python scripts/audit_diagnostic_campaign_binding.py `
  --packet-evidence results/20261024/native_generic_scope_packet_evidence_v10.json `
  --campaign-result results/20261024/native_generic_scope_vertical_merged_facility_ledger_population_v3.json `
  --provider-worklist results/20261024/native_generic_scope_worklist_with_native_binding_v1.json `
  --packet-root . `
  --output results/20261024/native_generic_scope_vertical_diagnostic_campaign_binding_v5.json
```

결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| packet event | 24 |
| 값 비교 event | 24 |
| 값 일치 event | 24 |
| 값 불일치 event | 0 |
| packet subset 값 소비 | `true` |
| 시간 단계 독립 재생 주장 | `false` |
| 적격 provider packet | 0 |
| 시설 IR/F-N 승격 | `false` |

따라서 현재 결과는 **24개 native packet의 방출 집계값이 시설 case 장부와
일치한다는 진단 근거**다. 수직 handoff 5개 event는 이 packet subset에 포함되지
않으므로 전체 campaign의 packet 소비 완료로 확대하지 않는다. 또한 native packet은
합성·operator-limited 또는 독립 검증 미충족 상태이므로 시설 QRA로 승격하지 않는다.

## 코드와 테스트

- 구현: `src/lh2_tno/diagnostic_campaign_binding.py`
- CLI: `scripts/audit_diagnostic_campaign_binding.py`
- 테스트: `tests/test_diagnostic_campaign_binding.py`
- 결과: `results/20261024/native_generic_scope_vertical_diagnostic_campaign_binding_v5.json`

이 장부는 문헌 빈도를 provider packet에서 추정하지 않는다. 빈도는 기존
FrequencyPlan에서만 오며, packet의 역할은 상태에서 계산된 방출·종료·재고 집계를
피해 chain과 시설 ledger가 소비했는지 검증하는 것이다.
