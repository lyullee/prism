# PRISM IJHE 완성 목표와 진행 기준

2026-10-09. 사용자가 제시한 5개 개발 범위를 목표로 설정했다. 출발점은 공개된 **PRISM 0.6.0**이다. 인용된 v0.3.0은 과거 중간 기록이며 v0.4 설비 기체 경계, v0.5 선택형 모드, v0.6 명칭·배포 이후 상태를 사용한다.

## 완료 목표

**선언한 적용범위의 주요 사고를 설비 상태부터 시설 위험도까지 계산하고, 미계산 사고·불확실성·처리시간을 명확히 보여준다.**

기본 적용범위는 일반적인 옥외 LH2 시설이다. 기존 설비 모델은 설비의 압력·엔탈피·상·유량·재고를 계산하고, SLABx-LH2/SLABx와 풀·피해 모델을 PRISM이 연결한다. 특정 센터의 설비·태그·운전 절차를 일반 기본값으로 강제하지 않는다.

현장 사고빈도 수집과 센서 기반 빈도 학습은 필수 개발에 포함하지 않는다. 문헌 빈도와 명시한 불확실성·민감도를 사용한다. 실내·폭굉·전체 도미노는 이번 필수 범위에서 제외한다.

## 출발점에서 이미 있는 기능

- 시설/포트/물성·시간·질량 계약, 문헌 빈도 17개 프로파일·55행, 단일 구멍 사건 결합.
- 제한된 옥외 방출→지면 도달/풀→극저온 전이→확산→점화→화재/폭발→인명 피해의 실제 진단 실행.
- native 설비 모델이 계산한 수평·대기압·Mach≤0.3 기체 출구와 provider가 명시한 수직→수평 `VerticalGasHandoff` 경계를 `ResolvedGasRelease`로 수용하고 문헌 `LH2_PIPE` 5개 누출 크기를 각각 독립 실행했다. 추가로 `LayeredTankNetworkSimulator`/`CommandedValve`의 합성 tank·isolation success/failure history 10건을 같은 경계 계약과 시설 campaign에 연결했다. 이번 단계에서는 외부 `lh2dt` `HomogeneousTank`+`Valve`가 내보낸 flash 기체·지면 액체·액적 도착 시계를 `ResolvedLiquidRelease`로 수용해 DynamicLH2PoolX와 최종 피해까지 한 건 실행했다. provider의 `ParaHydrogen`과 native 풀 모델의 `Hydrogen` 기준은 provenance가 있는 명시적 변환 경계로만 연결하며, 교차 물성 검증 전까지 operator-limited로 남긴다. 소비자가 유량을 다시 계산하지 않는다.
- 센서 단위·품질·시각 검사와 알려진 누출의 P/T 갱신, 동일 결과 캐시.
- 기존 외부 TNO 엔진의 IR/F-N 기능은 있지만 새 LH2 경로의 사건·기상 자동 전체 합산에는 연결돼 있지 않았다.
- 494개 portable 검사, 자연 종료 실제 체인 1건, G1 finite-inventory liquid-jet operator-limited 사례 2건과 G3 사례 4건, steady equipment-resolved pipe campaign 2건, transient isolation success/failure pipe campaign 20건, 다섯 inventory-depletion LOC의 두 기상 조건 10건, 두 provider 출구를 결합한 양단 파열 campaign 2건, provider-resolved vertical handoff campaign 2건, **다섯 vertical 개구면적을 각각 provider 계산한 10개 case**, provider-resolved liquid/two-phase exit의 pool·확산·피해 연결 1건, no-rainout pool 경계 3건, 문헌 빈도 분위수 재가중 검사를 확인했다. 양단 endpoint마다 Frechet 교집합 가능 범위와 보수적 합집합 상한을 기록하되 공동 plume 해석은 보류하고, 공유 사건 빈도는 한 번만 적용한다. 여러 설비의 frame을 한 시설 snapshot으로 묶는 `FacilityRealtimeConsequenceMonitor`와 설비별 provenance/deadline 회계도 추가했다. 매니페스트에 없는 사고 family의 `NOT_APPLICABLE` 회계도 추가했다. 현장 절대위험 검증·1 Hz 신규 계산·완전한 시설 feedback은 미완료다.
- DynamicLH2PoolX의 물/알루미늄 hold-out 반경 오차와 HSE 질량잔차를 해시 장부로 확인했지만, protocol snapshot 해시 drift가 있어 제한 구성요소 증거로만 사용한다. 설비 방출·대기확산·점화·IR/F-N 전체 체인의 물리 검증으로 확대하지 않는다.

## 단계별 작업과 통과 기준

| 단계 | 개발할 내용 | 완료 판정에 필요한 근거 |
|---|---|---|
| A. 설비 상태 | 탱크·배관·밸브·펌프·기화기·벤트의 실제 지원 모델/포트/상/에너지 기준 확인, 사고 위치와 연결, 유량 소유권 유지 | 지원표, 동일 물성·시계, 설비별 실제 계산 전달, 질량·정적/전체 에너지 장부의 구분, 미지원 설비 표시. `ResolvedLiquidRelease`로 provider flash/지면 분할 계약을 추가했지만 LayeredTank 실제 액체/2상 상태와 모든 설비 지원은 남아 있다. |
| B. 방출 경로 | 단일 구멍의 실제 종료, 차단 성공/실패, 재고 소진, 전량/600초·양단 파열·수직 벤트 전용 경로 | 통합 source의 압력 평형 자연 종료와 무연장 질량 장부, G1 SLABx-LH2 liquid-jet finite-inventory 질량 폐합, 5개 LH2 pipe area-bin 각각에 대한 합성 layered-tank/commanded-valve의 0.25초 isolation-success 및 0.5초 isolation-failure 진단 이력을 구현했다. 추가로 `ResolvedGasReleaseSet`·`equipment_two_sided_rupture`·`location_weight`를 구현해 TNO_PIPE full-bore 양단을 한 사건으로 두 번의 provider 경계에서 계산하고 Frechet 상한으로 결합했다. 이제 provider-resolved liquid/two-phase exit의 gas/ground partition과 pool/피해 연결 1건도 실행했다. barrier 확률은 합성값이고 재고 소진을 뜻하지 않는다. G1·양단·수직 handoff·liquid provider 경로는 provider 상호작용·액체/2상 feedback·실제 설비 입력의 물리 검증이 남아 있다. 수직 경로 자체는 handoff 계약과 synthetic campaign까지 구현했지만, 수직 제트 원거리 모델과 교차상호작용은 미완료다. |
| C. 시설 위험 | 모든 LOC의 경로 배정, 위치 배분, 연간 기상/인구와 점화·차단 분기, 기존 TNO IR/F-N 함수 연결 | 5개 LH2 pipe LOC의 사건 목록과 20개 물리 사례를 모두 실행하고, 조건부 확률 폐합, 빈도 1회 적용, 수용점별 IR, 개별 사건별 인구 피해/F-N을 확인했다. 합성 종료·장벽과 실제 설비 목록/위치가 없으므로 total은 보류. 매니페스트에 없는 설비 family는 `NOT_APPLICABLE`로 구분하고, 존재하는 설비의 누락·미계산만 blocker로 남긴다. |
| D. 빈도 불확실성 | LH2 문헌 분포, 상관 가정별 비교, TNO 기본값의 명시적 민감도, 위험 기여/설비 순위 안정성 | 근거 없는 사전분포 금지, TNO/LH2 대안 중복 금지, 상관 가정과 미계산 범위 공개, 분포·민감도·복사율 구간 구분 |
| E. 검증·속도 | 보유 공정 자료·외부 실험 출처/분할, 관측 연산자와 독립 검증, 보존/수렴, 처리시간 | 학습/검증 누수 없음, 실측/복원/합성 구분, 적용범위별 오차, 하드웨어·신규/캐시 구분, 반복 p50/p95/p99와 실패 기록 |

