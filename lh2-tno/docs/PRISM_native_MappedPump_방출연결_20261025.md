# native `MappedPump` 방출 연결 기록

`scripts/export_lh2dt_native_mapped_pump_prism_packet.py`는 외부 `lh2dt.MappedPump.export_accident_history(request)`를 직접 호출한다. 펌프의 H-Q-N 운전점은 native 응답의 `provider_meta.pump_operating_point`로 보존하고, 액체·기체 flash와 지상 액체 분할은 native steps 그대로 PRISM `ResolvedLiquidRelease`로 넘긴다.

```powershell
python scripts/export_lh2dt_native_mapped_pump_prism_packet.py `
  --lh2dt-root "<lh2dt_models 루트>" `
  --output-dir results/20261025/native_mapped_pump

python scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261025/native_mapped_pump/resolved_release.json `
  --output-dir results/20261025/native_mapped_pump/chain
```

상류 재고는 펌프가 아니라 호출자가 `available_mass_kg`로 선언한다. 종료도 기본적으로 `synthetic_diagnostic_horizon`이며, pump seal 고장확률·차단 신뢰도·현장 빈도는 계산하지 않는다. airborne liquid은 현재 native provider 계약대로 0이다.

이 결과가 `END_TO_END_DIAGNOSTIC_EXECUTED`가 되어도 합성 액체 상태·H-Q-N map·대기 개구·수용기·기상 조건에서의 연결 회귀일 뿐, qualified provider packet·독립 물리검증·시설 IR/F-N은 아니다.
