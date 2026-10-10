# PRISM 설비별 빈도와 사고 방출 포트 연결

## 왜 필요한가

문헌 빈도는 탱크·배관·밸브 같은 **설비 항목**에 붙어 있지만, 실제 피해 계산은 특정한 **방출 포트**에서 시작한다. 한 설비에 출구가 여러 개이면 설비 이름만 맞춰서는 빈도가 어느 출구의 사고인지 알 수 없다. PRISM은 이 연결을 명시적으로 기록하고, 확인하지 못한 연결을 자동으로 만들지 않는다.

## 입력 방법

`FrequencyAsset`에 `port_ids`를 넣는다.

```json
{
  "id": "tank-shell",
  "model_component_id": "storage-tank-01",
  "profile": "LH2_VESSEL",
  "physical_scope_ids": ["tank-shell-01"],
  "port_ids": ["tank-accident-out"],
  "classification_basis": "reviewed equipment and accident-port allocation"
}
```

한 자산의 LOC가 한쪽 구멍과 양단 파열을 함께 만들면 `port_ids_by_loc`로 LOC별 포트를 지정한다. 예를 들어 `G1` 양단 파열에는 두 포트를, `G2` 구멍에는 한 포트를 넣는다.

```json
{
  "port_ids_by_loc": {
    "G1": ["pipe-accident-a", "pipe-accident-b"],
    "G2": ["pipe-accident-a"]
  }
}
```

이 값은 `physical_scope_ids`와 다른 정보다. `physical_scope_ids`는 문헌 빈도를 적용한 물리적 설비·배관 구간을 세고, `port_ids` 또는 `port_ids_by_loc`는 그 빈도가 어느 사고 출구로 배분됐는지 기록한다.

PRISM은 이벤트를 만들 때 다음을 확인한다.

1. 포트가 시설에 실제로 존재하는가.
2. 포트가 빈도 자산의 동일한 `model_component_id`에 속하는가.
3. 포트가 입구가 아닌 외부 방출 방향인가.
4. 단일 방출은 포트 하나, 양단 파열은 포트 두 개를 지정했는가.

## 계산 중 확인

생성된 `FrequencyEvent`에도 같은 `port_ids`가 보존된다. `bind_event()`가 provider 방출 패킷을 빈도와 결합할 때는 다음 조건을 모두 확인한다.

- component ID가 일치한다.
- provider가 반환한 방출 포트 목록이 이벤트의 `port_ids`와 순서까지 일치한다.
- 양단 파열은 두 endpoint 포트가 모두 일치한다.

계산이 성공한 뒤에도 이 식별자는 사라지지 않는다. 시설 캠페인의 `cases[*].frequency_port_ids`와 `risk_atoms[*].frequency_port_ids`에 같은 포트 목록이 남기 때문에, IR/F-N 집계 결과를 다시 탱크·배관·밸브의 사고 출구까지 추적할 수 있다. 포트가 없던 하위 호환 이벤트는 이 필드가 `null`로 남는다.

여러 설비 캠페인을 합치는 `merge_facility_campaign_results()`도 같은 비교를 다시 한다. 최종 ledger의 `frequency_port_binding`에 포트 지정 사건 수, 미지정 사건 수, case/risk atom 불일치 수와 상태가 기록된다. 사건의 포트와 최종 행의 포트가 다르면 시설 범위는 `PORT_BINDING_MISMATCH`로 보류된다.

`status=ALIGNED`는 포트를 선언한 행끼리 서로 같은지를 뜻할 뿐이다. 포트가 하나도 없는 하위 호환 사건이 섞이면 `port_unbound_event_count`가 남고 `facility_qra_allowed=false`가 된다. 즉 provider 출구가 나중에 도착해도 검토된 문헌 빈도 포트가 없으면 시설 QRA 승격은 열리지 않는다. `frequency_inference_allowed`는 항상 `false`다.

`build_facility_assessment()`도 이 요약을 최상위 `frequency_port_binding`으로 복사한다. 따라서 보고서 소비자는 중첩 ledger를 열지 않고도 포트 결합 상태를 확인할 수 있다.

IJHE 완료 감사에 `diagnostic_facility_frequency_port_binding` 검사도 기록된다. 이 검사는 포트 추적성만 확인하는 진단 검사이며, 통과해도 qualified provider·독립 물리검증·시설 전체 QRA 게이트를 열지 않는다.

v0.6.0 준비도 보고서의 `chain.frequency_port_binding`에도 같은 추적이 요약된다. 공개 시설평가와 중첩 ledger의 복사본이 다르면 준비도 검증기가 오류를 내며, `NOT_REPORTED`·`PORT_BINDING_MISMATCH`·legacy 상태는 그대로 보류 상태로 남는다.

오래된 시설 assessment에 이 필드가 아직 없으면 readiness builder가 최신 `facility_evidence_request.frequency_port_binding`을 진단 출처로 표시한다. 이때 `source=facility_evidence_request`, `status=PORT_BINDING_WITHHELD`처럼 자료 부족을 드러내며 assessment를 보정하거나 포트를 추론하지 않는다.

readiness의 `facility_qra_allowed`는 전체 provider·검증 게이트가 남아 있는 동안 항상 `false`다. 하위 포트 연결 결과는 `port_binding_facility_qra_allowed`로 따로 보여 주어, 포트 검토 완료와 시설 QRA 승격을 섞지 않는다.