600초 전량방출은 `inventory_over_600s` operator와 완전 provider 이력 계약을 구현했고, 합성 10 m³ 진단 1건에서 600초 end-to-end chain을 실행했다. 액체·2상 provider 출구는 `ResolvedLiquidRelease`로 한 건을 실행했으며, airborne liquid은 별도 adapter가 없으면 거절한다. 실제 LayeredTank 액체/2상 재고 입력·현장 검증·시설 전체 위험 연결은 아직 완료하지 않았다.

단계 C의 실행 회계는 A/B에서 아직 계산하지 못한 항목을 즉시 드러내므로 먼저 공통 실행기를 구현한다. 이것이 A/B의 실제 공정 결합이나 장시간 방출을 완료했다는 뜻은 아니다.

## 여러 설비의 실시간 snapshot 경계

`RealtimeConsequenceMonitor`가 한 frame을 처리하는 동안 설비가 여러 개이면
`FacilityRealtimeConsequenceMonitor`가 component ID별 monitor를 조정한다. 각
설비는 자기 normalizer·사고 template·provider `release_resolver`를 명시해야 하며,
시설 monitor가 이름으로 설비나 사고를 자동 선택하지 않는다. 따라서 저장탱크의
압력 신호가 펌프의 방출 경계로 잘못 연결되지 않는다.

한 호출은 선언한 모든 설비의 frame을 요구한다. 누락 frame, 알 수 없는 component,
동일 stream ID의 재사용, 단위·시간·품질 오류, provider resolver 오류가 하나라도
있으면 전체 snapshot은 `REJECTED`다. 성공한 component 결과는 원인 분석을 위해
보존하지만 누락 설비에 이전 결과나 0을 넣지 않는다. `aggregate`에는 설비별
fresh-physics/cache 횟수, deadline miss 횟수, provider 방출 경계 개수와
`facility_annual_risk_available=false`가 남는다.

이 기능은 디지털트윈 화면과 운영 수집기 사이의 **동기 회계 경계**다. OPC-UA·MQTT
수집, 비동기 scheduler, 알람 화면, 시설 연간 빈도와 IR/F-N 계산은 별도 계층이며,
이 monitor를 추가했다고 1 Hz 신규 물리 계산이나 시설 QRA가 입증되지는 않는다.

## 첫 구현: 다중 사건·기상 실행기

`campaign.py`에서 각 문헌 LOC를 물리 요청 또는 미계산 사유에 연결하고, 각 요청을 연간 기상/인구 조건과 차단·방출 분기별로 실행한다. 점화별 피해를 분리한 상태로 native TNO `total_individual_risk`와 `fn_curve`에 넘긴다.

- 고정 수용점의 IR은 **그 위치에 항상 있는 한 사람**의 값이다. 인구의 재실확률을 IR에 다시 곱하지 않는다.
- 인구는 조건별 서로 겹치지 않는 옥외 집단을 수용점에 대표 배치한다. 재실확률은 집단의 기대 인원 계산에 적용한다.
- F-N은 기존 엔진의 **사건별 기대 사망자 수** 관례를 유지한다. 사람별 사망의 확률분포를 샘플링한 F-N이라고 설명하지 않는다.
- 기상·방출/차단·점화·누출 빈도는 각각 한 번만 곱한다.
- 문헌 빈도 불확실성은 event에 실제로 저장된 p05/published/p95만 사용한다. 자산별 공유 분위수와 사건별 독립 event-bound 시나리오를 비교해 상관 가정을 드러낸다. catalogue에 공개된 로그정규 mu/sigma가 있는 사건은 known-contribution p05/p50/p95 표본 구간을 추가할 수 있지만, 시설 전체 확률분포나 credible interval로 부르려면 선언 범위가 완전해야 한다.
- 로그정규 표본화 결과에는 계산된 known contribution 안에서 자산별 평균 순위와 1위 확률을 기록한다. 이는 미계산 LOC를 포함한 시설 전체 방호 우선순위가 아니다.
- 누락된 LOC는 입력 오류다. 의도적으로 미계산할 LOC도 사유와 함께 명시한다.
- backend 실패나 잘린 공간 영역은 미계산 회계에 남기며, 알려진 기여와 total을 분리한다.
- 0.2/0.4초 같은 합성 종료는 전체 시설 위험 완료의 근거가 되지 않는다.
- `source_duration_mode=model_natural`은 통합 source가 반환한 실제 구간만 사용한다. 요청 시간이 5초여도 모델이 0.2초에서 압력 평형으로 끝내면 유효 방출시간을 0.2초로 기록하며, 마지막 유량을 5초까지 채우지 않는다. 이 연결은 검증했지만 모델의 압력 평형 예측 정확도는 별도 검증 대상이다.
- G1의 `source_operator=inventory_liquid_jet`은 instantaneous inventory LOC를 구멍 누출로 바꾸지 않고 SLABx-LH2 liquid-jet source를 호출한다. 명시한 분무·액적·증발 가정과 2초 재고 폐합을 사용하며, 일정 upstream 상태와 열린 spray-energy closure 때문에 `EXECUTED_OPERATOR_LIMITED`로 기록한다.
- 설비 transient 진단은 외부 `LayeredTankNetworkSimulator`/`CommandedValve`에서 탱크 증기 셀 유량과 밸브 명령을 계산하고, 5개 `LH2_PIPE` area-bin의 isolation-success와 isolation-failure를 각각 `ResolvedGasRelease`로 전달한다. 성공은 0.25초 차단 뒤 유량 0, 실패는 0.5초 진단시계 동안 열린 유량으로 기록한다. 별도 `HomogeneousTank`/`DynamicNetworkSimulator` adapter는 다섯 area-bin에서 양수 재고 threshold에 도달한 실제 provider 구간을 두 기상 조건에 전달하여 10건을 실행했다. 합성 초기 압력·대기압 경계·저 Mach 수평 출구에 한정하며, barrier 확률과 재고 입력은 현장 근거가 아니고 실제 actuator 지연·실패확률·LayeredTank 액체/2상 방출은 아직 지원하지 않는다.

이 단계의 예제·명령·측정 결과는 별도 실행 기록에 정리한다. 이번 구현은 공개 0.6.2 이후의 개발 변경이며, 현재 commit에 대해 새 PyPI/DOI 릴리스는 만들지 않았다. 기존 0.6.2 공개 기록은 `docs/PRISM_v062_PyPI_DOI_배포기록_20261009.md`에 고정되어 있다.

## 연구 완료와 구분할 것

코드 검사 통과는 독립 물리 검증이 아니다. 선언한 일부 경로의 수치 합산이 끝나도 미계산 사고가 있으면 전체 시설 위험값으로 보고하지 않는다. 코드가 빠르다는 측정 없이 real-time/1 Hz를 주장하지 않는다. 제시한 목표는 계속 진행 중이며 이 문서를 추가했다는 이유로 완료 표시하지 않는다.

## 자동 완료 감사

수동으로 상태를 판단하지 않도록 다음 명령이 방출→피해 실행, 방출 지속시간·차단·재고 질량 장부, 주요 사고 범위, 시설 IR/F-N, 물리 검증, 빈도 불확실성, 처리시간을 각각 검사한다.

```powershell
python lh2-tno/scripts/build_ijhe_completion_audit.py `
  --current-status lh2-tno/CURRENT_STATUS.json `
  --scope-matrix results/20261009/provider_release_full_chain_diagnostic/accident_scope_matrix.json `
  --campaign-result results/20261009/provider_release_full_chain_diagnostic/campaign_result.json `
  --uncertainty-result results/20261009/provider_release_full_chain_diagnostic/campaign_result_with_uncertainty.json `
  --provider-worklist results/20261009/provider_evidence/generic_lh2_provider_release_worklist.json `
  --provider-qualification-coverage results/20261009/provider_evidence/provider_catalog_coverage.json `
  --output results/20261009/provider_release_full_chain_diagnostic/ijhe_completion_audit.json
