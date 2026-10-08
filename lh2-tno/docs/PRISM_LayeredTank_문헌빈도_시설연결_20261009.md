# PRISM LayeredTank 문헌 빈도·시설 연결 기록

## 목적

이 기록은 외부 `lh2dt.LayeredTankNetworkSimulator`의 액체 방출 이력을 SLABx-LH2로 분할한 뒤, PRISM의 검토된 액화수소 문헌 빈도와 시설 기상·인구·점화·피해 계산에 연결한 진단을 보존한다. 저장탱크·격리밸브·이송배관의 문헌 LOC를 모두 생성하고, provider 이력이 없는 LOC는 미계산으로 보존한다.

이번 연결은 실제 검사센터의 설비 태그를 고정하지 않는다. `consequence_facility.json`의 옥외 합성 시설을 사용하고, 실제 현장 설비 전체 QRA나 현장 빈도 검증으로 승격하지 않는다.

## 빈도를 붙이는 규칙

문헌 빈도는 방출량이 비슷하다는 이유로 붙이지 않는다. 다음 세 값이 모두 일치해야 한다.

1. provider가 선언한 `failure_opening_diameter_m`
2. `LH2_VESSEL` frequency catalogue의 면적 bin이 계산한 개구
3. `ResolvedLiquidRelease`의 `event_kind=accidental_leak`와 `upstream_service=LH2`

이번 진단은 provider 면적 `7.853981633974483e-7 m²`를 사용했다. `SLABx-LH2`가 반환한 provider 개구는 `0.001 m`이고, 기준 유동 직경 `0.1 m`의 `AREA_0.01%` bin이 계산하는 개구와 일치한다. 따라서 이 한 사건의 기본 빈도 `6.5e-4 year^-1`만 연결했다.

`AREA_0.1%`, `AREA_1%`, `AREA_10%`, `AREA_100%`는 다른 저장탱크 개구를 가지므로 별도 provider 이력 없이 보간하거나 같은 이력을 재사용하지 않았다. 격리밸브와 이송배관의 문헌 LOC도 provider 이력이 없으므로 같은 저장탱크 이력을 재사용하지 않았다. 모든 미계산 조합은 두 기상 조건별로 기록했다.

## 실행

먼저 외부 모델 경로를 사용해 문헌 bin과 맞는 provider 출구를 만든다.

```powershell
python lh2-tno/scripts/validate_layered_tank_inventory_slabsx.py `
  --lh2dt-root <lh2dt-root> `
  --slabx-root <slabx-root> `
  --full-open-area-m2 7.853981633974483e-7 `
  --output-dir lh2-tno/results/20261009/layered_tank_frequency_campaign/provider
```

그 다음 빈도와 시설 campaign을 실행한다.

```powershell
python lh2-tno/scripts/validate_layered_tank_frequency_campaign.py `
  --provider-dir lh2-tno/results/20261009/layered_tank_frequency_campaign/provider `
  --allow-pin-refresh `
  --distribution-draws 250
```

`--allow-pin-refresh`는 현재 소스 트리의 외부 backend digest가 기존 설정과 다를 때만 사용한다. 갱신된 digest는 `backend_config.json`과 `verification.json`에 보존한다.

## 결과

실행 결과는 `results/20261009/layered_tank_frequency_campaign/`에 저장된다.

| 항목 | 결과 |
|---|---:|
| 생성 문헌 LOC | 15개 (저장탱크·격리밸브·이송배관) |
| 정확 개구 일치 LOC | 1개 (`AREA_0.01%`) |
| 기상 조건 | 2개 |
| 물리 체인 실행 | 2건 |
| operator-limited | 2건 |
| 미계산 case ledger | 30건 |
| 전체 시설 IR/F-N | 보류 |
| campaign 처리시간 | 약 4.57 s |

물리 체인은 provider 상태와 종료시계, `ResolvedLiquidRelease`, SLABx 분할, PRISM 확산·점화·피해 계산까지 실행했다. provider와 SLABx의 역할은 `equipment_twin`과 `SLABx-LH2`로 분리해 결과에 기록했다. 현재 방출량과 receptor 거리가 작아 합성 receptor의 피해 기여가 0으로 나올 수 있으며, 이를 안전 판정이나 물리 검증으로 해석하지 않는다.

## 빈도 불확실성

`frequency_uncertainty.json`은 실행된 위험 원자를 다시 물리 계산하지 않고 문헌 빈도만 바꾼다. 저장탱크·격리밸브·이송배관 세 자산의 p05/중앙/p95 시나리오를 만들며, 실제 위험 원자가 있는 저장탱크 bin만 known contribution에 기여한다.

- 공유 자산 p05: `3.7383e-05 year^-1`
- 문헌 중앙값: `6.5e-04 year^-1`
- 공유 자산 p95: `1.13028e-02 year^-1`
- 독립 event-bound p95: 15개 생성 event에 대해 계산하되, 미계산 event의 피해 원자는 만들지 않음

`frequency_distribution.json`은 공개된 `mu/sigma`를 사용한 250회 빈도 표본이다. 이 결과는 물리·통계 신뢰구간이 아니라 문헌 빈도 모델의 known-contribution 민감도다. 시설 전체 credible interval이 아니다.

## 남은 범위

- 실제 탱크·배관·밸브·펌프·PSV 포트별 provider 이력 연결
- 실제 설비 재고와 차단 지연·실패 확률
- 다른 네 문헌 개구 bin에 대한 별도 LayeredTank/SLABx 이력
- 액적 비산(airborne liquid) adapter와 flash/분무 에너지 독립 검증
- 현장 기상·인구·장벽 자료를 사용한 전체 시설 IR/F-N
- 실제 실험 및 실증 데이터에 의한 물리 보정

따라서 이번 기록의 상태는 `PARTIAL_DECLARED_SCOPE_OPERATOR_LIMITED`이다. 빈도를 붙였다는 사실만으로 전체 시설 위험도가 완성된 것으로 표시하지 않는다.
