# PRISM native source/throat 상태 완결성 감사

작성일: 2026-10-26
대상: native `lh2dt` 7개 사고 export와 선택형 `prism.compressible_plane_handoff.v1` 경계

## 목적

7개 native 설비의 사고 export가 실행된 것과, 고속 기체 사건을 압축성 근접장 handoff로 넘길 수 있는 것은 다른 조건이다. `scripts/audit_native_source_state_completeness.py`는 원본 `provider_response.json`을 읽고 source/throat 상태가 실제로 어떤 필드까지 있는지 감사한다. 같은 클래스의 액체·2상과 기체 상태는 서로 다른 시나리오 행으로 기록하며 누락된 값을 계산하거나 추정하지 않는다.

선택형 압축성 source-state adapter가 요구하는 핵심 필드는 다음 네 가지다.

* `source_specific_entropy_j_kgk`
* `throat_pressure_pa_abs`
* `throat_density_kg_m3`
* `throat_specific_enthalpy_j_kg`

## 현재 판정

원본 native class는 7개지만, `DynamicHEMPipe`는 액체·2상과 기체 상태가 서로 다른 export 계약이므로 감사 장부에는 **8개 상태 시나리오 행**으로 기록한다.

| 구분 | 설비 | 판정 |
|---|---|---|
| 기체 | StrokeLimitedCommandedValve | native entropy·throat 상태 제공으로 완결 |
| 기체 | DynamicHEMPipe (gas branch) | native upstream entropy와 hydraulic throat 상태 제공으로 완결 |
| 기체 | DynamicVaporizer | 동일 provider 물성 backend로 entropy·throat 상태를 완성 |
| 기체 | DynamicReliquefier | 동일 provider 물성 backend로 entropy·throat 상태를 완성 |
| 기체 | VentStack | source 상태는 있으나 entropy·throat 상태가 없어 차단 |
| 액체·2상 | LayeredTank, DynamicHEMPipe (liquid/two-phase branch) | 현재 기체 adapter 대상 아님; 별도 2상 근접장 계약 필요 |
| 액체 | MappedPump | 현재 기체 adapter 대상 아님; 액체/지면 액체 handoff 검증 필요 |

따라서 이번 감사의 결과는 **기체 분기 5개 중 압축성 adapter source-state 완결 4개, 차단 1개**다. DynamicHEMPipe gas branch는 native `ValveResult`의 throat 압력·질량플럭스와 pipe upstream entropy로 throat 온도·밀도·엔탈피를 계산해 provider response에 보존한다. DynamicVaporizer와 DynamicReliquefier는 native source pressure/temperature/throat pressure를 바탕으로 동일 provider 물성 backend가 entropy와 throat 온도·밀도·엔탈피를 결정적으로 채웠고, StrokeLimitedCommandedValve는 native `ValveResult`가 계산한 throat 압력·질량플럭스와 provider entropy를 사고 export에 보존한다. 이는 근접장 제트 해나 독립 검증이 아니므로 별도 compressible-plane handoff와 qualified evidence는 여전히 필요하다. VentStack은 Darcy 모델 결과에 throat pressure가 없어 차단된다.

재생 명령:

```powershell
python scripts/audit_native_source_state_completeness.py `
  --output examples/native_source_state_completeness_v1.json
```

이 장부는 현장 빈도, provider 자격, 독립 물리검증, 시설 IR/F-N을 추가하지 않는다. 다음 구현 자료는 VentStack의 throat 경계 또는 별도 Darcy→근접장 검증과, 액체·2상 provider의 별도 검증된 근접장 계약을 제공하는 것이다.
