# native LayeredTank 차단시간·방출 연결 기록 (2026-10-25)

## 이번 보완의 목적

기존 탱크 진단 adapter는 외부 `LayeredTankNetworkSimulator`를 PRISM 쪽에서 호출해 사고 이력을 구성했다. 최신 `lh2dt_models`에는 탱크 클래스 자체의 `export_accident_history(request)`가 있으므로, 이번 보완에서는 그 native 메서드를 직접 호출하고 PRISM strict liquid boundary로 검증한다.

```text
native LayeredTank state
  → native export_accident_history(request)
  → explicit isolation_time_s + post_isolation_observation_s
  → prism.external_accident_history.v1
  → ResolvedLiquidRelease
  → SLABx-LH2 / pool / ignition / damage 입력
```

PRISM은 이 과정에서 개구, 방출시간, 차단 성공 또는 재고 소진을 추정하지 않는다. 모두 provider 응답의 종료 원장으로 받아서 검사한다.

## 재현 명령

외부 모델 소스 경로는 로컬 환경에 맞게 바꾼다.

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$lh2dt = "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models"

& $py scripts/export_lh2dt_native_layered_tank_prism_packet.py `
  --lh2dt-root $lh2dt `
  --output-dir results/20261025/native_layered_tank_isolation `
  --horizon-s 0.1 `
  --time-step-s 0.05 `
  --minimum-step-s 0.0005 `
  --isolation-time-s 0.05 `
  --post-isolation-observation-s 0.01
```

## 확인 결과

결과는 [`verification.json`](../results/20261025/native_layered_tank_isolation/verification.json)에 저장했다.

| 항목 | 결과 |
|---|---:|
| native provider method | `export_accident_history` |
| provider schema | `prism.external_accident_history.v1` |
| PRISM resolved schema | `prism.resolved_release.v1` |
| 종료 근거 | `reviewed_isolation_success` |
| 차단 시점 | 0.05 s |
| 차단 후 관찰 | 0.01 s |
| 전체 provider 이력 | 0.060000 s |
| 질량 잔차 | 약 `-5.7×10⁻¹⁴ kg` |
| 상태 snapshot digest | provider echo와 일치 |
| provider 승격 | `false` |

첫 구간에는 액체·기체 flash 분할이 있고, 차단 후 구간에는 유량이 0으로 남는다. 따라서 downstream PRISM chain은 native provider의 시간 이력을 그대로 소비한다.

같은 `resolved_release.json`을 [`validate_lh2dt_prism_packet_chain.py`](../scripts/validate_lh2dt_prism_packet_chain.py)에 넣은 결과는 [`chain/verification.json`](../results/20261025/native_layered_tank_isolation/chain/verification.json)의 `END_TO_END_DIAGNOSTIC_EXECUTED`이다. `equipment_liquid_release` 경계에서 0.060000 s provider history와 질량 잔차 0 kg을 읽고, SLABx-LH2/풀/점화/피해 단계까지 실행했다. chain 명령에는 initiating frequency를 넣지 않았으므로 IR/F-N을 계산하거나 시설 위험으로 합산하지 않는다.

## 해석 범위

이 실행은 연결 회귀와 종료 원장 검증이다. 형상, 초기 재고, 개구, 대기 조건은 합성값이며 현장 계측이나 독립 실험으로 보정하지 않았다. 따라서 이 결과는 `qualified_actual` packet, 사고빈도, 시설 전체 IR/F-N, 물리검증을 만들지 않는다. 실제 시설에 사용하려면 같은 event/component/port와 source/result digest를 가진 provider qualification sidecar와 독립 검증 자료를 별도로 제출해야 한다.
