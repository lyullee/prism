# native DynamicHEMPipe 차단시간·2상 방출 연결 기록 (2026-10-25)

## 보완 내용

외부 `lh2dt.DynamicHEMPipe.export_accident_history(request)`를 PRISM의 strict liquid/two-phase release 경계에 직접 연결했다. PRISM-side `step()` 재현기가 사고 이력을 대신 만들지 않고, native 배관이 계산한 유량·flash 분할·재고·차단 종료를 그대로 소비한다.

```text
DynamicHEMPipe native finite-volume state
  → native export_accident_history(request)
  → gas/ground-liquid flash history
  → explicit isolation termination ledger
  → prism.resolved_release.v1
  → SLABx-LH2 / pool / ignition / damage
```

## 재현 명령

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$lh2dt = "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models"

& $py scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py `
  --lh2dt-root $lh2dt `
  --output-dir results/20261025/native_dynamic_pipe_isolation
```

## 결과

[`verification.json`](../results/20261025/native_dynamic_pipe_isolation/verification.json)은 다음을 기록한다.

| 항목 | 결과 |
|---|---:|
| native provider method | `export_accident_history` |
| phase basis | `two_phase` |
| 종료 근거 | `reviewed_isolation_success` |
| 차단 시점/관찰 | 0.05 s / 0.01 s |
| 전체 provider 이력 | 0.060000 s |
| 질량 잔차 | provider 원장 기준 0 kg |
| airborne liquid | 0 (native 계약의 보수적 제한) |
| provider 승격 | `false` |

동일 packet을 [`validate_lh2dt_prism_packet_chain.py`](../scripts/validate_lh2dt_prism_packet_chain.py)로 재생한 [`chain/verification.json`](../results/20261025/native_dynamic_pipe_isolation/chain/verification.json)은 `END_TO_END_DIAGNOSTIC_EXECUTED`이며 `equipment_liquid_release`에서 SLABx-LH2/풀/점화/피해까지 실행됐다. initiating frequency는 넣지 않았으므로 시설 IR/F-N을 계산하지 않는다.

하향 출구를 수직 handoff 없이 자동 회전시키지 않기 위해 이 일반 진단은 수평 outlet 방향을 명시한다. 실제 수직 벤트·하향 배출은 provider가 `VerticalGasHandoff`를 함께 제출해야 한다.

## 제한사항

배관 길이·직경·초기 2상 상태·대기 조건은 합성값이다. native export의 존재와 chain 실행은 qualified provider packet, 현장 빈도, 독립 물리검증, 시설 전체 IR/F-N을 의미하지 않는다. 실제 시설 적용에는 source/result digest와 provider qualification sidecar가 필요하다.
