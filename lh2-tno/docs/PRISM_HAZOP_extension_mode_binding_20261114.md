# PRISM 액화수소 확장 이벤트 운전 모드 결합 기록 (2026-11-14)

## 목적

수직 handoff와 inventory-depletion을 포함한 union campaign은 기존 24개 base 이벤트에 10개 extension 이벤트를 추가한다. extension 이벤트에는 base HAZOP 표의 행을 임의로 복사하거나 운전 모드를 설비 이름에서 추론하면 안 된다. 이 기록은 사용자가 명시한 운전 모드·HAZOP 행·시나리오 family·방출 모드를 실제 campaign event에 대조해 결합한 결과를 남긴다.

## 결합 규칙

`src/lh2_tno/hazop_extension_mode_binding.py`는 다음 값이 모두 명시된 경우에만 extension을 결합한다.

- 설비 component ID와 event ID prefix
- 운전 모드(`receiving`, `supply`, `standby` 등)
- HAZOP scenario ID와 row ID
- 사고 family와 release mode
- HAZOP table ID와 source provenance

campaign에 실제로 존재하지 않는 event, family, release mode는 결합하지 않는다. 모듈은 빈도값을 새로 할당하지 않고, provider release packet을 만들지 않으며, 시설 QRA 승격도 하지 않는다. 상태 snapshot digest가 있으면 campaign case에서 그대로 복사해 연결하고, 없으면 빈 값으로 남긴다.

## 최신 진단 결과

실행:

```powershell
python scripts/build_hazop_extension_mode_binding_diagnostic.py `
  --runtime-audit results/20261114/full_scope_hazop_runtime_audit_observed_runtime.json `
  --mode-binding examples/native_lh2_full_scope_hazop_mode_binding.json `
  --campaign-result results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/campaign_result.json `
  --extension-config examples/native_lh2_full_scope_hazop_extension_mode_config.json `
  --output-dir results/20261114/hazop_extension_mode_binding_fullscope_hazop_port_bound
```

| 항목 | 결과 |
|---|---:|
| extension component | 2 |
| 전체 union event | 34 |
| HAZOP→event 결합 | 34/34 |
| 미결합 event | 0 |
| 빈도 할당 | 수행하지 않음 |
| provider release 생성 | 수행하지 않음 |
| 시설 QRA 주장 | 수행하지 않음 |

이 결합 후 union의 HAZOP 선택 감사는 `HAZOP_SELECTION_EVENT_BINDING_COMPLETE`가 되었고, IJHE 완료 감사의 HAZOP 선택 검사는 `PASS`가 되었다. 이는 HAZOP 정성 단계의 identity 연결이 닫혔다는 뜻이다. 방출 경계, provider 자격, 독립 물리검증, 시설 IR/F-N은 별도 증거가 필요하므로 전체 QRA 완료를 의미하지 않는다.

## 산출물

- `examples/native_lh2_full_scope_hazop_extension_mode_config.json`
- `results/20261114/hazop_extension_mode_binding_fullscope_hazop_port_bound/hazop_runtime_audit_extension_bound.json`
- `results/20261114/hazop_extension_mode_binding_fullscope_hazop_port_bound/hazop_mode_binding_extension_bound.json`
- `results/20261114/hazop_extension_mode_binding_fullscope_hazop_port_bound/hazop_selection_event_binding_extension_bound.json`
- `results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/hazop_selection_event_binding.json`
- `results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/hazop_extension_mode_evidence_request.json`
- `results/20261114/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json`

통합 개념도는 [`LH2 위험분석 통합 흐름도`](figures/lh2_risk_flow_integrated_v2.png)이다. 현장 측정값과 운전 모드가 함께 HAZOP 판단으로 들어가며, 현재 상태와 예측 상태 모두에서 사고 빈도·공정 방출·SLABx-LH2·점화/피해·IR/F-N 모델이 같은 통합 분석 계층으로 사용된다. PRISM은 이 모델들을 연결하는 오케스트레이션 역할로 표시한다.
