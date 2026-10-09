# native DynamicHEMPipe 기체 source/throat·압축성 handoff 기록

작성일: 2026-10-26

## 목적

기존 DynamicHEMPipe 진단은 액체·2상 초기 상태를 사용해 대기 flash와 지상 액체를 확인했다. 같은 native class의 기체 상태는 별도 사고 가족으로 유지해야 하므로, PRISM은 이를 액체 packet으로 재분류하지 않고 기체 export와 선택형 압축성 plane handoff를 별도로 실행했다. 이번에는 차단 후 provider가 반환한 0 유량 interval도 handoff 장부에 보존했다.

```text
native DynamicHEMPipe gas state
  → export_accident_history(request)
  → source entropy + throat pressure/density/enthalpy/mass flux
  → prism.compressible_plane_handoff.v1 (활성 구간 + 0 유량 종료 구간)
  → SLABx gas consequence chain
```

## 재현 명령

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$lh2dt = "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models"

& $py scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py `
  --lh2dt-root $lh2dt `
  --source-mode gas `
  --initial-pressure-pa-abs 1000000 `
  --initial-temperature-k 300 `
  --wall-temperature-k 300 `
  --failure-opening-diameter-m 0.001 `
  --horizon-s 0.1 `
  --time-step-s 0.05 `
  --isolation-time-s 0.05 `
  --post-isolation-observation-s 0.01 `
  --output-dir results/20261026/native_dynamic_pipe_gas_isolation

& $py scripts/build_compressible_plane_handoff.py `
  --packet results/20261026/native_dynamic_pipe_gas_isolation/resolved_release.json `
  --provider-response results/20261026/native_dynamic_pipe_gas_isolation/provider_response.json `
  --lh2dt-root $lh2dt `
  --output-handoff results/20261026/native_dynamic_pipe_gas_isolation/compressible_handoff.json `
  --output-audit results/20261026/native_dynamic_pipe_gas_isolation/compressible_handoff_audit.json

& $py scripts/attach_compressible_plane_handoff.py `
  --packet results/20261026/native_dynamic_pipe_gas_isolation/resolved_release.json `
  --handoff results/20261026/native_dynamic_pipe_gas_isolation/compressible_handoff.json `
  --output-packet results/20261026/native_dynamic_pipe_gas_isolation/resolved_release_with_handoff.json `
  --output-audit results/20261026/native_dynamic_pipe_gas_isolation/attach_audit.json

& $py scripts/validate_compressible_plane_handoff.py `
  --packet results/20261026/native_dynamic_pipe_gas_isolation/resolved_release_with_handoff.json `
  --output results/20261026/native_dynamic_pipe_gas_isolation/handoff_validation.json

& $py scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261026/native_dynamic_pipe_gas_isolation/resolved_release_with_handoff.json `
  --output-dir results/20261026/native_dynamic_pipe_gas_isolation/chain
```

## 결과

| 항목 | 결과 |
|---|---:|
| native source branch | `gas` |
| 종료 근거 | `reviewed_isolation_success` |
| provider interval | 2 |
| 0 유량 종료 interval | 1 |
| 압축성 handoff | `COMPRESSIBLE_PLANE_HANDOFF_ATTACHED_AND_VALIDATED` |
| handoff 소비 | `true` |
| 최대 Mach | `3.8072504483943233` |
| 최대 에너지 잔차 | `0 J/kg` |
| 최종 chain | `END_TO_END_DIAGNOSTIC_EXECUTED` |
| qualified provider / 물리검증 / 시설 IR-FN | `false / false / false` |

`provider_response.json`의 각 기체 interval은 native pipe 상류 엔트로피와 hydraulic throat 결과로부터 `throat_temperature_k`, `throat_density_kg_m3`, `throat_specific_enthalpy_j_kg`를 보존한다. PRISM은 대기 packet 속도에서 upstream 압력을 역산하지 않는다. `max_entropy_residual_j_per_kgk`가 127.47 J/kgK로 남아 있으므로, 이 handoff는 에너지·질량 경계의 진단 연결만 확인하며 등엔트로피 물리검증으로 해석하지 않는다.

격리 성공 기체 branch에서는 차단 후 0 유량 interval이 생긴다. PRISM은 이 interval을 유량 0·속도 0 carrier section으로 보존하고, throat 상태가 빠졌는지 또는 잔여 plume을 추정하지 않는다. 따라서 방출 지속시간·차단 종료·질량 장부와 압축성 활성 구간이 같은 packet에서 닫힌다.

## 범위 제한

합성 배관 형상·초기 상태·대기·수신기·빈도 없는 단일 packet이다. 따라서 문헌 빈도, provider 자격, 독립 근접장 검증, 현장 차단 신뢰도, 시설 전체 IR/F-N을 승격하지 않는다. VentStack의 Darcy 경계와 액체·2상 provider의 근접장 계약은 여전히 별도 보완 항목이다.
