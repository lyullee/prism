# PRISM HAZOP 전체 이벤트 선택·빈도 이벤트 연결 감사 (2026-11-14)

이번 감사는 다설비 HAZOP 실행에서 대표 행만 계산되던 문제를, 사고 시나리오 선택 단계에서 명시적으로 보완한 기록이다. 목표는 HAZOP가 선택한 사고군이 문헌 빈도 이벤트의 설비·운전 모드·방출 모드와 실제로 연결되는지 확인하는 것이다. 이 작업은 빈도를 새로 만들거나 provider 방출 packet을 생성하는 작업이 아니다.

## 확인한 누락

기존 다설비 runtime 표에는 설비별 대표 행 7개가 있었다.

| 설비 | 기존 대표 HAZOP family | 전체 frequency campaign에서 추가로 확인된 family |
|---|---|---|
| ambient-vaporizer-01 | `inventory_depletion` | `inventory_over_600s`, `vaporizer_hole` |
| reliquefier-01 | `two_sided_rupture` | `reliquefier_hole` |

나머지 설비는 기존 대표 행이 해당 event의 허용 family 중 하나와 일치했다. 따라서 없는 행을 다른 사고군으로 대체하지 않고, 위 3개 family만 별도의 범위 감사 행으로 추가했다.

## 구현

- `src/lh2_tno/hazop_scope_runtime.py`
  - 명시적 campaign event와 HAZOP mode binding을 읽는다.
  - 기존 HAZOP 행의 센서 tag·단위·threshold를 재사용한다.
  - campaign에 실제로 선언된 family와 release mode가 기존 표에 없을 때만 행을 추가한다.
  - mode·family·release mode가 없는 event는 보류한다.
  - 빈도 할당, provider packet 생성, 피해영향 계산, 시설 QRA 승격은 수행하지 않는다.
- `scripts/build_full_scope_hazop_runtime_audit.py`
  - 범위 HAZOP 표, 관측 runtime 선택 감사, HAZOP→frequency event identity 감사를 각각 저장한다.
- `src/lh2_tno/hazop_event_selection_audit.py`
  - 하나의 HAZOP 선택이 여러 LOC event bin으로 확장되는 관계를 event ID 단위로 확인한다.

## 최신 재실행 결과

실행 명령:

```powershell
python scripts/build_full_scope_hazop_runtime_audit.py `
  --campaign-result results/20261114/native_isolation_catalog_facility_chain_hazop_runtime_bound/campaign_result.json `
  --output results/20261114/full_scope_hazop_runtime_audit.json

python scripts/run_native_isolation_catalog_facility_chain.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261019/generic_native_packet_rebound_campaign.json `
  --catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --backend-config results/20261009/backend_config_current.json `
  --hazop-mode-binding examples/native_lh2_full_scope_hazop_mode_binding.json `
  --hazop-runtime-audit results/20261114/full_scope_hazop_runtime_audit_observed_runtime.json `
  --output-dir results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop

python scripts/build_scope_closure_report.py `
  --scope-matrix results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop/scope_matrix.json `
  --facility-assessment results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop/facility_assessment.json `
  --frequency-scenarios results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop/frequency_scenarios.json `
  --hazop-mode-binding results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop/hazop_event_mode_binding.json `
  --hazop-selection-event-binding results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop/hazop_selection_event_binding.json `
  --output results/20261114/scope_closure_report_fullscope_hazop.json
```

핵심 결과는 다음과 같다.

- HAZOP 선택 시나리오: 10개
- 문헌 빈도 event: 24개
- HAZOP→event identity bound: 24/24
- unbound event: 0개
- 운전 모드 추론: 수행하지 않음
- 빈도 할당·빈도 추론: 수행하지 않음
- provider packet 생성: 수행하지 않음
- 시설 전체 QRA 승격: 수행하지 않음

따라서 “어떤 HAZOP 사고군이 어떤 빈도 event bin을 대상으로 하는가”라는 정성적 연결은 24개 event 전체에 대해 닫혔다. 이것은 24개 방출을 모두 자격 있는 provider로 계산했다는 뜻이 아니다.

## 남아 있는 제한

재실행된 시설 chain은 `PARTIAL_FACILITY_SCOPE`이다. 24개 case와 96개 risk atom이 생성되었지만 20개 case는 `EXECUTED_OPERATOR_LIMITED` 또는 검토되지 않은 종료·차단·재고 경계 때문에 strict 방출 원장에서 보류된다. provider packet 자격, 독립적인 전체 near-field 물리검증, 실제 설비 geometry·차단 신뢰도, 시설 전체 연간 IR/F-N 승격은 여전히 닫혀 있다. 이 결과는 HAZOP 선택과 문헌 event identity가 완성되었음을 보여주는 진단 장부이며, 시설 QRA 완료 선언이 아니다.

주요 결과 파일:

- `results/20261114/full_scope_hazop_runtime_audit.json`
- `results/20261114/full_scope_hazop_runtime_audit_table_set.json`
- `results/20261114/full_scope_hazop_runtime_audit_event_binding.json`
- `results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop/hazop_selection_event_binding.json`
- `results/20261114/scope_closure_report_fullscope_hazop.json`
- `results/20261114/ijhe_completion_audit_fullscope_hazop.json`

IJHE 완료 감사에도 `diagnostic_hazop_selection_event_binding = PASS`로 연결했다. 전체 감사 상태는 방출 경계·provider 자격·물리검증·시설 IR/F-N·빈도 불확실성 장부가 아직 닫히지 않아 `INCOMPLETE_EVIDENCE`로 남는다.

시설 chain이 생성한 `facility_assessment.json`의 문헌 빈도 불확실성 원장도 같은 campaign에 명시적으로 연결했다. `results/20261114/ijhe_completion_audit_fullscope_hazop_with_uncertainty.json`에서는 조건부 known-atom 빈도 민감도 검사와 HAZOP event identity 검사가 모두 `PASS`가 되었고, 전체 감사 차단 사유는 6개에서 5개로 줄었다. 이 결과는 문헌 p05/published/p95 재가중 증거를 연결한 것이며, 시설 credible interval이나 시설 전체 QRA 승격은 아니다.