포트가 다르면 빈도를 억지로 붙이지 않고 오류를 낸다. 이 오류는 해당 사고 케이스가 **미계산**이라는 뜻이며, 빈도를 0으로 바꾸거나 다른 포트로 옮기지 않는다.

시설 증거요청서도 provider packet이 아직 없는 미계산 사건의 `frequency_port_ids`를 `exact_match_required.port_ids`에 그대로 넣는다. provider가 나중에 다른 포트를 반환하면 `PORT_BINDING_MISMATCH`로 표시하고, 해당 packet은 자격심사에 사용할 수 없다.

요청서 최상위 `frequency_port_binding`은 검토된 빈도 포트, provider packet에만 있는 포트, 포트 불일치, 포트 미확정 사건을 따로 센다. 따라서 provider 출구가 존재해도 문헌 빈도 포트가 없으면 `PORT_BINDING_WITHHELD`로 남는다.

이 검사는 `bind_event()`에만 있지 않다. 이미 빈도가 들어 있는 `ConsequenceRequest`를 JSON으로 직접 만들더라도 요청 검증기가 provider 방출 포트와 `frequency_event.port_ids`를 다시 비교한다.

provider 방출 작업목록을 만들 때 매니페스트에서 지정 포트가 빠져 있으면 작업목록은 해당 이벤트를 `UNCOMPUTED_NO_ACCIDENT_PORT`로 남긴다. 정상 운전 포트를 사고 포트로 대체하지 않으며, 누락된 포트를 복구할 때까지 packet 수는 증가하지 않는다.

이런 worklist를 시설 캠페인으로 컴파일하려 하면 컴파일러도 중단한다. 포트 매핑이 복구되기 전에는 캠페인·IR/F-N 계산으로 진행하지 않고, worklist 자체만 진단 자료로 남긴다.

## 포트가 아직 없는 기존 계획

기존 문헌 계획은 하위 호환을 위해 `port_ids` 없이도 읽을 수 있다. 이런 이벤트는 component-level 빈도로만 표시되며, provider가 반환한 특정 방출 포트의 근거가 자동으로 생기지 않는다. 따라서 보고서의 `frequency_port_binding`에 `port_unbound_event_count`로 남는다.

이 상태는 계산을 중단시키지 않지만, 설비에 출구가 여러 개일 때는 설계 검토자가 사고 포트 배분을 추가해야 한다. 포트가 없다는 이유로 현장 빈도를 학습하거나 압력·센서값으로 빈도를 추정하지 않는다.

## 보고서 필드

- `frequency_port_binding.port_scoped_event_count`: reviewed accident port가 지정된 이벤트 수
- `frequency_port_binding.port_unbound_event_count`: component-level로만 남은 이벤트 수
- `frequency_port_binding.all_events_port_scoped`: 모든 생성 이벤트에 포트가 있는지
- `frequency_port_binding.facility_qra_allowed`: 모든 이벤트가 검토된 포트로 결합되고 행 간 불일치가 없을 때만 `true`
- `frequency_port_binding.frequency_inference_allowed`: 빈도 추론 금지 플래그이며 항상 `false`
- `coverage.by_component[*].reviewed_accident_port_ids`: 설비별 검토된 사고 포트 목록
- `coverage.by_component[*].generated_port_unbound_event_count`: 설비별 포트 미지정 이벤트 수

외부 설비 모델 감사에서도 crosswalk 행에 `accident_port_ids`를 기록할 수 있다. 이 값이 있는 문헌 이벤트는 해당 목록에 포함되는지 다시 확인하고, 목록이 없거나 포트가 다르면 `PORT_BINDING_WITHHELD`로 남는다. 외부 모델의 정상 상태나 후보 포트 목록만으로 사고 포트를 추정하지 않는다.

`strict_facility_qra_gate`는 현재 `false`로 유지한다. 즉, 이 기능은 잘못된 포트 결합을 막고 심사 가능한 누락을 드러내는 연결부이며, 독립 물리 검증·provider 자격 증명·시설 전체 범위 충족을 대신하지 않는다.

시설 ledger와 assessment에는 `qualified_facility_qra_blocking_reasons`도 남긴다. 문헌 빈도 포트가 하나라도 빠지면 조건부 진단 IR/F-N은 보존하지만 qualified facility QRA는 `false`로 유지한다.

배포된 `examples/generic_lh2_full_scope_frequency_plan.json`은 이 계약을 사용해 24개 문헌 이벤트를 모두 포트 지정 상태로 생성한다. 열교환기 양단 파열 LOC는 `port_ids_by_loc`에 두 출구를, 단일 구멍 LOC는 한 출구를 지정한다. 이 예제의 `frequency_port_binding`은 `port_scoped_event_count=24`, `port_unbound_event_count=0`이어야 한다.

## 빈도에 관한 경계

빈도는 계속 검토된 Purple Book/LH2 문헌 카탈로그에서만 온다. 디지털 트윈의 정상 상태, 알람, 압력, 온도 또는 누출 감지 신호는 빈도를 만들지 않는다. 신호는 상태 스냅샷과 provider 방출 계산의 입력으로만 사용되며, 문헌 빈도와 포트 배분은 별도로 감사한다.
