# Native LH2 시설 chain의 HAZOP 운전 모드 전달

## 목적

시설 사건을 계산할 때 운전 모드를 별도 설명으로 남기지 않고, 명시적 HAZOP mode/scenario binding으로 입력한다. 같은 입력이 event route, 설비 provider request, 피해영향 계산 case, risk atom까지 유지되는지를 확인한다.

```text
명시적 현장/시뮬레이션 상태 + 운전 모드
  → HAZOP 시나리오 ID
  → 설비별 방출 packet
  → 지속시간·차단·재고 경계
  → SLABx-LH2/SLABx 피해 계산
  → 기상·점화·인구·IR/F-N risk atom
```

## 실행

```powershell
python scripts/run_native_isolation_catalog_facility_chain.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261019/generic_native_packet_rebound_campaign.json `
  --catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --backend-config results/20261009/backend_config_current.json `
  --hazop-mode-binding examples/native_lh2_full_scope_hazop_mode_binding.json `
  --output-dir results/20261112/native_isolation_catalog_facility_chain_hazop_mode
```

`examples/native_lh2_full_scope_hazop_mode_binding.json`은 event ID별 `component_id`, `operating_mode`, `hazop_scenario_id`, release mode를 모두 명시한다. 현재 파일은 일반 시설 연결을 재현하기 위한 합성 generic 입력이다. 실제 시설에서는 현장 상태 프레임 또는 검토된 HAZOP/P&ID에서 같은 형식의 binding을 공급해야 한다.

## 확인 결과

| 항목 | 결과 |
|---|---:|
| HAZOP event | 24 |
| mode/scenario bound event | 24 |
| mode 누락 | 0 |
| scenario ID 누락 | 0 |
| mode 충돌 | 0 |
| consequence case | 24 |
| risk atom | 96 |
| 조건부 시설 위험 경로 | `true` |
| 적격 provider 승격 | `false` |
| 시설 전체 IR/F-N 승격 | `false` |

결과 파일은 [`hazop_event_mode_binding.json`](../results/20261112/native_isolation_catalog_facility_chain_hazop_mode/hazop_event_mode_binding.json), [`campaign_result.json`](../results/20261112/native_isolation_catalog_facility_chain_hazop_mode/campaign_result.json), [`scope_closure_report.json`](../results/20261112/native_isolation_catalog_facility_chain_hazop_mode/scope_closure_report.json)이다. `scope_closure_report.json.evidence_gates.hazop_mode_binding`은 24/24 전달을 별도로 기록한다.

## 해석 경계

- mode와 HAZOP 시나리오는 입력으로 전달되며, 압력·온도·누출면적·설비 종류에서 역으로 추정하지 않는다.
- mode가 없는 실제 입력은 `HAZOP_EVENT_MODE_BINDING_REQUIRED`로 보류해야 한다.
- mode binding은 빈도를 만들거나 바꾸지 않는다. 빈도는 별도 문헌 catalogue 입력으로만 적용된다.
- 계산된 24개 case 중 operator-limited 또는 domain-incomplete case는 strict 방출 경계에서 계속 보류한다.
- 합성 HAZOP 표와 synthetic 시설 조건만으로는 적격 provider, 독립 물리검증, 현장 시설 전체 IR/F-N을 주장할 수 없다.
