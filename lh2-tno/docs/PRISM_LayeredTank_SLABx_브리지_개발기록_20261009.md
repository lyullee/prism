# PRISM LayeredTank–SLABx-LH2 경계 브리지 개발 기록

기준일: 2026-10-09  
상태: `END_TO_END_DIAGNOSTIC_EXECUTED`  
범위: 합성 LayeredTank 액체 포트 probe 1건, 옥외 피해 체인 1건

## 이번 개발의 목적

LayeredTank 디지털트윈은 탱크 안의 상태와 밸브를 계산합니다. SLABx-LH2는 탱크 밖으로 나온 극저온 수소가 기체와 액체로 어떻게 나뉘는지 계산합니다. PRISM은 그 다음 단계인 풀, 확산, 점화, 복사열·폭발, 사람 피해를 계산합니다.

이번 브리지는 세 계산을 한 사건의 시간표와 질량 장부로 연결합니다.

```text
LayeredTank 상태·밸브
  → 설비가 계산한 전체 질량유량(최종 질량 장부)
  → SLABx-LH2 flash·액적/지면 분할
  → ResolvedLiquidRelease 계약
  → PRISM 풀·확산·점화·피해
```

## 책임을 나눈 이유

두 모델이 같은 유량을 각각 계산해 합치면 질량이 두 번 계산되거나 서로 다른 사건이 될 수 있습니다. 그래서 다음 규칙을 코드로 고정했습니다.

| 값 | 최종 책임 | 처리 |
|---|---|---|
| 시간 간격과 설비 전체 질량유량 | LayeredTank provider | PRISM의 질량 장부로 그대로 사용 |
| flash된 기체, 지면 액체, 액적 도착 시각 | SLABx-LH2 | 설비 유량에 맞춰 비율만 조정 |
| 대기 기체 경계의 면적·속도 | SLABx-LH2 | 기체 유량을 보존하도록 면적을 다시 계산 |
| 질량·엔탈피 폐합 | PRISM 계약 | 실패하면 `ResolvedLiquidRelease`를 만들지 않음 |

설비 유량과 SLABx 총유량의 상대 오차가 기본 5%를 넘으면 브리지는 중단합니다. 이번 probe의 첫 구간은 설비 `0.001339542388 kg/s`, SLABx `0.001372400106 kg/s`로 상대 오차 `2.4529%`였으므로 통과했습니다.

## 시간 의미

LayeredTank provider 결과는 한 계산 간격을 진행한 뒤의 끝 상태로 반환됩니다. export는 이 의미를 다음 문자열로 선언합니다.

`provider_result_end_state_representative_for_preceding_fixed_step`

예를 들어 `time_s=0.1`인 결과는 `0.0–0.1 s` 구간의 대표값으로 바꾸어 PRISM에 전달합니다. 이 선언이 없거나 간격이 양수가 아니면 브리지는 거절합니다.

## 실제 실행 결과

입력은 외부 LayeredTank의 액체 포트와 대기압 sink를 연결한 합성 probe입니다.

- 시간 간격: `0.1 s`
- 총 시간: `0.2 s`
- 밸브 full-open area: `1.0e-6 m²`
- 방출계수: `0.8`
- 출구 높이: `1.0 m`
- 방향: ENU `[1, 0, -1]`
- 첫 구간 설비 유량: `0.001339542388 kg/s`
- 첫 구간 SLABx 유량: `0.001372400106 kg/s`
- 브리지 상대 오차: `0.024529 < 0.05`
- 설비가 제공한 총 방출 질량: `0.000133954239 kg`
- PRISM 최종 질량 잔차: `0 kg`
- airborne liquid: `0 kg/s`
- 전체 체인 실행 시간: 약 `2.224 s` (현재 PC, 합성 0.2초 사건)

최종 장부에서는 이번 조건의 기체가 전량 직접 기체로 들어갔고, 지면 풀 유입은 0이었습니다. 이것은 해당 probe의 SLABx 결과이며 모든 액화수소 설비의 일반적인 결과를 뜻하지 않습니다.

## 재현 명령

저장소 루트에서 외부 SLABx 소스 경로를 지정해 실행합니다.

```powershell
.\output\prism-release-v060-v69n9vf6\venv\Scripts\python.exe `
  lh2-tno\scripts\validate_layered_tank_slabsx_bridge.py `
  lh2-tno\results\20261009\layered_tank_boundary\liquid_atmospheric_probe_export.json `
  --slabx-root C:\Users\lyul\Desktop\DocuData\SLABx_LH2\slabx-lh2 `
  --execute-chain
```

산출물은 `results/20261009/equipment_layered_tank_slabsx/`에 저장합니다.

- `provider_export.json`: LayeredTank 원자료와 시간·형상 선언
- `slabx_partition.json`: 구간별 SLABx 계산과 액적 결과
- `combined_liquid_rows.json`: 유량 gate와 scaling 감사표
- `resolved_liquid_release.json`: PRISM 입력 계약
- `facility.json`, `request.json`, `result.json`: 전체 피해 체인 입력과 결과
- `verification.json`: 상태, 오차, 질량 장부, 단계별 처리시간

## 현재 의미와 한계

이번 결과는 LayeredTank 출력이 PRISM 계약으로 변환되고 최종 피해 계산까지 이어진다는 **연결 검증**입니다. 실제 탱크 설계값, 실제 밸브 계수, 실제 대기 출구, 현장 재고 소진, flash/분무 에너지 검증, airborne droplet adapter, 현장 차단 신뢰도, 사고 빈도와는 별개입니다.

기존 `audit_layered_tank_boundary.py`의 일반 fill/vent 경로는 여전히 100 kPa 수요 경계이며, 대기 출구 분할이 없어 자동 승격하지 않습니다. 이번 브리지는 대기압 액체 probe에 대해 SLABx를 명시적으로 호출한 별도 경로입니다. 따라서 “LayeredTank 모델 전체가 완성됐다”거나 “시설 전체 연간 IR/F-N이 완성됐다”고 해석하지 않습니다.

## 다음 개발 항목

1. 실제 설비 포트별 full-open area, Cd, 높이·방향, 대기 경계를 export에 포함합니다.
2. LayeredTank 액체/2상 재고를 매 간격 feedback하여 방출 종료를 실제 tank depletion과 연결합니다.
3. SLABx flash·분무 에너지와 액적 비산/증발을 실증 데이터로 검증합니다.
4. 동일 브리지를 탱크·배관·밸브·펌프·PSV/벤트의 설비 ID별로 반복하고, 각 사건의 문헌 빈도와 연결합니다.
5. 새 설비 입력에서 처리시간과 수렴을 반복 측정한 뒤 IJHE용 검증표를 작성합니다.

