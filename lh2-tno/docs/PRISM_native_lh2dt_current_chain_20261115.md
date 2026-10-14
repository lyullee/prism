# 현재 lh2dt LayeredTank native chain 재실행 (2026-11-15)

## 발견한 계약 문제

외부 `LayeredTank.export_accident_history()`는 isolation clock을 요청하지 않은
경우에도 `provider_meta`에 `isolation_time_s: null`,
`post_isolation_observation_s: 0.0`, `isolation_success: false`를 유지할 수 있다.
기존 PRISM adapter는 이 선택 필드를 모두 숫자로 읽어 `null`을 거부했기 때문에,
차단 시계를 사용하지 않는 native 사고 방출도 피해계산에 전달되지 않았다.

`equipment_release_adapter`를 다음 규칙으로 보완했다.

- 선택 numeric/boolean 필드의 `null`은 미선언으로 보존한다.
- isolation clock이 없을 때 observation `0.0`은 무의미한 기본값으로 무시한다.
- isolation clock 없이 양의 observation delay가 오면 여전히 계약 오류로 거부한다.
- 실제로 선언된 숫자와 boolean은 기존처럼 엄격히 검증한다.

## 재실행 결과

외부 모델 소스는 `lh2dt_models`의 현재 tree digest
`13a65aa75b54aee7677a1286fec1b52a149b7d0805e7908be6a0fa0ef11c1e22`를 사용했다.
합성 LayeredTank 상태·형상·개구와 대기 조건으로 native export를 호출하고,
그 응답을 PRISM strict liquid release로 변환한 뒤 같은 packet을 consequence chain에
전달했다.

| 항목 | 결과 |
|---|---:|
| native provider | `lh2dt.layered_tank.LayeredTank` |
| native export 시간 | 약 1,446 ms |
| 방출 기간 | 0.05 s |
| 방출 질량 잔차 | 0 kg |
| 방출 에너지 잔차 | 0 J |
| consequence chain | `END_TO_END_DIAGNOSTIC_EXECUTED` |
| chain 시간 | 약 19,117 ms |
| provider packet 승격 | false |
| 빈도 추론 | false |
| 시설 IR/F-N 주장 | false |

권위 실행 파일은 다음과 같다.

- [`verification.json`](../results/20261115/native_layered_tank_current_chain/verification.json)
- [`resolved_release.json`](../results/20261115/native_layered_tank_current_chain/resolved_release.json)
- [`consequence_chain/verification.json`](../results/20261115/native_layered_tank_current_chain/consequence_chain/verification.json)

## 해석

이번 실행으로 **외부 설비 상태·native 사고방출·방출 종료/질량장부·PRISM strict
packet·SLABx-LH2 피해 chain**이 현재 소스에서도 실제로 이어지는 것을 확인했다.
이는 합성 진단 연결의 증거다. 실제 시설 geometry, 현장 계측 보정, qualified provider
sidecar, 독립 물리검증과 현장 빈도는 제공되지 않았으므로 시설 전체 QRA나 IJHE의
현장 검증 결과로 승격하지 않는다.

## 재현 명령

```powershell
python scripts/run_lh2dt_native_layered_tank_smoke.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --output-dir results/20261115/native_layered_tank_current_chain `
  --run-consequence-chain
```

같은 현재 source digest로 `DynamicHEMPipe` 2상 사고도 별도 재실행했다.
0.06 s `reviewed_isolation_success` packet이 생성되고, 동일한
`validate_lh2dt_prism_packet_chain.py`를 통과해 `END_TO_END_DIAGNOSTIC_EXECUTED`를
기록했다. 결과는
[`native_dynamic_pipe_current`](../results/20261115/native_dynamic_pipe_current/)에
있다. 이 배관 실행 역시 synthetic geometry와 no-frequency 진단이며, 두 endpoint
상호작용이나 시설 전체 QRA를 의미하지 않는다.

같은 현재 source digest로 `DynamicHEMPipe` 2상 사고도 별도 재실행했다.
0.06 s `reviewed_isolation_success` packet이 생성되고, 동일한
`validate_lh2dt_prism_packet_chain.py`를 통과해 `END_TO_END_DIAGNOSTIC_EXECUTED`를
기록했다. 결과는
[`native_dynamic_pipe_current`](../results/20261115/native_dynamic_pipe_current/)에
있다. 이 배관 실행 역시 synthetic geometry와 no-frequency 진단이며, 두 endpoint
상호작용이나 시설 전체 QRA를 의미하지 않는다.
