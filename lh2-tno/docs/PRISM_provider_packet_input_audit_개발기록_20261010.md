# PRISM provider packet 일괄 입력 감사

## 목적

시설 case 대조기는 이미 만들어진 `prism.provider_packet_evidence.v1` 행이 요청 case와 정확히 맞는지 확인한다. 하지만 실제 설비 모델에서 release 파일과 qualification sidecar를 여러 개 받을 때, 파일 한 쌍이 왜 거절됐는지 기록하는 입력 경계가 필요했다. 이 기록은 그 경계를 `prism.provider_packet_input_audit.v1`로 고정한 것이다.

## 입력 규칙

`scripts/audit_provider_packet_inputs.py`는 다음 manifest를 읽는다.

```json
{
  "records": [
    {
      "record_id": "tank-event-001",
      "release_path": "tank-event-001.release.json",
      "qualification_path": "tank-event-001.qualification.json"
    }
  ]
}
```

`release`와 `qualification` 객체를 inline으로 넣는 것도 허용한다. 경로는 manifest 파일 기준 상대경로로 해석한다. 각 행은 기존 `build_provider_packet_evidence_from_records()`에 전달되어 다음을 모두 다시 확인한다.

- `prism.resolved_release.v1` 또는 `prism.resolved_release_set.v1` strict release contract
- provider가 선언한 시간·종료·질량·엔탈피 장부
- `status=qualified_actual` 및 실제 provider origin
- release와 sidecar의 event/component/port 및 source/result SHA-256 exact match
- `input_origin=synthetic` 차단

실패한 행도 결과에서 제거하지 않고 `blocking_reasons`와 함께 남긴다. 동일 `event_id`가 두 번 들어오면 첫 행만 accepted catalog에 남기고 두 번째 행을 중복으로 거절한다.

## 현재 결과

현재 일반 LH2 union에 연결된 실제 provider release/qualification 파일은 없다. 빈 template [`examples/provider_packet_input_manifest.json`](../examples/provider_packet_input_manifest.json)을 감사한 결과는 다음과 같다.

- 상태: `NO_PROVIDER_PACKET_INPUT`
- 입력 행: 0
- strict 자격 통과 packet: 0
- 시설 case 연결: 0/44 (기존 exact case coverage와 일치)
- 문헌 빈도 부여: 없음
- 시설 IR/F-N 승격: 없음

최신 결과는 [`provider_packet_input_audit.json`](../results/20261026/native_full_scope_union_assessment/provider_packet_input_audit.json)이다. 이 결과는 자료가 없다는 사실을 명시할 뿐, 위험도가 0이라는 뜻이 아니다.

## 다음 사용 순서

1. 설비별 실제 사고 release와 qualification sidecar를 manifest에 추가한다.
2. `python scripts/audit_provider_packet_inputs.py --manifest provider_packet_manifest.json --output provider_packet_input_audit.json`을 실행한다.
3. `QUALIFIED_PROVIDER_PACKET_CATALOG`인 경우에만 `provider_packet_evidence` 배열을 별도 catalog로 저장한다.
4. `facility_case_packet_coverage.py`로 44개 facility case의 event/component/port/source/result digest를 다시 대조한다.
5. 독립 물리검증, 주요 사고범위, 시설 IR/F-N gate가 모두 닫히기 전에는 QRA를 승격하지 않는다.

이 경계는 현장 빈도를 학습하지 않고, packet에 빈도를 넣지도 않는다. 문헌 빈도는 기존 `FrequencyPlan`에서 한 번만 적용한다.
