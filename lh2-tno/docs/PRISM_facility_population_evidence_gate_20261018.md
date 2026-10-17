# 시설 인구·수용점 근거 게이트

시설 IR/F-N 계산에는 수용점 위치와 각 연간 조건의 인구·재실률이 모두
필요하다. PRISM은 이 값을 센서나 위험도 계산 결과에서 추정하지 않는다.
현재 원장은 수용점 집합과 인구 행이 빠짐없이 연결됐는지 먼저 확인하고, 그
다음에 인구자료의 출처 상태를 별도로 확인한다.

## 출처 상태

각 인구 행은 다음 중 하나의 `source_status`를 가질 수 있다.

- `field_confirmed`: 현장 확인 자료
- `reviewed_design`: 검토된 설계·배치 자료
- `reviewed`: 별도 검토가 완료된 자료
- `synthetic` 또는 `unqualified`: 진단용·미검토 자료

`field_confirmed`, `reviewed_design`, `reviewed` 행은 64자리 SHA-256
`source_digest`도 함께 가져야 한다. 모든 참조 인구 행이 이 조건을 만족할
때만 원장 상태가 `QUALIFIED_REVIEWED_OR_FIELD_CONFIRMED`가 된다. 행 수가
맞는 것만으로는 시설 QRA를 열지 않는다.

## 현재 권위 결과

현재 일반 LH2 예제는 수용점 1개와 인구 행 5개를 구조적으로 가지고 있지만,
모든 행이 합성·미검토이므로 다음 상태를 유지한다.

```text
population_source_qualification_status = UNQUALIFIED_SYNTHETIC_OR_UNVERIFIED
population_source_digest_count = 0
population_source_unqualified_row_count = 5
facility_qra = FACILITY_QRA_WITHHELD
```

이는 인구가 없다는 뜻이 아니라, 실제 시설의 검토된 인구·재실 근거가 아직
제출되지 않았다는 뜻이다. 조건부 진단 IR/F-N은 계속 계산할 수 있지만 시설
전체 QRA로 승격하지 않는다.

## 연결 위치

- `src/lh2_tno/facility_ledger.py`가 수용점 일치, 인구 행, 출처 상태와 digest를
  원장에 기록한다.
- `src/lh2_tno/facility_qra_gate.py`가 검토설계·현장확인 출처가 없는 경우
  시설 범위 게이트를 닫는다.
- `tests/test_facility_ledger.py`와 `tests/test_facility_qra_gate.py`가 합성
  자료 차단과 field-confirmed 자료 허용 경계를 회귀검사한다.

향후 실제 자료를 연결할 때는 각 수용점의 좌표, 연간 조건별 인구 수,
재실률, 출처 상태, 원자료 digest를 함께 제출해야 한다. 누락된 수용점이나
0명 인구도 행을 생략하지 않고 명시해야 한다.