```

현재 실제 합성 provider 경로의 판정은 `INCOMPLETE_EVIDENCE`다. 설비 모델은 `STATE_ONLY_BOUND`이고 사고 release export 0개이며, 실제 provider 사고 packet 부재, 사고 가족 미완결, 시설 IR/F-N 보류, 독립 전체 체인 물리검증 부재, 완전 시설 빈도 credible interval 부재가 차단 이유로 남는다. 이 감사기가 `READY_FOR_IJHE_SCOPE`를 내기 전에는 논문에서 전체 시설 QRA 완성으로 표현하지 않는다.

## 2026-10-12 VentStack 방출 경계 추가

외부 `VentStack.evaluate()`를 별도 사고 adapter로 호출하고, steady two-port 결과를 0.5 s·10 interval의 synthetic diagnostic gas history로 변환했다. 기본 102 kPa upstream·0.01 m bore에서 strict `ResolvedGasRelease` 질량 잔차 `0 kg`, 엔탈피 잔차 `0 J`를 얻었고, low-Mach gas packet을 최종 피해 chain까지 실행했다.

이 경계는 tank/PSV inventory, relief setpoint, field vent frequency를 제공하지 않는다. upstream 압력·bore가 커지면 compressible/underexpanded plane이 되어 현재 low-Mach scope gate에서 차단되며, 별도 compressible adapter 없이는 승격하지 않는다.

## 2026-10-12 DynamicHEMPipe 방출 경계 추가

외부 `DynamicHEMPipe`를 명시적 full-bore atmospheric outlet로 실행하는 PRISM 측 adapter를 추가했다. 유한체적 pipe 상태가 반환한 유량·엔탈피를 왼쪽 유지 interval로 보존하고, `prism.resolved_release.v1` 액체/2상 packet의 질량·에너지 장부를 다시 적분했다. `0.001 s` 진단에서 질량 잔차는 `0 kg`, 에너지 잔차는 약 `-5.42e-20 J`였다. 이후 외부 커밋 `3d9b982`의 압력 평형 이벤트 보정을 `source_duration_mode=model_natural`로 정식 연결해, 0.01 m full-bore 합성 배관에서 `model_pressure_equalization`, 최종 압력 `101,325.000000004 Pa`, 질량 잔차 `0 kg`을 기록하고 consequence chain까지 실행했다. 상세 기록은 [native 사고계약 감사](PRISM_외부LH2모델_native_사고계약_감사_20261018.md)의 full-bore 절에 있다.

이 packet은 잔류 pipe inventory를 보유한 고정 진단시계이며 전량 방출·현장 배관 파손 확률·차단 성공을 의미하지 않는다. `validate_lh2dt_prism_packet_chain.py`의 `radius_m=0.0001 m` 선언 sensitivity footprint를 사용해 최종 피해 체인까지 실행했지만, 이 footprint와 synthetic inlet/geometry는 현장 형상으로 승격하지 않는다.

## 2026-10-12 LayeredTank strict packet과 전체 chain

외부 `LayeredTankNetworkSimulator+CommandedValve`의 합성 양수 재고 threshold 이력을 `scripts/export_lh2dt_layered_tank_prism_packet.py`로 `prism.external_accident_history.v1`에 맞추고, 공통 strict adapter를 통해 `prism.resolved_release.v1` 액체 packet으로 변환했다. provider 16개 interval의 왼쪽 유지 시간, `inventory_depletion` 종료 basis, 누적 질량·엔탈피를 검사한 결과 8.0 s 방출, 질량 잔차 `1.73e-18 kg`, 에너지 잔차 `0 J`를 얻었다. `scripts/validate_lh2dt_prism_packet_chain.py`는 이 packet을 DynamicLH2PoolX, SLABx-LH2/SLABx, cloud, 점화, 화재·폭발 및 TNO 피해까지 실행했다.

이 실행은 선언된 `0.005 m` sensitivity pool footprint를 사용해 작은 합성 packet의 wet-cell 조건을 확인한 것이다. 지면 액체가 없는 provider 결과는 `prism.no_rainout_evidence.v1`로 선언할 수 있으며, 이 경우 기본 pool context를 사용하지 않는다. 외부 provider가 flash gas와 airborne liquid을 계산하지 않고, 설비 형상·개구·차단 신뢰도·현장 재고도 합성이므로 `EXECUTED_OPERATOR_LIMITED` 진단으로만 기록한다. 초단시간 finite-release puff는 provider 방출시간을 보존한 native puff를 먼저 시도하고, backend가 거부할 때만 순간화한다. provider packet 승격·빈도 부여·시설 IR/F-N·독립 물리검증은 계속 보류한다. 외부 `lh2dt` 각 클래스에 native 사고 export를 넣고 24개 사건과 exact-match하는 작업은 다음 단계다.

## 2026-10-11 연결 경계 보완

외부 설비 모델이 정상 상태만 계산하고 사고 이력을 내보내지 않는 문제를 명확히 분리하기 위해 `src/lh2_tno/equipment_accident_export.py`를 추가했다. `AccidentReleaseExportRequest`는 사고 포트·개구·관찰시계·provider 종료 소유권·원본 digest를 필수화하고, provider는 `export_accident_history(request)`와 `prism.external_accident_history.v1`를 제공해야 한다. `evaluate()`·`simulate()`·`advance()`만 있는 모델은 사고 packet으로 사용하지 않는다. 합성·스크리닝 결과는 strict packet 검증 뒤에도 `DIAGNOSTIC_PACKET_NOT_PROMOTED`로 남긴다.

현재 실제 `lh2dt_models` 클래스에는 이 전용 메서드가 없으므로 설비 매핑은 여전히 `STATE_ONLY_BOUND`, 실제 적격 packet은 0건이다. 2026-10-14부터 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기의 PRISM-side 진단 adapter 7건을 별도로 기록하지만, 이는 `synthetic_diagnostic` packet을 만드는 연결 시험이지 native provider export나 물리검증 완료가 아니다. 새 계약은 외부 모델이 구현될 때 사용할 PRISM 측 경계이며, 시설 IR/F-N·빈도·물리 검증 완료를 대신하지 않는다. 예시 요청은 `examples/equipment_accident_export_request.json`, 상세 규칙은 [외부 설비 사고방출 export 계약](PRISM_외부설비_사고방출_export_계약_20261011.md)에 기록했다. 새 계약 테스트를 포함한 portable suite는 394개이며, IJHE 자동 감사는 17개 검사 중 7개 차단 상태를 유지한다.

## 2026-10-14 진단 adapter의 IJHE 감사 연결

`build_ijhe_completion_audit.py`는 이제 `--diagnostic-adapter-registry`를 받을 수 있다. 이 ledger는 adapter 클래스가 catalog에서 해석되고 공통 `export_accident_history(request)` 메서드를 제공하는지만 검사한다. provider 인스턴스 수와 qualified packet 수를 별도로 표시하므로, adapter 실행 계약이 PASS여도 실제 사고 방출 provider와 시설 QRA가 완료된 것으로 해석하지 않는다.

```powershell
python scripts/build_ijhe_completion_audit.py `
  --current-status CURRENT_STATUS.json `
  --scope-matrix results/20261014/generic_mixed_accident_scope_matrix_refined_pool.json `
  --campaign-result results/20261014/generic_mixed_provider_campaign_refined_pool_result.json `
  --uncertainty-result results/20261014/generic_lh2_mixed_facility_assessment_refined_pool.json `
  --facility-assessment results/20261014/generic_lh2_mixed_facility_assessment_refined_pool.json `
  --vertical-handoff-result results/20261009/vertical_vent/verification.json `
  --provider-worklist results/20261014/generic_lh2_provider_release_worklist_diagnostic_adapter.json `
  --diagnostic-adapter-registry results/20261014/diagnostic_adapter_registry_audit_live.json `
  --diagnostic-adapter-execution results/20261014/diagnostic_adapter_runner_worklist_storage_001.json `
  --output results/20261014/ijhe_completion_audit_live_with_runner.json
