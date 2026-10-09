# PRISM 확장 사건 상태 snapshot coverage 기록

## 목적

기본 native LH2 24개 사건은 `prism.equipment_state_snapshot.v1` payload와 provider echo digest를 요청·결과에 함께 보존한다. 통합 원장에 추가한 vertical handoff 5개와 inventory depletion 5개도 같은 기준을 만족해야 시설 전체 상태 연결로 볼 수 있다.

## 이번 보완

`src/lh2_tno/extension_state_snapshot_coverage.py`와 `scripts/run_native_full_scope_union_assessment.py`가 확장 사건을 event별로 감사한다. 결과 파일은 `results/20261026/native_full_scope_union_assessment/extension_state_snapshot_coverage.json`이다.

현재 결과:

- 확장 사건: 10개
- canonical state snapshot이 provider echo까지 확인된 사건: 0개
- 상태 snapshot이 없는 사건: 10개
- vertical handoff: 5개는 provider packet identity와 source/result digest가 있으나 canonical 상태 payload가 없다.
- inventory depletion: 5개는 provider packet identity 자체도 없어 상태 handoff를 확인할 수 없다.

방출 경계의 유량·압력·온도·질량, provider result digest, 또는 종료시간은 사고 방출 계산의 근거이지 설비 정상 상태 snapshot이 아니다. 이 값을 이용해 snapshot을 재구성하면 설비 상태→방출 연결이 검증된 것처럼 보일 수 있으므로 모듈은 이를 허용하지 않는다.

## 재현

통합 실행은 `--state-snapshot-binding-audit`를 기본 native 장부에 사용하고, 선택적으로 `--extension-state-snapshot-audit`에 확장 provider의 canonical 상태 장부를 넣는다. 후자가 없으면 결과는 자동으로 `EXTENSION_STATE_SNAPSHOT_COVERAGE_INCOMPLETE`가 된다. `build_ijhe_objective_coverage_audit.py --extension-state-snapshot-coverage`는 이 결과를 strict facility state gate에 반영한다.

## 다음 입력 계약

각 확장 event ID에 대해 provider가 다음을 보내야 한다.

1. 검증된 `prism.equipment_state_snapshot.v1` payload
2. payload digest와 provider echo digest
3. provider source/result digest와 component ID
4. snapshot 시각·신선도·정상 공정 상태와 사고 방출 이력의 분리 근거

이 자료가 들어오면 같은 event ID의 audit row가 `BOUND_AND_ECHOED`가 되는지 확인하고, 그때만 시설 전체 state coverage strict gate를 재실행한다. 현재 장부는 실패가 아니라 자료 부재를 명시한 진단 결과이며, 시설 QRA 승격이나 독립 물리검증을 주장하지 않는다.
