# native `StrokeLimitedCommandedValve` 방출 연결 기록

## 무엇을 연결했나

`scripts/export_lh2dt_native_valve_prism_packet.py`는 PRISM 안에서 밸브 유량을 다시 계산하는 wrapper가 아니다. 외부 `lh2dt_models`의
`lh2dt.valve.StrokeLimitedCommandedValve.export_accident_history(request)`를 직접 호출하고, 그 결과를 PRISM의
`prism.resolved_release.v1` gas packet으로 검증한다.

연결 순서는 다음과 같다.

1. 외부 native 밸브가 지정된 압력·온도·개구·방출계수·stroke time으로 출구 이력을 계산한다.
2. PRISM은 event/component/port identity, 시간 간격, 질량·엔탈피 적분, 대기 출구 면적·속도를 다시 검사한다.
3. strict packet은 기존 `validate_lh2dt_prism_packet_chain.py`로 SLABx/SLABx-LH2, 점화, 화재·폭발, TNO 피해까지 전달할 수 있다.

밸브는 상류 재고를 소유하지 않으므로 `available_mass_kg`와 종료 근거를 호출자가 제공한다. 따라서 이번 기본 케이스의 종료는 차단 성공이 아니라 `synthetic_diagnostic_horizon`이다.

## 재현 명령

외부 모델 루트를 지정해 native packet을 만든다.

```powershell
python scripts/export_lh2dt_native_valve_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --output-dir results/20261025/native_stroke_valve
```

기본 합성 입력은 500 kPa, 300 K, 2.5 mm 개구, 0.1 s 진단시계다. 이 조건은 대기 출구 속도가 높아 현재 PRISM의 저마하 직접 대기면 범위를 넘을 수 있다. 그 경우 packet을 억지로 피해 계산으로 통과시키지 않고, 별도 provider 압축성 plane handoff가 필요하다는 이유로 미계산으로 남긴다.

저마하 경계의 구조 연결만 확인하는 near-ambient 진단은 다음과 같이 실행한다.

```powershell
python scripts/export_lh2dt_native_valve_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --output-dir results/20261025/native_stroke_valve_low_mach `
  --source-pressure-pa-abs 101500 `
  --available-mass-kg 1.0

python scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261025/native_stroke_valve_low_mach/resolved_release.json `
  --output-dir results/20261025/native_stroke_valve_low_mach/chain
```

현재 재현 결과는 `chain/verification.json`의 `END_TO_END_DIAGNOSTIC_EXECUTED`이다. 이는 합성 설비·수용기·기상·점화 조건에서의 구조 연결 확인이며, 실제 밸브 고장빈도나 시설 IR/F-N이 아니다.

## source/throat 상태 보완

외부 `lh2dt`의 `ValveResult`는 이미 throat 압력과 질량플럭스를 계산하고 있었지만, 사고 export가 이를 버리고 있었다. 외부 helper를 보완해 native upstream entropy와 throat 압력·온도·밀도·엔탈피·질량플럭스를 `provider_source_state`로 보존했다. PRISM 어댑터는 이 값을 다시 계산하지 않고 strict packet에 전달하며, native actuator의 `opening`처럼 PRISM 계약에 없는 보조 필드만 strict handoff에서 제거한다. 따라서 현재 감사는 기체 4개 중 밸브·기화기·재액화기 3개의 source/throat 상태를 완결로 판정하고, VentStack 1개는 throat 해가 없는 Darcy 모델이라 계속 차단한다.

상태가 완전해졌다는 것은 provider가 근접장 팽창·혼합을 계산했다는 뜻이 아니다. 고속 기본 케이스는 여전히 `build_compressible_plane_handoff.py`가 요구하는 provider-resolved downstream plane을 별도로 가져야 한다.

- source/throat 상태는 압축성 source-state adapter의 입력을 충족하지만, 이것만으로 고속 근접장 plane을 자동 생성하지 않는다. provider-resolved downstream plane과 독립 검증이 별도로 필요하다.
- 밸브 자체에는 상류 재고, 차단 신뢰도, 현장 고장빈도가 없다. 남은 재고는 upstream reserve로 기록되며 빈도는 결합하지 않는다.
- 이번 실행은 `synthetic_diagnostic`이고 `provider_packet_promoted=false`, `physical_validation_claim=false`, `facility_qra_claim=false`다.

따라서 이 작업은 **밸브 설비 경계의 native 방출 계산과 PRISM 피해 경로를 연결한 것**이다. 일반 액화수소시설 전체의 qualified 방출 자료, 빈도, 독립 물리검증, IR/F-N 완료를 의미하지 않는다.
