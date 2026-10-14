# DynamicHEMPipe 이송 배관 차단 연결 진단

## 목적

기존 일반 액화수소시설 worklist의 이송 배관 5개 개구율(`AREA_0.01%`, `0.1%`, `1%`, `10%`, `100%`)은 짧은 고정 시간으로 끝나는 진단 패킷이었다. 이 기록은 외부 `lh2dt.DynamicHEMPipe`가 사고 시작 후 명시된 차단 시각에 출구를 닫고, 차단 후 관찰구간까지 반환하는지 확인한 결과다.

## 실행 결과

| 개구율 | 차단 시각(s) | 차단 후 관찰(s) | 총 기록(s) | 종료 근거 | 질량 잔차(kg) |
|---:|---:|---:|---:|---|---:|
| 0.01% | 0.00500 | 0.05000 | 0.05500 | `reviewed_isolation_success` | 0 |
| 0.1% | 0.00050 | 0.05000 | 0.05050 | `reviewed_isolation_success` | 0 |
| 1% | 0.00010 | 0.05000 | 0.05010 | `reviewed_isolation_success` | 0 |
| 10% | 0.00005 | 0.05000 | 0.05005 | `reviewed_isolation_success` | 0 |
| 100% | 0.00001 | 0.00050 | 0.00051 | `reviewed_isolation_success` | 0 |

패킷은 다음 디렉터리에 저장되어 있다.

`results/20261014/hazop_isolation_packets/transfer-line-01-AREA_<bin>/`

각 디렉터리의 `provider_response.json`에는 차단 시각, 차단 후 관찰시간, `isolation_success=true`, 제공자 질량수지 잔차가 있고, `resolved_release.json`은 PRISM의 엄격한 액체/2상 방출 경계로 검증된다.

## 통합 경로

`run_hazop_lh2_multiequipment_provider_diagnostic.py --isolation-packet-root results/20261014/hazop_isolation_packets` 실행에서 대표 이송 배관 사건(`AREA_100%`)을 자동 선택하도록 연결했다. 그 결과:

- 7개 설비 모두 HAZOP 운전모드 판단 → 제공자 방출 → SLABx-LH2 결과 → 현재 기상 조건부 위험 원자까지 도달했다.
- 이송 배관은 `source_duration_mode=declared`로 전달되어, 명시적 차단 종료를 `model_natural` 압력평형 종료와 혼동하지 않는다.
- 통합 진단 기록: `results/20261014/hazop_multiequipment_provider_isolation_diagnostic_v3.json`
- 전체 실행시간은 약 62.4초였고, 1 Hz 신선 물리계산 성능을 주장하지 않는다.

## 해석 제한

이 결과는 차단 명령과 영(0) 유량 관찰을 외부 모델이 반환하는지 확인한 **진단 증거**다. 현장 ESD 작동시간 분포, 차단 실패확률, 배관 형상·재고의 실측 보정, 독립 실험 검증, 문헌 빈도와의 결합을 제공하지 않는다. 따라서 `qualified_provider_packet`, 빈도 추론, 시설 전체 IR/F-N, 시설 QRA 승격은 계속 닫혀 있다. 고정된 패킷의 차단 시각을 현장 빈도로 해석하거나 센서 신호에서 빈도를 학습하지 않는다.

## 재현 명령

```powershell
python scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --output-dir results/20261014/hazop_isolation_packets/transfer-line-01-AREA_1pct `
  --component-id liquid-transfer-line-01 `
  --port-id line-accident-out `
  --event-id "generic-lh2-full-scope-frequency-example/transfer-line/AREA_1%" `
  --pipe-diameter-m 0.0025 `
  --failure-opening-diameter-m 0.0025 `
  --horizon-s 0.0501 `
  --time-step-s 0.001 `
  --isolation-time-s 0.0001 `
  --post-isolation-observation-s 0.05
```

이 명령의 숫자는 해당 bin의 진단 입력 예시이며, 현장 설비의 차단시간이나 사고빈도를 대신하지 않는다.
