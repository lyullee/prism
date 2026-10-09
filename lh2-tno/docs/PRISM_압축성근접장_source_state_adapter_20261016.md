# PRISM 압축성 근접장 source-state adapter (2026-10-16)

## 이번 보완의 목적

기존 고속 gas packet은 대기 출구에서 `질량유량 ÷ 출구면적`으로 속도를 닫았다. 이 값은 설비 내부의 압력과 목 유동을 보존한 압축성 근접장 해가 아니다. 따라서 고속 값만 보고 underexpanded jet으로 넘기면 실제보다 강한 방출을 만들 수 있다.

이번 보완은 두 경계를 분리한다.

1. 외부 설비 모델이 각 시간 구간의 상류 상태와 throat 상태를 함께 내보낸다.
2. 선택형 adapter가 그 자료를 이용해 대기 평면의 등가 carrier를 만들고, 기존 `prism.compressible_plane_handoff.v1` 계약으로 검증한다.

상류·throat 자료가 없으면 adapter는 중지한다. 대기 packet의 속도나 센서 압력에서 source pressure를 역산하지 않는다.

## 코드와 계약

* `ResolvedGasStep.provider_source_state`는 다음을 보존한다.
  * provider 상류 pressure, temperature, density, enthalpy, entropy
  * provider throat pressure, temperature, density, enthalpy, mass flux, choked 여부
  * source-state provenance
* `src/lh2_tno/compressible_source_adapter.py`는 exact provider result digest, interval clock, mass continuity를 확인한다.
* `scripts/build_compressible_plane_handoff.py`는 외부 `lh2dt` property backend를 사용해 선택형 handoff를 만든다.
* `scripts/attach_compressible_plane_handoff.py`는 component/port/event와 upstream source/result digest를 다시 맞춘다.
* `src/lh2_tno/chain_worker.py`는 선언된 handoff 평면에서만 SLABx-LH2를 시작한다. PRISM이 원래 누출을 회전하거나 팽창시키지 않는다.

기본 adapter는 `birch_momentum_energy`이다. throat의 질량·운동량으로 등가 평면 속도를 정하고 provider property backend에서 정적 enthalpy를 닫는다. 따라서 질량과 에너지 잔차를 기록하며, entropy 보존을 동시에 주장하지 않는다. `birch_momentum_isentropic`는 비교용으로만 제공된다. 두 모드 모두 현재 `synthetic_diagnostic`이며 qualified provider 또는 독립 물리검증으로 승격되지 않는다.

## 재현 예

```powershell
$py = 'output/prism-release-v060-v69n9vf6/venv/Scripts/python.exe'
$lh2dt = 'C:/Users/lyul/Desktop/DocuData/액화수소 저장탱크_밴트 시스템/lh2dt_models'

& $py scripts/export_lh2dt_dynamic_vaporizer_prism_packet.py `
  --lh2dt-root $lh2dt `
  --output-dir results/20261016/dynamic_high_pressure_source_state_smoke `
  --duration-s 0.5 --time-step-s 0.05 `
  --inlet-pressure-pa 1000000 --inlet-temperature-k 300 `
  --opening-diameter-m 0.001 `
  --component-id dynamic-vaporizer-high-pressure-source-state `
  --event-id dynamic-vaporizer-high-pressure-source-state/G1

& $py scripts/build_compressible_plane_handoff.py `
  --packet results/20261016/dynamic_high_pressure_source_state_smoke/resolved_release.json `
  --provider-response results/20261016/dynamic_high_pressure_source_state_smoke/provider_response.json `
  --lh2dt-root $lh2dt `
  --output-handoff results/20261016/dynamic_high_pressure_source_state_smoke/compressible_handoff.json `
  --output-audit results/20261016/dynamic_high_pressure_source_state_smoke/compressible_handoff_audit.json
```

이 smoke는 source pressure 약 1 MPa의 합성 설비 상태에서 handoff 최대 Mach `3.9982`, 에너지 잔차 `0 J/kg`를 기록했다. 이는 알고리즘 연결과 장부 검사를 보인 것이며, 실제 설비 검증이나 사고빈도 근거가 아니다.

## 현재 선택된 G1의 판정

`results/20261014/vaporizer_worklist_g1`의 기존 고속 packet은 source/throat 상태를 포함하지 않는다. 새 adapter는 다음 이유로 중지한다.

```text
COMPRESSIBLE_PLANE_HANDOFF_SOURCE_STATE_BLOCKED
provider data.steps[0] has no provider_source_state;
atmospheric packet velocity cannot be used
```

따라서 이 보완은 문제를 숨기지 않고, 실제 `ambient-vaporizer/G1` provider가 export해야 할 정확한 추가 자료를 정의한다. 해당 자료와 독립 검증이 들어오기 전에는 시설 IR/F-N이나 실제 빈도로 승격하지 않는다.
