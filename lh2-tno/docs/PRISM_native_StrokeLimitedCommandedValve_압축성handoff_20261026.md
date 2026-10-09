# native `StrokeLimitedCommandedValve` 압축성 handoff 진단

## 연결한 경로

외부 `lh2dt.StrokeLimitedCommandedValve`가 계산한 native source/throat 상태를 PRISM strict gas packet에 보존한 뒤, 선택형 `prism.compressible_plane_handoff.v1`를 붙였다.

```powershell
python scripts/export_lh2dt_native_valve_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --output-dir results/20261025/native_stroke_valve

python scripts/build_compressible_plane_handoff.py `
  --packet results/20261025/native_stroke_valve/resolved_release.json `
  --provider-response results/20261025/native_stroke_valve/provider_response_strict.json `
  --lh2dt-root "<lh2dt_models 루트>" `
  --output-handoff results/20261026/native_stroke_valve_high_pressure/compressible_handoff.json `
  --output-audit results/20261026/native_stroke_valve_high_pressure/compressible_handoff_audit.json

python scripts/attach_compressible_plane_handoff.py `
  --packet results/20261025/native_stroke_valve/resolved_release.json `
  --handoff results/20261026/native_stroke_valve_high_pressure/compressible_handoff.json `
  --output-packet results/20261026/native_stroke_valve_high_pressure/resolved_release_with_handoff.json `
  --output-audit results/20261026/native_stroke_valve_high_pressure/attach_audit.json

python scripts/validate_compressible_plane_handoff.py `
  --packet results/20261026/native_stroke_valve_high_pressure/resolved_release_with_handoff.json `
  --output results/20261026/native_stroke_valve_high_pressure/handoff_validation.json

python scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261026/native_stroke_valve_high_pressure/resolved_release_with_handoff.json `
  --output-dir results/20261026/native_stroke_valve_high_pressure/chain
```

## 확인된 결과

| 항목 | 결과 |
|---|---|
| source/throat 입력 | 2개 native interval 모두 exact digest로 연결 |
| handoff 상태 | `COMPRESSIBLE_PLANE_HANDOFF_ATTACHED_AND_VALIDATED` |
| 최대 Mach | 약 `2.2855` |
| 에너지 잔차 | `0 J/kg` |
| handoff 소비 | `true` |
| 최종 피해 chain | `END_TO_END_DIAGNOSTIC_EXECUTED` |

이 handoff는 PRISM의 보존식 기반 notional plane adapter가 만든 진단 경계다. native 밸브의 상류 재고·차단 신뢰도·현장 빈도는 여전히 외부 입력이고, handoff 자체도 provider가 독립적으로 검증한 실제 근접장 해가 아니다. 따라서 `provider_packet_qualified=false`, `physical_validation_claim=false`, `facility_qra_claim=false`를 유지한다. 고압 밸브 상태가 chain에 소비된다는 사실은 확인했지만, 시설 전체 IR/F-N이나 IJHE용 완전 QRA로 승격하지 않는다.
