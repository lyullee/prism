# PRISM 시설별 공급자 packet 요청서

이 문서는 시설 위험평가 장부에 있는 사건을 외부 설비 모델 또는 실증 데이터의
정확한 입력 요청으로 바꾸는 방법을 설명한다. 목적은 빈도나 누출량을 새로
추정하는 것이 아니라, 어떤 사건의 어떤 포트에 어떤 시간 이력이 필요한지를
재현 가능하게 전달하는 것이다.

## 수직 handoff 현재 상태

`generic-lh2-full-scope-example/vertical-handoff/terminal-valve`에는 누출면적
5개가 있고, 각 사건은 D-3 m/s와 D-4 m/s 두 기상 조건으로 평가되어 총 10개
case가 있다. 현재 결과는 방출→SLABx-LH2→피해 계산까지 실행됐지만,
`EXECUTED_OPERATOR_LIMITED`이며 다음 입력이 synthetic이다.

- `input_origin=synthetic`
- 0.37 s 진단 종료 시각
- 수직에서 수평으로 바뀌는 handoff 상태의 독립 검증 부재
- qualified provider packet coverage: 0/34 facility cases

따라서 기존 결과는 개발 연결 확인용으로 보존하고, 시설 QRA의 최종 수치로
승격하지 않는다. 5개 사건 자체가 10개 기상 case로 확장된다는 점을 요청서에
명시한다.

외부 `DEGALI_TRANSFER`/PreSLHy 자료에서 `accepted=true`인 handoff replay 5건도
확인했다. 이 자료는 flux replay 오차와 내부 handoff 계약을 점검하는 데는
유용하지만, PRISM의 사건 ID·설비 component·사고 port·방출 digest·재고 및
종료 장부가 없다. 따라서 [`native_generic_scope_vertical_external_handoff_evidence_inventory_v1.json`](../results/20261024/native_generic_scope_vertical_external_handoff_evidence_inventory_v1.json)에
`SCREENING_ONLY_UNBOUND`로 기록했고, 수직 5개 사건의 provider packet이나
독립 시설 물리검증으로 사용하지 않았다.

## 자동 생성 파일

다음 명령은 최신 시설 assessment와 병합 scope matrix를 읽어 case별 요청서를
만든다.

```powershell
$py = 'C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py scripts/build_facility_evidence_request.py `
  --assessment results/20261024/native_generic_scope_vertical_merged_facility_assessment_population_v5.json `
  --scope-matrix results/20261023/native_generic_scope_vertical_merged_scope_matrix_v1.json `
  --output results/20261024/native_generic_scope_vertical_facility_evidence_request_v2.json
```

출력의 `case_requests`는 다음을 포함한다.

- 사건 ID, 설비/모델 component, provider branch, 기상 조건
- 사고 family별 필요한 상태 이력
- 정확히 일치해야 하는 `port_ids`, provider source/result digest
- 현재 packet 상태와 승격을 막는 이유
- qualified provider packet으로 교체해야 한다는 요청 종류

사건/포트/digest가 실제 공급자 출력과 일치하지 않으면 packet을 결합하지
않는다. 센서 신호나 임의 빈도로 누출 빈도를 학습하지 않으며, 외부 provider가
실제 또는 검증된 모델 출력임을 명시하기 전까지 `qualification_required`는
`true`로 남는다.

## 공급자에게 요청할 최소 수직 handoff 출력

각 10개 case마다 `prism.resolved_release.v1` packet을 제출해야 한다. packet은
동일한 사건 ID와 terminal port를 사용하고, 방출 시작부터 종료까지의 질량유량,
압력, 온도, 밀도, 유효면적, 방향, 수직→수평 handoff 상태를 시간 배열로
포함해야 한다. 종료는 임의의 0.37 s 명령 종료가 아니라 inventory depletion,
실제 isolation, 또는 모델이 설명하는 경계 종료 중 하나여야 한다.

질량·에너지 잔차, 초기/최종 inventory, property basis, source/result SHA-256,
검증 근거를 같이 제출해야 한다. 이 자료를 받은 뒤에만 같은 사건의 기존
SLABx-LH2 결과를 재실행하고, 시설 ledger와 IR/F-N 집계에 반영한다.
