# native `DynamicVaporizer`·`DynamicReliquefier` 방출 연결 기록

`scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py`는 외부 유한체적 모델의 `export_accident_history(request)`를 직접 호출한다. 두 모드는 같은 보존식 상태를 사용하지만 열경계가 다르다.

```powershell
python scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --mode vaporizer `
  --output-dir results/20261025/native_dynamic_vaporizer

python scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --mode reliquefier `
  --output-dir results/20261025/native_dynamic_reliquefier
```

native finite-volume 질량, 최종 질량, 종료 basis와 방출량을 원본 응답에 보존하고, PRISM은 strict gas release의 시간·질량·엔탈피·대기면을 검사한다. 기본 horizon은 잔류 재고가 있으므로 `synthetic_diagnostic_horizon`이다.

현재 외부 helper의 `provider_source_state`는 개방도·choked·source 상태와 throat pressure 일부만 제공하며 PRISM의 완전한 throat 온도·밀도·엔탈피·엔트로피 기록을 아직 충족하지 않는다. 원본 trace는 `provider_response.json`에 유지하고 strict packet의 선택 필드에서는 제거한다. 고속 방출에는 별도 provider 압축성 plane handoff가 필요하며 PRISM이 source pressure에서 임의로 근접장을 만들지 않는다.

따라서 이 연결은 **기화기·재액화기 상태→native 방출→strict gas packet→피해 계산**의 코드 경계를 확인하는 합성 진단이다. 현장 빈도, 차단 신뢰도, 독립 물리검증, 시설 IR/F-N으로 승격하지 않는다.
