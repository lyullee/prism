# PRISM PRESLHY Trial 10 좌표 방향 증거 기록 (2026-11-03)

## 확인 결과

외부 실증자료의 현재 비교에서 방출 방향을 임의로 정하지 않도록 1차 보고서를 다시 확인했다. PRESLHY E3.5 보고서의 표 A11은 **Trial 10**이 **Test 3.5.10**을 사용했다고 기록한다. 표 A10에서 Test 3.5.10은 수평 방출, 높이 0.5 m, 구경 25.4 mm, 압력 5 bar이다. 같은 보고서의 표 A5 주석은 시험 장치의 방출 방향이 **북쪽 기준 약 75°**라고 기록한다.

- 1차 자료: [PRESLHY D3.6 E3.5 Rainout 보고서](https://hysafe.info/wp-content/uploads/sites/3/2020/08/PRESLHY_D3.6_Summary_of_Rainout_Experiments_V1.20.pdf)
- 공개 데이터셋 식별자: `10.35097/1481`
- 기계 판독 기록: `results/20261103/external_field_model_comparison/preslhy_trial10_documentary_coordinate_evidence.json`

## 현재 모델과의 관계

기존 PRISM Trial 10 재현 결과는 `source_release_bearing_deg=286°`로 실행되어 있다. 이번 확인으로 286°를 사실값으로 유지하지 않고, 보고서 선언값 75°와 구분해야 한다는 것이 명확해졌다. 따라서 기존 결과를 수정해 검증 결과처럼 보이게 하지 않고, 다음 두 값을 별도로 보존한다.

| 구분 | 값 | 의미 |
|---|---:|---|
| 문헌 선언 방향 | 약 75° | 시험 장치/방출 방향의 1차 자료 기록 |
| 기존 재현 방향 | 286° | 이전 진단 실행에 실제 사용된 값 |

보고서 표 A5에는 방출점에서 180°에 있는 Local PCE가 북쪽 기준 255°에 있다고 적혀 있다. 이는 방출 방향 75°와 정반대인 방향이므로, 75°를 북쪽 기준의 signed bearing으로 해석할 근거가 된다. 반면 source-relative 축을 반사해 ENU로 바꾸는 경우에는 75°의 진단 후보가 약 285°가 될 수 있다. `285°`와 기존 `286°`는 이 축 반사·기존 실행을 확인하기 위한 후보일 뿐, 문헌값을 fitting한 결과가 아니다.

## 아직 닫히지 않은 부분

보고서는 방출 장치의 북쪽 기준 방향을 알려주지만, 파생된 `source-relative metres` 자료의 x·y 축이 동·북 방향에 어떻게 매핑되는지는 제공하지 않는다. 그러므로 75°를 곧바로 수신기 좌표 변환으로 사용하면 안 된다. 방출 방향과 수신기 좌표축 변환은 서로 다른 정보다.

현재 상태는 다음과 같다.

- 문헌 방향 증거: 확보 (`75°`, 정반대 풍향계 위치 `255°`와 일관)
- source-relative x/y → ENU 변환: 미확정
- 현재 비교의 hash drift: 남아 있음
- 독립 물리검증: 차단
- 시설 IR/F-N 승격: 차단

## 다음 실행 순서

1. 원자료 또는 실험 배치도에서 source-relative x/y의 북쪽 기준 방위와 축 방향을 확보한다.
2. PRISM orientation diagnostic을 문헌 방향 75°와 확인된 축 변환으로 재실행한다.
3. source, weather, common-clock 파일의 hash를 원자료 버전과 다시 맞춘다.
4. 공급자 사고방출 packet과 독립 검토가 충족될 때만 물리검증 gate를 재평가한다.

이번 기록은 방향을 맞춰 보기 위한 근거이며, 매개변수 fitting이나 물리검증 승인이 아니다.
