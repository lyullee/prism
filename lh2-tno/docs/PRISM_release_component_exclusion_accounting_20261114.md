# 방출 설비 예상 목록과 명시적 인터페이스 제외 회계

이번 보완은 위험 계산식을 바꾼 것이 아니라, 시설 매니페스트와 빈도 계획의 경계를 실행기가 정확히 읽도록 만든 수정이다.

## 발견된 문제

일반 LH2 예시 매니페스트에는 `receiving-boundary-01`이 있다. 이 항목은 인수 경계 인터페이스를 표현하지만, 예시 빈도 계획은 다음 이유로 이를 우발적 방출 설비에서 명시적으로 제외한다.

> boundary is an interface, not an accidental-release equipment item in this generic example

기존 시설 원장 실행기는 매니페스트의 모든 component ID를 “방출 결과가 반드시 있어야 하는 설비”로 전달했다. 그 결과 명시적으로 제외된 경계가 `missing expected component`로 다시 보고됐다. 제외 근거가 사라진 것은 아니지만, 누락과 제외가 동시에 표시되어 범위 회계가 혼동됐다.

## 수정 내용

`src/lh2_tno/component_scope.py`의 `expected_component_ids_for_release()`를 추가했다.

- 빈도 계획의 `excluded_model_components`를 읽는다.
- 명시적으로 제외된 인터페이스는 방출 결과를 요구하는 expected list에서 제거한다.
- 제외 행 자체는 시설 범위·coverage 원장에 계속 남긴다.
- 수직 handoff와 inventory-depletion 같은 확장 설비 ID는 명시적으로 추가한다.
- 중복 ID를 제거하고, 새로운 사고나 빈도를 만들지 않는다.

다음 두 실행기가 같은 규칙을 사용한다.

- `scripts/run_native_isolation_catalog_facility_chain.py`
- `scripts/run_native_full_scope_union_assessment.py`

따라서 `receiving-boundary-01`은 `EXCLUDED`로 남고 accidental-release 설비처럼 계산되지 않는다. 반대로 탱크·배관·밸브·벤트·펌프·기화기·재액화기와 두 개의 확장 방출 경로는 expected release component로 남는다.

## 현재 재실행 결과

포트가 결합된 24개 기본 사건과 두 확장 캠페인을 다시 실행했다.

| 항목 | 결과 |
|---|---:|
| 기본 사건 | 24 |
| 통합 사건 | 34 |
| 통합 case | 44 |
| 통합 risk atom | 176 |
| 상태 snapshot 결합 | 24/24 |
| 통합 frequency port 결합 | 34/34 |
| `receiving-boundary-01` | 명시적 `EXCLUDED` |
| IJHE 완료 감사 | 23개 검사, 17 pass, 6 blocked |

이번 수정으로 `missing expected component: receiving-boundary-01` 오류는 사라졌다. 그러나 이것은 provider 방출 packet 자격, 방출 종료 경계, 독립 물리검증, 전체 사고군 qualification, 시설 전체 IR/F-N을 닫은 것이 아니다. 최신 완료 감사는 계속 `INCOMPLETE_EVIDENCE`이며, 남은 6개 차단 사유를 그대로 공개한다.

## 검증

`tests/test_component_scope.py`는 명시적 인터페이스 제외가 누락으로 보고되지 않는지, 확장 ID가 보존·중복 제거되는지를 검사한다. 전체 테스트 결과는 `1177 passed`이다.
