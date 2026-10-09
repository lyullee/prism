# PRISM 실시간 시설 위험 handoff 개발 기록

## 목적

실시간 디지털트윈 계산은 설비 상태에서 시작해 provider 방출 경로와 SLABx-LH2 피해 결과까지 연결된다. 이 결과를 기존 시설 위험 장부에 전달할 때, 현재 기상 한 번의 진단값을 완전한 연간 시설 QRA로 오해하지 않도록 중간 handoff 계약을 추가했다.

## 추가된 계약

`build_realtime_facility_risk_handoff(snapshot)`은 `FacilityRealtimeConsequenceMonitor.update_from_frames()` 또는 `update_from_rows()`의 결과를 받아 `prism.realtime_facility_risk_handoff.v1` 패킷을 반환한다.

패킷은 다음 자료를 보존한다.

- 원본 snapshot 전체와 canonical SHA-256 digest
- 설비별 frame/mapping digest와 현재 기상 risk atom digest
- provider 방출 경로 상태, 종료 basis, 격리·재고 상태
- 현재 기상 IR, p05·published·p95 빈도 민감도, 조건부 expected-death F/N
- 시설 source-time window와 synchronous processing-time ledger

## 시설 ledger 승격 경계

handoff는 항상 `facility_ledger_merge.mergeable=false`와
`facility_annual_ir_available=false`, `facility_fn_available=false`를 기록한다. 실시간
risk atom은 관측된 한 방출의 피해 map이므로 다음 시설 ledger 필드가 없다.

- 연간 기상 condition ID와 확률
- release branch ID와 확률
- ignition branch별 피해와 branch ID
- 수용점 기준 expected deaths 폐합
- 적격 provider packet과 독립 물리검증 증거

따라서 PRISM은 event ID로 branch를 추측하거나 전체 피해를 점화 branch에 임의 배분하지 않는다. 누락 branch를 0으로 대체하지도 않는다. 별도 검토 캠페인이 이 자료를 갖춘 뒤 기존 `merge_facility_campaign_results()`에 넣어야 시설 ledger를 만들 수 있다.

## 검증

`tests/test_consequence_service.py`에 정상 snapshot 보존·승격 차단과 malformed snapshot 거절을 추가했다. 실시간 consequence 서비스 전체 시험은 **42 passed**이며, 이 기능은 기존 시설 IR/F-N 보류 정책을 변경하지 않는다.

이 handoff는 운영 화면과 후속 시설 campaign 사이의 감사 가능한 연결이다. 적격 provider 수를 실시간 monitor가 판정하지 않으므로 `qualification_evaluated_by_realtime_monitor=false`, 물리검증 주장은 `false`로 남는다.
