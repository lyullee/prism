# native DynamicVaporizer 압축성 plane handoff 진단

작성일: 2026-10-25  
대상: 외부 `lh2dt.DynamicVaporizer` native 사고 export와 PRISM 선택형 `prism.compressible_plane_handoff.v1`

## 실행 범위

고압 기체 출구가 PRISM 저마하 경계를 바로 통과하지 않도록, 1 MPa·300 K 합성 기화기 상태를 0.05 s 한 구간으로 실행했다. native 응답이 제공한 source pressure/temperature와 throat pressure를 동일 provider 물성 backend로 보완해 entropy, throat temperature/density/enthalpy를 만들고, 원본 native result digest와 보완 packet digest를 따로 보존했다.

```powershell
python scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --mode vaporizer `
  --source-pressure-pa-abs 1000000 `
  --horizon-s 0.05 `
  --time-step-s 0.05 `
  --output-dir results/20261025/native_dynamic_vaporizer_high_pressure_completed

python scripts/build_compressible_plane_handoff.py `
  --packet results/20261025/native_dynamic_vaporizer_high_pressure_completed/resolved_release.json `
  --provider-response results/20261025/native_dynamic_vaporizer_high_pressure_completed/provider_response.json `
  --lh2dt-root "<lh2dt_models 루트>" `
  --output-handoff results/20261025/native_dynamic_vaporizer_high_pressure_completed/compressible_handoff.json `
  --output-audit results/20261025/native_dynamic_vaporizer_high_pressure_completed/compressible_handoff_audit.json

python scripts/attach_compressible_plane_handoff.py `
  --packet results/20261025/native_dynamic_vaporizer_high_pressure_completed/resolved_release.json `
  --handoff results/20261025/native_dynamic_vaporizer_high_pressure_completed/compressible_handoff.json `
  --output-packet results/20261025/native_dynamic_vaporizer_high_pressure_completed/resolved_release_with_handoff.json `
  --output-audit results/20261025/native_dynamic_vaporizer_high_pressure_completed/attach_audit.json

python scripts/validate_compressible_plane_handoff.py `
  --packet results/20261025/native_dynamic_vaporizer_high_pressure_completed/resolved_release_with_handoff.json `
  --output results/20261025/native_dynamic_vaporizer_high_pressure_completed/handoff_validation.json

python scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261025/native_dynamic_vaporizer_high_pressure_completed/resolved_release_with_handoff.json `
  --output-dir results/20261025/native_dynamic_vaporizer_high_pressure_completed/chain
```

## 결과

* `compressible_handoff_audit.json`: `COMPRESSIBLE_PLANE_HANDOFF_GENERATED_SOURCE_STATE_BOUND`
* `handoff_validation.json`: `COMPRESSIBLE_PLANE_HANDOFF_VALIDATED`
* 최대 Mach: 약 `4.5694`
* handoff interval: 1개, provider 질량·에너지 장부 잔차: `0`
* chain: `END_TO_END_DIAGNOSTIC_EXECUTED`
* `handoff_consumed=true`, `provider_packet_qualified=false`, `physical_validation_claim=false`, `facility_qra_claim=false`

이 기록은 고속 native 기체를 압축성 plane 계약으로 연결하는 코드와 보존식 검사를 증명한다. 0.05 s active interval의 합성 geometry·초기상태·기상·수용점만 사용했으며, handoff는 notional-plane 진단이다. entropy residual은 energy-closure 알고리즘과 별도 장부로 기록되므로 이 결과를 독립적인 근접장 검증으로 해석하지 않는다. 실제 시설 QRA에는 provider가 검증된 plane 상태와 qualification/실험 근거를 제공해야 한다.