```

현재 live 결과는 17개 검사 중 7개 차단, 10개 통과다. `diagnostic_adapter_execution_contract`는 7/7 클래스 해석으로 통과하고, `diagnostic_worklist_execution_evidence`도 저장탱크 worklist 항목의 event/component/port/opening exact-match와 `END_TO_END_DIAGNOSTIC_EXECUTED`를 확인해 통과한다. 추가한 `diagnostic_worklist_packet_coverage_evidence`는 저장된 외부 결과를 전체 24개 worklist와 대조하여 후보 24개, exact/strict 24개, consequence-chain 기록 15개를 확인한다. 이번 갱신에서는 외부 LayeredTank export 명령에 worklist의 `event_id`·`port_id`를 직접 전달하고 storage-tank의 5개 개구를 실행했다. 100% 개구는 외부 모델의 `All cell masses must be finite and positive` 조건을 피하기 위해 더 작은 진단 시간 간격을 사용했으며, 이는 물리 정확도를 높였다는 뜻이 아니라 모델 안정성 조건을 기록한 것이다. 추가된 조건부 시설 위험 검사는 24개 event·24개 case·96개 risk atom에서 조건부 IR/F-N이 계산되었음을 확인하고, 문헌 빈도 불확실성 검사는 5개 시나리오·자산 순위·조건부 IR/F-N 재가중을 확인하고, 별도 vertical handoff 검사는 5개 generated event 중 2개 실행 case의 provider handoff 소비를 확인하지만, total facility risk나 시설 credible interval을 승격하지 않는다. 이 여섯 진단 검사는 provider 인스턴스의 호출 경계와 저장된 진단 증거만 확인하며, qualified packet·빈도·시설 IR/F-N·독립 물리검증을 승격하지 않는다. 실제 provider 사고 packet·주요 사고 범위·시설 IR/F-N·독립 물리검증 gate는 그대로 차단된다. 결과는 `results/20261014/ijhe_completion_audit_live_with_diagnostic_facility_risk.json`과 상태 장부에 기록했다. 모든 실행·packet 증거 검사는 `diagnostic_only=true`이고, 유효하지 않은 exact-match나 빈도 연결이 들어오면 해당 검사만 `BLOCKED`로 표시한다. 세부 스캔 기준과 행별 결과는 [worklist packet 증거 감사 기록](PRISM_worklist_패킷증거감사_20261015.md)에 기록했다.

같은 adapter 종류를 여러 실제 설비에 연결할 수 있도록 `instance_id` registry도 추가했다. 이 registry는 탱크·배관·밸브별 provider 객체를 분리하고 실행 감사에 물리 설비 ID를 남긴다. 두 인스턴스 분리·중복·종류 불일치 검사를 포함한 portable suite는 394개가 통과했다. registry는 연결 계약을 넓혔지만 qualified 사고 packet을 생성하거나 빈도를 추정하지 않는다.

## 2026-10-14 외부 LayeredTank 공통 실행기 smoke

`scripts/run_diagnostic_adapter_runner_smoke.py`는 외부 `lh2dt` LayeredTank 모델을 host가 명시한 생성자 인자로 만들고, `DiagnosticAdapterRunner.register_provider_from_config()`와 `execute(..., release_kind="liquid")`로 실제 provider 인스턴스를 한 번 호출한다. 기본 진단은 합성 `1e-6 m²` 개구, `0.05 s` 간격, 양수 재고 임계값 종료를 사용한다. strict packet은 `0.1 s` 방출, 질량 잔차 `0 kg`, 엔탈피 잔차 약 `-4.44e-16 J`를 반환했고 새 physics 호출 시간은 약 `1556 ms`였다.

이 결과는 **실제 외부 adapter 인스턴스가 공통 실행기와 strict 액체 packet 경계를 통과했다는 증거**다. packet의 evidence status는 `synthetic_diagnostic`이고 `provider_packet_promoted=false`, qualified packet 수는 0이다. 따라서 현장 설비 형상·재고·사고빈도·시설 IR/F-N·독립 물리검증·1 Hz 실시간 계산을 주장하지 않는다. 재현 결과는 `examples/diagnostic_adapter_runner_layered_tank_smoke.json`, 실행 스크립트는 `scripts/run_diagnostic_adapter_runner_smoke.py`에 보존했다.

같은 runner를 저장탱크 worklist의 `AREA_0.01%` 항목에도 적용했다. `provider_instance_id=storage-tank-01`을 명시하고 event/component/port/opening 네 필드를 exact-match한 뒤 strict release를 consequence context와 synthetic final chain에 전달했다. chain은 `END_TO_END_DIAGNOSTIC_EXECUTED`로 종료되었고 약 11.22초, 질량 잔차 약 `-9.92×10⁻¹⁸ kg`였다. `worklist_frequency_bound=false`를 유지했으며 pool 반경 0.005 m는 선언 sensitivity 값이다. 이는 설비별 worklist→provider→방출→피해 연결을 확인한 것이고, qualified provider packet·문헌 빈도·시설 전체 위험을 완성한 증거는 아니다. 결과는 `examples/diagnostic_adapter_runner_worklist_storage_001.json`과 `results/20261014/diagnostic_adapter_runner_worklist_storage_001_consequence_chain`이다.

## 2026-10-15 packet과 시설 campaign의 구조 결합 감사

packet 증거가 시설 위험 계산 장부까지 이어지는지 확인하기 위해 `src/lh2_tno/diagnostic_campaign_binding.py`와 `scripts/audit_diagnostic_campaign_binding.py`를 추가했다. 24개 exact/strict worklist 사건의 ID를 campaign event·case·risk atom 장부와 대조한 결과, event 24/24, case 24/24, risk atom 24/24 사건 단위 match가 확인됐다. campaign에는 risk atom이 사건마다 4개씩 있어 총 96개이며, component ID는 24/24, 개구 직경을 선언한 사건은 21/21이 일치한다. relief와 재고기반 사고 3개는 개구 직경 자체가 없는 사고형식이므로 별도 미검사 수로 기록한다.

이 감사는 현재 campaign이 worklist 사건을 구조적으로 인식한다는 점을 증명하지만, 외부 packet 시간 이력을 실제로 사용했다는 뜻은 아니다. campaign event/case에 `provider_source_digest`·`provider_result_digest`가 저장되지 않았으므로 `packet_identity_consumed=false`이고, 빈도도 provider packet에서 추정하지 않고 문헌 `FrequencyPlan`에서만 적용된다. 따라서 결과 상태는 `PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING`, qualified provider packet은 0개, 시설 total IR/F-N과 물리검증은 계속 보류한다.

최신 portable suite는 402개가 통과했고, IJHE live audit는 18개 검사 중 7개 차단이다. `scripts/rebind_campaign_to_worklist_packets.py`로 evidence 스캔의 exact/strict 선택 packet을 다시 campaign 요청에 연결한 뒤, 24/24 provider source/result digest 쌍이 일치하는 것을 확인했다. 재실행은 4건 `EXECUTED`, 19건 `EXECUTED_OPERATOR_LIMITED`, 1건 `FAILED`로 남았고, `ambient-vaporizer/G1`은 고속 출구가 현재 저마하 확산 어댑터 범위를 넘어 `compressible/underexpanded plane adapter required`로 보류됐다. 따라서 packet identity는 `true`지만 structural binding은 23/24 risk-atom 결과만 생성해 `BLOCKED_DIAGNOSTIC_CAMPAIGN_BINDING`으로 기록한다. 이 결과는 packet을 정확히 소비했다는 증거이지, 모든 방출의 피해 계산·provider 적격성·빈도·시설 전체 IR/F-N을 충족했다는 뜻이 아니다. 실행 결과는 `results/20261015/generic_mixed_provider_campaign_worklist_rebound_result.json`, 결합 감사는 `results/20261015/generic_lh2_diagnostic_campaign_binding_worklist_rebound.json`, 최신 감사는 `results/20261015/ijhe_completion_audit_live_worklist_rebound.json`이다. 외부 설비 native accident export와 독립 물리검증도 별도로 확보해야 한다.

고속 기체 경로를 임의로 저마하로 낮추지 않기 위해 `ResolvedGasRelease.compressible_plane_handoff` 경계를 추가했다. provider가 downstream carrier plane의 위치·방향·열역학·단면·시간별 수소 질량분율을 제공하고 질량유량과 닫을 때만 SLABx near-field로 넘긴다. 합성 handoff smoke는 `END_TO_END_DIAGNOSTIC_EXECUTED`와 19개 상태 소비를 확인했지만 실제 provider export가 아니므로 IJHE 검증이나 시설 위험 승격에는 사용하지 않는다. 이 경계는 현재 G1 실패를 숨기지 않으면서 다음 실험에서 필요한 측정·export 자료를 구체화한다.
packet 판정 CLI도 추가했다. 선택된 vaporizer G1 packet은 고속 plane handoff가 없어 `COMPRESSIBLE_PLANE_HANDOFF_BLOCKED`이며, 별도로 보관된 저마하 진단 packet은 `DIRECT_LOW_MACH_GAS_EXIT_VALIDATED`와 최대 Mach `0.243589`를 보인다. 두 파일을 자동으로 섞지 않는 것이 packet identity와 피해 계산 범위를 보존하는 핵심이다.
## 2026-10-16 고속 출구 연결 작업

고속 `ambient-vaporizer/G1`을 임의로 저마하 packet으로 바꾸지 않기 위해 외부 handoff 부착 경계를 추가했다. `src/lh2_tno/compressible_handoff.py`와 `scripts/attach_compressible_plane_handoff.py`는 `prism.compressible_plane_handoff.v1`의 event/component/port 및 upstream source/result digest를 exact-match하고, 모든 provider interval의 수소 질량 장부를 `ResolvedGasRelease`로 재검증한다. 19개 interval synthetic smoke가 부착·검증되었지만 provider export·독립 물리검증·시설 QRA로 승격하지 않았다. 선택된 G1의 실제 상태는 여전히 provider handoff 부재로 `COMPRESSIBLE_PLANE_HANDOFF_BLOCKED`다. 전체 portable suite는 405개 통과했다. 계약과 필요한 외부 입력은 [압축성 근접장 handoff 계약](PRISM_압축성근접장_handoff_계약_20261016.md)에 기록했다.

## 2026-10-18 최신 연결 상태

외부 `lh2dt_models`의 일곱 설비 클래스가 native `export_accident_history(request)` 경계를 제공하도록 구현되었고, 외부 회귀시험 375건과 PRISM portable suite 447건을 통과했다. 이 사실은 사고 방출 계약이 있다는 뜻이며, 실제 적격 provider packet이나 시설 전체 QRA가 완료됐다는 뜻은 아니다.

저장탱크에 대해서는 `scripts/run_lh2dt_native_frequency_case.py`로 문헌 `LH2_VESSEL AREA_0.01%` 빈도와 native `LayeredTank` 방출을 한 사건에서 결합했다. 개구 `0.0127 m` exact-match, provider 질량 잔차 0 kg, native export 약 0.29 s, consequence campaign 약 23.8 s, 사건 상태 `EXECUTED_OPERATOR_LIMITED`를 기록했다. 빈도는 packet에서 추정하지 않고 기존 문헌 catalogue에서 읽었다. 결과는 `results/20261018/native_lh2dt_frequency_case/verification.json`이다.

현재 IJHE 완료 감사는 `INCOMPLETE_EVIDENCE`이며 23개 검사 중 차단 이유는 세 가지다. 합성/스크리닝 provider 외에 적격 packet이 없고, 선언한 주요 사고가족 중 부분·미계산 항목이 있으며, 그 때문에 시설 IR/F-N 총값을 보류한다. 이 native frequency case는 첫 번째 연결을 강화하지만 이 세 차단 이유를 해소하지 않는다.

감사기에 `--native-full-bore-result examples/native_lh2dt_dynamic_pipe_full_bore_case_verification.json`을 주면 23번째 진단 검사 `diagnostic_native_full_bore_chain`이 추가된다. 이 검사는 `model_pressure_equalization`, 최종 압력, provider 질량 잔차, consequence chain 실행을 확인하고, 빈도·시설 QRA·물리검증 승격은 명시적으로 거부한다. 최신 기록은 `results/20261018/ijhe_completion_audit_with_full_bore.json`이며 이 검사는 PASS 진단 전용이고 전체 차단 이유 수는 세 가지로 유지된다.

이번 단계에서는 `--native-full-bore-frequency-result examples/native_lh2dt_dynamic_pipe_full_bore_frequency_case_verification.json`도 추가했다. 새 검사 `diagnostic_native_full_bore_frequency_binding`은 native full-bore packet과 `LH2_PIPE AREA_100%` 문헌 사건 ID, `0.025 m` opening, 연간 빈도 `1.9×10⁻⁷ year⁻¹`, 자연 종료 및 피해 chain을 exact-match한다. 최신 감사는 `results/20261018/ijhe_completion_audit_with_full_bore_frequency.json`의 24개 검사 중 이 결합을 진단 전용 PASS로 기록한다. 적격 provider packet 부재, 부분·미계산 사고 범위, 시설 IR/F-N 보류라는 세 차단 이유는 그대로 유지한다.

`native_lh2dt_dynamic_pipe_full_bore_facility_frequency_case_verification.json`은 같은 사건을 시설 campaign 장부까지 보낸 결과다. 5개 배관 opening bin 중 `AREA_100%`만 실행되어 1개 case·4개 `UNCOMPUTED` case와 4개 risk atom이 기록된다. 조건부 장부가 존재해도 전체 시설 IR/F-N은 `facility_total_risk_available=false`로 보류한다.

## 2026-10-18 native DynamicHEMPipe 2상 연결

배관 경계도 같은 방식으로 확인했다. 외부 `DynamicHEMPipe` native export는 명시적 액체·2상 초기 품질을 받고 대기 flash의 기체/지상 액체 분할과 질량·엔탈피 장부를 반환한다. `LH2_PIPE AREA_0.01%` 개구와 문헌 빈도를 한 정확한 사건에 결합한 결과는 `PARTIAL_DECLARED_SCOPE`이며, 2상 packet은 strict adapter와 SLABx-LH2 consequence chain까지 소비됐다. 다른 opening bin과 나머지 설비는 명시적 미계산/제외로 남겼다. airborne liquid, 전량 방출, 현장 위치별 빈도, 물리검증을 추가하지 않았으므로 이 연결도 시설 전체 위험도 완료를 의미하지 않는다.

## 2026-10-18 검사센터 시계열 상태 감사

검사센터의 인수·벤트·공급 및 원본 학습 XLSX 17개, 78개 sheet를 `scripts/audit_inspection_center_timeseries.py`로 읽어 파일 해시, 헤더, 행 수, 신호 접두어, 집계 범위를 기록했다. `PT`·`DPT`·`TT` 후보는 발견했지만 파일 헤더만으로 공학 단위를 확정할 수 없으므로 실제 숫자값이 있는 522개 후보 수치 열을 `MISSING_OR_UNCONFIRMED`로 남겼다. 이 감사는 일반 LH2 시설에서 재사용할 수 있는 입력 준비도 검사이며 센터의 태그나 수치를 일반 설비 기본값으로 복사하지 않는다.

따라서 검사센터 시계열은 현재 `state_snapshot_binding_allowed=false`, `frequency_applied=false`, `sensor_frequency_learning_used=false`, `provider_packet_created=false`, `facility_qra_claim=false`다. exact tag-to-unit map, 압력 기준·온도 기준·유량 기준, 보정·결측·시각 품질, 설비·포트 대응표와 별도의 상태 adapter 검증이 끝나야 실시간 사고 초기조건으로 연결할 수 있다. 자세한 절차와 제한은 [검사센터 시계열 상태 감사](PRISM_검사센터_시계열상태감사_20261018.md)에 기록했다.

## 2026-10-18 네이티브 패킷 장부

설비별 외부 모델 결과를 다시 확인할 수 있도록 `src/lh2_tno/native_packet_coverage.py`와 `scripts/build_native_lh2dt_packet_coverage_ledger.py`를 추가했다. 장부 `examples/native_lh2dt_packet_coverage_ledger.json`은 저장된 네이티브 사고 패킷 25건, 선언된 작업목록과 정확히 맞는 사건 24건, 피해영향 체인까지 연결된 사건 18건, 문헌 빈도가 연결된 진단 1건을 기록한다. 행마다 개구·방출시간·종료 근거·질량잔차·체인 경로를 보존하며, 승격·빈도 추론·시설 QRA·물리검증 플래그는 모두 닫혀 있다.

`build_ijhe_completion_audit.py --native-packet-coverage-ledger`를 사용하면 이 장부의 일관성을 별도 진단검사로 확인할 수 있다. 최신 감사는 `results/20261018/ijhe_completion_audit_with_native_packet_coverage.json`에 25개 검사를 기록하며 상태는 여전히 `INCOMPLETE_EVIDENCE`, 차단 이유는 3개다. 이 단계가 추가한 것은 방출 패킷의 설비별 추적성이고, 현장용 provider 적격성·미계산 사고의 실행·시설 전체 IR/F-N을 닫은 것은 아니다. 장부의 읽는 법과 현재 행별 범위는 [네이티브 LH2DT 사고 패킷 장부](PRISM_네이티브_LH2DT_사고패킷_장부_20261018.md)에 정리했다.

## 2026-10-19 native packet 시설 campaign 소비

`rebind_campaign_to_worklist_packets.py`로 24개 작업목록 사건의 요청을 저장된 strict native packet으로 다시 만들고, `run_lh2_mixed_provider_campaign.py`로 시설 campaign을 재실행했다. `examples/native_lh2dt_packet_campaign_execution_ledger.json`은 24/24 packet identity와 source/result digest 소비, 23개 체인 실행, 19개 운전자 제한, 1개 명시적 실패를 기록한다. 실패 사건은 `ambient-vaporizer/G1`이며 압축성·underexpanded plane handoff가 없어 실패했다. 이 결과는 방출 packet이 시설 계산 요청에 실제로 들어갔다는 증거지만, 실패·운전자 제한·합성 경계를 보존하므로 시설 전체 IR/F-N이나 provider 적격성으로 승격하지 않는다.

## 2026-10-19 G1 압축성 handoff의 시설 campaign 재결합

G1의 실패를 숨기기 위해 저마하 packet을 바꾸어 넣지 않고, source/throat 상태에서 생성된 별도 `resolved_release_with_handoff.json`을 명시적으로 재결합했다. `rebind_campaign_to_compressible_handoff.py`는 event ID, component ID, port ID, provider source digest를 기존 packet과 exact-match한 경우에만 요청을 다시 만든다. provider result digest가 달라진 사실과 handoff provenance는 `results/20261019/generic_native_packet_rebound_campaign_g1_handoff.provenance.json`에 남긴다.

최종 24개 사건 실행은 `4 EXECUTED + 20 EXECUTED_OPERATOR_LIMITED + 0 FAILED`, 96 risk atom, facility total IR/F-N `null`이었다. G1은 `EXECUTED_OPERATOR_LIMITED`로 chain에 들어갔지만 handoff provenance가 `not independently validated`인 진단용 plane adapter이므로 provider 적격성·고속 근접장 물리 검증·시설 위험 승격은 하지 않는다. 같은 결과를 시설 ledger로 합산하면 조건부 진단 IR/F-N 경계가 생성되지만 `facility_total_risk_available=false`이다. 최신 IJHE 감사 `results/20261019/ijhe_completion_audit_with_native_packet_campaign_g1_handoff.json`은 27개 검사를 수행하고 기존 3개 차단 이유를 그대로 유지한다. 즉 방출→피해 연결의 계산 경로는 24개 case에서 닫혔지만, 논문에서 전체 시설 QRA라고 부를 수 있는 증거가 된 것은 아니다.

최신 감사는 `results/20261019/ijhe_completion_audit_with_native_packet_campaign.json`의 26개 검사 중 새 `diagnostic_native_packet_campaign_execution`을 PASS 진단 전용으로 기록한다. 차단 이유는 적격 현장 packet 부재, 일부 사고군의 불완전성, 시설 IR/F-N 보류라는 3개가 그대로 남는다. 상세 재현 절차는 [네이티브 packet 시설 campaign 감사](PRISM_네이티브패킷_시설캠페인_감사_20261019.md)에 있다.

## 2026-10-19 공통 시설 namespace에서 vertical handoff 결합

별도 `vertical-vent-campaign`의 수직 방출 결과를 공통 시설에 넣을 때 시설 ID만 바꾸면 event·provider packet·설비·수용점이 서로 다른 장부로 남는다. 그래서 `vertical_handoff_campaign.py`가 event ID, provider packet ID, asset/component ID, facility ID를 함께 rebind하고 provenance를 남긴다. 원래 네 수용점은 현재 generic campaign의 `worker-01`에 명시적으로 매핑했으며, 충돌 시 endpoint maximum만 취하는 진단 규칙을 적용했다. 이는 현장 인구·좌표를 만든 것이 아니므로 물리검증이나 QRA 승격을 하지 않는다.

결합한 시설 평가 `results/20261019/native_campaign_with_vertical_handoff_facility_assessment.json`은 generic 24개와 vertical 5개를 합쳐 29개 event, 34개 case, 104개 risk atom을 보며, 5개 문헌 빈도 시나리오에서 vertical event의 선언 진단 빈도를 고정해 재가중한다. vertical handoff는 2개 실행 case와 10개 미계산 case를 가진 `PARTIAL`로 남는다. 따라서 최신 IJHE 감사는 여전히 `INCOMPLETE_EVIDENCE` 27개 검사·3개 blocker이며, 조건부 진단 IR/F-N만 노출하고 시설 전체 IR/F-N·credible interval·qualified provider·물리검증은 보류한다. 상세 수치는 [`vertical handoff 시설 평가 요약`](../examples/native_lh2dt_packet_campaign_vertical_handoff_facility_assessment_summary.json)과 [`시설 campaign 감사`](PRISM_네이티브패킷_시설캠페인_감사_20261019.md)를 사용한다.

## 2026-10-19 two-sided rupture와 공통 사고범위 장부

두 종단 provider-set campaign을 공통 시설 namespace에 결합했다. `rebind_campaign_namespace.py`는 원본 시설·asset·component ID를 exact-match하고 event ID와 risk atom 수용점을 함께 바꾼다. 결과는 2개 endpoint event, 4개 실행 operator-limited case row, 6개 uncomputed row, 16개 risk atom이다. 네 harm atom은 `worker-01`에 비영 피해를 가지며, 조건부 진단 시설 IR/F-N은 [1.0×10^-7, 1.0×10^-7] / year와 1명 F-N 수준을 표시한다. 이 값은 합성 two-sided geometry와 명시적 many-to-one receptor maximum의 결과라서 물리검증·시설 QRA로 승격하지 않는다.

generic, vertical, two-sided 세 matrix를 `scope_matrix_merge.py`로 병합해 최신 범위 장부를 `results/20261019/generic_vertical_two_sided_merged_scope_matrix.json`에 만들었다. `vertical_handoff`와 `two_sided_rupture`는 이제 모두 `PARTIAL`로 표시되고, `NO_EVENT_GENERATED`가 숨겨지지 않는다. 최신 평가 `results/20261019/native_campaign_with_vertical_handoff_two_sided_facility_assessment.json`은 31개 event, 40개 case, 120개 atom을 집계하지만 22개 operator-limited와 5개 명시적 uncomputed case, 부분 사고 family, synthetic provider가 남아 전체 시설 IR/F-N을 `null`로 유지한다.

2026-10-20에는 vertical handoff의 대표 면적 하나만 계산하던 경로를 확장했다. `scripts/validate_vertical_vent.py --all-area-bins`는 `AREA_0.01%`, `0.1%`, `1%`, `10%`, `100%`를 각기 다른 provider opening으로 계산하고 두 기상 조건에 연결한다. 그 결과 `results/20261020/vertical_vent_all_bins/verification.json`은 5개 generated event, 10개 executed case, provider handoff 소비, 최대 질량잔차 0 kg을 기록한다. 전체 시설 원장에 다시 결합한 `results/20261020/native_campaign_with_vertical_all_bins_two_sided_inventory_isolation_facility_ledger.json`은 41개 event, 70개 case, 272개 risk atom을 보존한다. 병합 원장은 신선 물리 계산 68건과 case p95 약 45.9 s, p99 약 49.2 s를 기록하지만, 이는 별도 설비 campaign을 합산한 진단 측정이며 1 Hz 서비스 보장이 아니다. provider handoff의 독립 검증과 나머지 부분 사고범위가 남아 있으므로 시설 전체 IR/F-N은 계속 보류한다. 상세 기록은 [vertical 모든 개구면적 연결](PRISM_수직벤트_모든개구면적_연결_개발기록_20261020.md)에서 확인한다.

## 2026-10-19 재고 소진 설비를 포함한 네 번째 시설 campaign

이번 단계에서 기존 generic campaign, vertical handoff, two-sided rupture에 독립적으로 실행된 inventory-depletion campaign을 하나의 시설 평가로 연결했다. 네 campaign은 서로 다른 물리 범위를 같은 사건으로 합치지 않도록 namespace와 component ID를 분리한다. 재고 소진 설비는 `inventory-depletion-pipe-01`이며 5개 event, 10개 실행 case, 0개 미계산 case, 40개 risk atom을 갖는다. 각 case의 종료는 provider의 positive-mass depletion threshold다.

문헌 빈도 시나리오도 다섯 개 asset/event 시나리오에 재고 소진 설비를 명시적으로 포함했다. 중앙·p05·p95·independent event 시나리오에서 선언된 진단 빈도만 재가중하며, provider packet에서 빈도를 추론하지 않는다. 시설 credible interval과 최종 IR/F-N 승격은 여전히 범위 완결성과 물리검증 이후의 단계다.

최신 평가 결과는 36개 event, 50개 case, 37개 미계산 case, 160개 risk atom, 10개 component다. `inventory-depletion-pipe-01`은 coverage 회계 보완 후 `EXECUTED`로 보이지만 전체 시설 상태는 `PARTIAL_FACILITY_SCOPE`다. IJHE 감사는 27개 검사와 3개 blocker를 유지한다. 따라서 이번 추가는 설비 상태→재고 소진 방출→피해 chain의 연결을 강화한 것이며, 전체 시설 QRA가 끝났다는 의미는 아니다.

## 2026-10-19 차단 성공·실패 경로를 시설 장부에 추가

차단 성공과 차단 실패가 같은 사건에서 서로 다른 종료시간을 만드는 문제를 별도 campaign으로 검증했다. `equipment_isolation_campaign`의 다섯 배관 개구를 `isolation-diagnostic-pipe-01`로 rebind하고, 10개 성공 case와 10개 실패 case를 각각 보존했다. 성공은 0.25초 차단 후 유량 0을 provider가 확인한 `reviewed_isolation_success`, 실패는 0.5초 동안 열린 상태를 유지한 `synthetic_diagnostic_horizon`이다.

이 결과를 generic·vertical handoff·two-sided rupture·inventory depletion과 함께 합치면 41개 event, 70개 case, 240개 risk atom, 11개 component가 된다. 빈도는 기존 문헌 pipe rate를 명시적으로 고정하며, 이 추가 campaign에서 빈도를 학습하거나 새로 추정하지 않는다. 실패 horizon과 synthetic 입력은 계속 제한으로 표시되므로 전체 시설 IR/F-N은 보류한다.

## 2026-10-19 미완료 증거 요청을 자동화

부분 시설 평가의 다음 입력을 명확히 하기 위해 `facility_evidence_request.py`와 CLI를 추가했다. 사고범위에 설비가 실제로 없다고 판정된 `NOT_APPLICABLE` 사고 family는 범위 기록만 남기고 provider 증거 요청에서 제외하며, 실제 설비가 있는 family의 누락·미계산은 계속 요청·차단한다. 최신 assessment와 5개 source matrix를 병합한 사고범위 matrix를 넣으면 12개 사고군·11개 component별로 필요한 실제 provider 근거를 나열한다. 요구사항은 exact event/component/port/opening, 방출 시간 이력과 종료 basis, 차단 및 재고 소진, 질량·에너지 폐합, `prism.external_accident_history.v1` schema, 독립 물리검증이다.

요청서의 상태는 `OPEN_EVIDENCE_REQUEST`이며 문헌 빈도는 복사하지 않고, 센서나 provider packet에서 빈도를 학습하지 않는다. 따라서 이 자동화는 다음 실증 데이터의 입구를 만든 것이고 시설 total IR/F-N을 조기 승격하는 기능이 아니다. 현재 생성된 요약은 [`facility_evidence_request_summary.json`](../examples/facility_evidence_request_summary.json)이다.

## 2026-10-19 provider packet·물리검증 승격 게이트

실제 설비 모델의 사고 이력이 들어오는 다음 단계를 위해 `campaign.py`에 `prism.provider_packet_evidence.v1` 계약을 추가했다. 이 레코드는 event/component/port와 provider source/result digest, qualification evidence ID를 함께 보유한다. 캠페인이 소비한 packet identity와 이 값들이 exact-match일 때만 `qualified_provider_packet_case_count`를 증가시키며, 이 과정에서 문헌 빈도는 읽기 전용으로 유지된다.

또한 `physical_validation_evidence`를 `not_validated`/`independent_validated`로 분리했다. 완전한 시설 범위, 모든 실행 case의 qualified packet, 독립 물리검증 근거가 모두 있을 때만 `complete_facility_qra_claim`을 열 수 있다. 기존 수치 합산 장부의 `facility_total_risk_available`와 별도로 자격 상태를 보고하므로, 구조 연결·합성 진단 결과를 실제 시설 QRA로 오인하지 않는다. 현재 결과에는 qualified packet이 없고 물리검증 상태도 제한적이어서 승격 게이트는 닫혀 있다. 관련 portable suite는 470개 테스트가 통과했다.

문헌 빈도 불확실성 함수도 이 상태를 각 시나리오와 최상위 결과에 전달한다. p05·published·p95 재가중 또는 lognormal 샘플링이 실행되어도 provider packet 적격성, 독립 물리검증, 완전 시설 QRA 상태는 별도 gate로 남는다.

새 gate 적용 후 기존 5개 disjoint campaign을 재집계한 결과는 `results/20261019/native_campaign_with_vertical_handoff_two_sided_inventory_isolation_provider_gate_assessment.json`에 보관했다. 41개 event, 70개 case, 37개 미계산 case, 240개 risk atom이며 provider packet case와 qualified packet case는 모두 0이다. 이 재집계는 새 물리 계산이 아니라 저장된 risk atom의 시설 회계·빈도 불확실성 결과를 갱신한 것이다.

최신 all-bin 재실행에서는 vertical campaign의 40개 risk atom을 포함해 총 272개 risk atom을 다시 집계했다. `results/20261020/ijhe_completion_audit_all_bins.json`은 27개 검사를 수행하고, 빈도 불확실성·처리시간·vertical handoff 진단은 통과시킨다. 현재 남은 차단은 부분 사고범위와 시설 IR/F-N 보류 두 가지다. 이 감사의 `INCOMPLETE_EVIDENCE` 상태는 계산 실패가 아니라, qualified provider packet·독립검증·모든 주요 사고군의 완전한 범위가 아직 없다는 뜻이다.

시설 평가기는 이미 병합된 `prism.facility_risk_ledger.v1`를 다시 campaign으로 취급하지 않도록 보완했다. 그 결과 evidence request가 설비 coverage를 모두 누락으로 표시하지 않고, 11개 component를 `EXECUTED` 3개·`PARTIAL` 8개·`EXCLUDED` 1개로 보존한다. 외부 패킷 감사기와 두 개의 회귀시험을 추가한 현재 portable 검사는 **494개 통과**이며, IJHE 감사의 차단 두 항목은 그대로 유지된다.

이 assessment를 완료 감사기에 다시 넣은 결과도 `examples/ijhe_completion_audit_provider_gate_summary.json`에 보관했다. 15개 검사, 4개 blocker이며 방출→피해 chain·문헌 빈도 불확실성·지속시간/차단/재고 장부·처리시간 계약은 통과한다. 실제 사고 provider packet, 전체 사고범위, 시설 IR/F-N은 여전히 `BLOCKED`다.

## 2026-10-19 파일 기반 provider packet 입구

실제 외부 설비 모델이 저장한 `prism.resolved_release.v1` 또는 양단 파열용 `prism.resolved_release_set.v1` 파일과 별도 `prism.provider_qualification_evidence.v1` sidecar를 받으면, `scripts/build_provider_packet_evidence.py`가 두 파일을 strict 검증하고 `prism.provider_packet_evidence.v1`를 만든다. event/component/port와 source/result SHA-256이 정확히 일치해야 하며, `input_origin=synthetic` packet은 거부한다. 이 변환기는 문헌 initiating frequency를 만들거나 바꾸지 않는다.

예시는 다음과 같다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_provider_packet_evidence.py `
  --release actual_resolved_release.json `
  --qualification provider_qualification.json `
  --output provider_packet_evidence.json
