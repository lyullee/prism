# PRISM native source/throat 상태 완결성 감사

작성일: 2026-10-25  
대상: native `lh2dt` 7개 사고 export와 선택형 `prism.compressible_plane_handoff.v1` 경계

## 목적

7개 native 설비의 사고 export가 실행된 것과, 고속 기체 사건을 압축성 근접장 handoff로 넘길 수 있는 것은 다른 조건이다. `scripts/audit_native_source_state_completeness.py`는 원본 `provider_response.json`을 읽고 source/throat 상태가 실제로 어떤 필드까지 있는지 감사한다. 누락된 값을 계산하거나 추정하지 않는다.

선택형 압축성 source-state adapter가 요구하는 핵심 필드는 다음 네 가지다.

* `source_specific_entropy_j_kgk`
* `throat_pressure_pa_abs`
* `throat_density_kg_m3`
* `throat_specific_enthalpy_j_kg`

## 현재 판정

| 구분 | 설비 | 판정 |
|---|---|---|
| 기체 | StrokeLimitedCommandedValve | source 상태는 있으나 entropy·throat 상태가 없어 차단 |
| 기체 | DynamicVaporizer | source와 throat 압력/질량 flux 일부만 있어 차단 |
| 기체 | DynamicReliquefier | source와 throat 압력/질량 flux 일부만 있어 차단 |
| 기체 | VentStack | source 상태는 있으나 entropy·throat 상태가 없어 차단 |
| 액체·2상 | LayeredTank, DynamicHEMPipe | 현재 기체 adapter 대상 아님; 별도 2상 근접장 계약 필요 |
| 액체 | MappedPump | 현재 기체 adapter 대상 아님; 액체/지면 액체 handoff 검증 필요 |

따라서 이번 감사의 결과는 **기체 4개 중 압축성 adapter 완결 0개, 차단 4개**다. 이는 native export가 실패했다는 뜻이 아니라, 고속 출구에서 PRISM이 source pressure를 역산하거나 대기 출구 속도를 근접장 속도로 재사용하지 않도록 하는 보수적 경계다.

재생 명령:

```powershell
python scripts/audit_native_source_state_completeness.py `
  --output examples/native_source_state_completeness_v1.json
```

이 장부는 현장 빈도, provider 자격, 독립 물리검증, 시설 IR/F-N을 추가하지 않는다. 다음 구현 자료는 각 기체 provider가 동일한 시간 간격으로 source entropy와 throat pressure·temperature·density·enthalpy·mass flux를 내보내고, 액체·2상 provider가 별도 검증된 근접장 계약을 제공하는 것이다.
