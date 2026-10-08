# PRISM LayeredTank 경계 감사 개발 기록 (2026-10-09)

## 목적

액화수소 설비 디지털 트윈의 `LayeredTankNetworkSimulator` 결과를 PRISM의
`ResolvedLiquidRelease` 입력으로 연결할 수 있는지 확인했다. 이 작업은 외부
설비 프로젝트를 PRISM 패키지 안에 복사하거나 런타임 의존성으로 만들지 않고,
공급자가 내보낸 결과의 의미와 누락 항목을 기계적으로 점검하는 경계 어댑터를
추가하는 방식으로 수행했다.

구현 파일은 다음과 같다.

- `src/lh2_tno/layered_network_boundary.py`
- `scripts/audit_layered_tank_boundary.py`
- `tests/test_equipment_boundary.py`의 2개 계약 시험

## 확인한 공급자 결과

외부 프로젝트의 `examples/run_layered_network_fill_vent.py`를 새로 실행해
`LayeredTankNetworkSimulator`의 5개 시간 결과를 저장했다.

- 공급자 모델: `LayeredTank`, 액체 2개 셀·증기 2개 셀의 층상 탱크
- 연결 포트: `vapor_port` → `vent_sink`
- 포트 상태: 명시적인 `TANK:V1` → `VENT:IN`
- 탱크 장부: 누적 경계 질량·에너지와 시간별 링크 질량유량 보존
- 공급자 수요 경계 압력: 100,000 Pa
- PRISM 대기 기준압력: 101,325 Pa
- 최대 관측 유량: 약 `3.8214e-08 kg/s`
- 탱크 누적 경계 질량: `5.29715e-08 kg`

기계 판독 원본은 `results/20261009/layered_tank_boundary/provider_export.json`이고,
감사 결과는 같은 디렉터리의 `layered_tank_boundary_audit.json`이다.

추가로 액체 셀 포트 `liquid_port`를 101,325 Pa 경계에 직접 연결하는 최소
probe도 실행했다. 이 경우 대기 경계 판정은 `true`이고 최대 outward 유량은
`1.33954e-03 kg/s`였지만, 공급자 결과에는 여전히 플래시 가스·지상 액체·비산
액체 분할, 출구 형상, 종료 계약이 없어서 `ready_for_resolved_liquid_release`
는 `false`다. 원본은
`results/20261009/layered_tank_boundary/liquid_atmospheric_probe_export.json`,
판정은 `liquid_atmospheric_probe_audit.json`에 저장했다.

## 판정

이번 결과는 **탱크·포트·네트워크 계산이 실행되었다**는 증거다. 그러나 PRISM의
대기 액체/2상 방출 사건으로 승격하지 않았다.

승격이 보류된 이유는 다음 네 가지다.

1. 목적지가 대기압 경계가 아니라 100 kPa 수요 경계다.
2. 플래시 가스, 지상 액체, 비산 액체의 질량 분할이 없다.
3. 대기 출구 위치·방향·유효 면적이 없다.
4. 방출 종료 조건을 PRISM 사건 장부로 선언하지 않았다.

따라서 현재 어댑터는 질량유량·엔탈피·노드 압력·상태·탱크 누적 장부만
추출한다. 누락된 항목을 임의의 누출량이나 액적 분율로 채우지 않는다. 이
실패 폐쇄 판정은 `ResolvedLiquidRelease`가 요구하는 provider-owned flash 및
droplet 경계를 지키기 위한 것이다.

## 실행 방법

```powershell
python scripts/audit_layered_tank_boundary.py `
  results/20261009/layered_tank_boundary/provider_export.json
```

출력의 `ready_for_resolved_liquid_release`가 `false`이면 시설 피해 계산에
연결할 수 없다. 공급자 쪽에서 대기 출구와 플래시/액적 분할을 추가한 뒤,
동일한 어댑터 입력에 그 근거와 종료 장부를 명시해야 `true`가 될 수 있다.

## 다음 연결 작업

1. 실제 사고 포트(탱크 액체·증기, 배관 양단, PSV/벤트)의 위치와 방향을
   공급자 포트 목록으로 확정한다.
2. 액체 포트에서 대기로 나가는 경우에 대해 공급자가 플래시 가스, 지상
   액체, 비산 액체, 액적 도착 위치와 출구 면적을 같은 시간축으로 내보낸다.
3. 차단 명령과 재고 소진을 포함한 종료 이벤트를 provider result에 기록한다.
4. 그 결과를 `ResolvedLiquidRelease`로 검증한 후에만 SLABx-LH2,
   DynamicLH2PoolX, 점화, IR/F-N 경로에 연결한다.

이번 기록은 LayeredTank 액체·2상 재고 피드백이 완성되었다는 뜻이 아니다.
대기압 액체 포트까지는 연결 가능하지만, 피해 체인에 넣을 provider-owned
flash/액적/종료 경계가 없으면 승격하지 않는다는 것을 확인한 경계 시험이다.
