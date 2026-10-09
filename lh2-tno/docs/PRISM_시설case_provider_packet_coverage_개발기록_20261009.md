# PRISM 시설 case provider packet coverage 개발기록

## 목적

시설 case 요청서와 공급자가 제출한 `prism.provider_packet_evidence.v1`를
정확히 대조하는 fail-closed 검증 단계를 추가했다. 이 단계는 packet을 위험도에
합산하지 않고, 사건을 잘못 연결하지 않았는지 확인하는 장부 역할만 한다.

## 대조 항목

각 case마다 다음 다섯 값이 모두 같아야 한다.

- `event_id`
- `component_id`
- `port_ids`
- provider source SHA-256 digest
- provider result SHA-256 digest

같은 사건이 D-3 m/s와 D-4 m/s처럼 여러 기상 조건을 가지면 공급자 packet 하나를
여러 case가 참조할 수 있다. 따라서 보고서는 고유 provider event 수와 전체 case 수를
따로 기록한다.

## 현재 결과

```powershell
$py = 'C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py scripts/audit_facility_case_packet_coverage.py `
  --requests results/20261024/native_generic_scope_vertical_facility_evidence_request_v2.json `
  --output results/20261024/native_generic_scope_vertical_case_packet_coverage_v1.json
```

현재 34개 case에 대해 qualified evidence는 0개이며 결과는
`NO_CASE_MATCH`이다. 이는 실패한 계산을 뜻하는 것이 아니라 실제 provider packet이
아직 들어오지 않았다는 뜻이다. 결과를 `QUALIFIED_FULL_CASE_COVERAGE`로 바꾸려면
각 사건의 실제 방출 packet과 qualification evidence를 제출해야 한다.

검증기는 빈도, 센서 신호, 누출 면적, 차단확률을 추정하지 않는다. 전체 case가
정확히 연결되어도 독립 물리검증, 사고범위 완성, 시설 IR/F-N gate가 별도로 통과되어야
시설 위험도를 공개할 수 있다.

## IJHE 완료 감사 연결 (2026-10-09)

`build_ijhe_completion_audit.py --facility-case-packet-coverage`를 사용하면 이
장부가 IJHE 완료 감사의 `facility_case_provider_packet_coverage` 검사로 들어간다.
`QUALIFIED_FULL_CASE_COVERAGE`가 아니면 차단 상태로 남기며, 현재 병합 일반 LH2
범위에서는 34개 case 중 0개가 qualified라서 `NO_CASE_MATCH`와 함께 감사 blocker로
기록된다. 이 검사는 기존의 합성 packet·부분 사고범위·시설 IR/F-N 차단을 대신하지
않고, “실행된 consequence case”와 “적격 provider packet이 정확히 연결된 case”를
분리해 보여준다.

최신 재생 결과는
`results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v12.json`이며,
25개 검사 중 21개가 통과하고 4개가 차단된 `INCOMPLETE_EVIDENCE`다. 새로 추가된
차단은 `facility cases do not all have exact qualified provider packet evidence`이다.