```

생성된 evidence catalog를 `scripts/build_equipment_campaign.py --provider-evidence-catalog provider_packet_evidence.json`으로 컴파일된 campaign에 붙일 수 있다. 독립 물리검증 기록은 `--physical-validation-evidence validation.json`으로 별도 연결하며, `independent_validated`에는 evidence ID와 SHA-256이 모두 필요하다. `scripts/audit_provider_catalog_coverage.py --provider-evidence-catalog provider_packet_evidence.json`은 worklist 구조 exact-match와 qualification exact-match를 별도 집계하고, 합성 packet을 qualified로 세지 않는다. 그 coverage JSON을 완료 감사기의 `--provider-qualification-coverage`로 전달하면 자격 검증된 packet 수와 전체 worklist 충족 여부가 `actual_provider_release_packet`·`provider_worklist_coverage` 검사에 반영된다. evidence에 없는 사건은 자동 대체하지 않고 미계산·미자격으로 유지한다. 현재 저장된 검사·진단 자료에는 이 sidecar를 갖춘 실제 packet과 독립 검증 기록이 없으므로 `qualified_provider_packet_case_count=0`과 시설 QRA 보류 상태는 유지된다. 새 경로는 실제 자료가 들어왔을 때 수동 재조립 없이 같은 승격 규칙을 적용하기 위한 입구다.

시설 평가 자체에도 같은 coverage를 `scripts/build_facility_assessment.py --provider-qualification-coverage coverage.json`으로 전달할 수 있다. 이 경우 시설 ledger의 실제 qualified packet 수와 coverage의 `qualified_provider_packet_count`를 대조하고, 전체 worklist 자격·미자격 exact-match·count 불일치를 `provider_qualification_coverage`에 남긴다. 이 대조는 qualified packet이나 물리검증을 새로 만들지 않으며, 두 보고서가 일치할 때만 coverage gate를 완전하다고 표시한다.

## 2026-10-20 검사센터 자료와 외부 패킷 재감사

검사센터 CSV 3개를 현재 원본에서 재수입한 결과는 52개 후보 행이며, 41개가 일반 실외 범위 후보이고 11개가 선언 범위 밖이다. 이 자료는 `pipe_hole`, `valve_hole`, `vessel_hole`, `vaporizer_hole`, `vent_hole`, `vertical_handoff`, `inventory_over_600s`의 후보와 압력·유량·밸브·검지·온도·벤트 신호를 제공한다. 사고빈도·provider 방출 packet·종료시간·질량·에너지 폐합은 제공하지 않으므로 일반 시설 위험 계산에 직접 연결하지 않고 [`검사센터·외부 패킷 재감사 기록`](PRISM_검사센터_외부패킷_재감사_20261020.md)으로 보존한다.

별도 외부 디지털트윈 출력 아카이브의 JSON 84개도 자동 검사했다. provider response 2개와 verification 12개는 확인됐지만 `prism.provider_qualification_evidence.v1`는 0개, 독립 물리검증 주장은 0개, 완전 시설 QRA 주장은 0개였다. 따라서 현재 자료는 `EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY`이며, 방출 계산이 실행됐다는 이유만으로 빈도·provider 적격성·시설 IR/F-N을 승격하지 않는다. 이 감사기와 요약은 `scripts/audit_provider_artifacts.py`, [`provider_artifact_audit_external_summary.json`](../examples/provider_artifact_audit_external_summary.json)에 있다.

## 2026-10-20 transfer-line 설비 경계 교체 결합

generic 시설의 `liquid-transfer-line-01` 다섯 개 개구면적을 설비 provider 경계와 직접 연결했다. `scripts/validate_equipment_campaign.py --all-area-bins`는 다섯 개 provider 방출 event를 만들고 각 event를 두 기상 조건에 연결해 10개 case를 실행한다. `--component-id liquid-transfer-line-01`과 공통 수용점 ID를 사용해 기존 시설 장부와 결합 가능한 결과를 만든다. 이때 빈도는 문헌 catalogue에서만 오며 provider·센서에서 추정하지 않는다.

기존 generic transfer-line event를 중복해서 더하지 않도록 `generic_campaign_without_transfer_line_for_replacement.json`을 파생 입력으로 만들고, 그 자리를 설비 campaign으로 교체했다. 최신 결합 ledger `results/20261020/native_campaign_with_transfer_line_replacement_vertical_all_bins_two_sided_inventory_isolation_facility_ledger.json`은 41개 event, 75개 case, 280개 risk atom, 32개 미계산 case를 기록한다. 이전 all-bin 장부의 37개 미계산 case에서 5개가 줄었고 `liquid-transfer-line-01`은 `EXECUTED`가 됐다. 탱크·펌프·밸브·양단파열·수직 handoff의 미계산·operator-limited 범위는 그대로 차단된다.

새 빈도 시나리오는 `examples/native_lh2_transfer_line_replacement_frequency_scenarios.json`에 있으며 시설 assessment와 조건부 IR/F-N을 다시 계산한다. `results/20261020/ijhe_completion_audit_transfer_line_replacement.json`은 27개 검사를 수행하고, 실제 qualified provider packet 부재, 부분 주요 사고범위, 시설 전체 IR/F-N 보류의 세 차단을 유지한다. 상세 연결 규칙과 재현 명령은 [설비 상태·배관 개구면적 시설 결합 기록](PRISM_설비상태_배관개구면적_시설결합_개발기록_20261020.md)을 따른다.

## 2026-10-22 현재 감사 기준점

최신 밸브 보완 시설 원장은 `results/20261022/native_campaign_with_repaired_valve_transfer_line_replacement_vertical_all_bins_two_sided_inventory_isolation_facility_ledger.json`에 있다. 41개 사건, 80개 case, 37개 미계산/보류 case, 312개 risk atom을 기록하며, 밸브 다섯 면적 구간과 두 기상 조건의 10개 case는 모두 `EXECUTED_OPERATOR_LIMITED`로 끝났다. 이 수치는 방출부터 피해까지 숫자를 계산했다는 뜻이지, 적격 provider·독립 검증·시설 전체 QRA를 의미하지 않는다.

최신 범위표는 조건부 수치 회계와 엄격한 시설 승격을 분리한다. 조건부 범위는 12개 선언 family 모두 `EXECUTED`이며 미계산 case가 0개다. 엄격한 범위는 9개 family가 `PARTIAL`로 남아 있다. `results/20261022/ijhe_completion_audit_repaired_valve_transfer_line_replacement.json`은 28개 검사 중 25개 통과·3개 차단이며, 새 `conditional_accident_scope_accounting`은 형식 검사를 통과한다. 남은 차단은 적격 provider 방출 packet 부재, 주요 사고 범위 미완결, 시설 IR/F-N 보류다. 전체 portable test suite는 496개 통과했다.
