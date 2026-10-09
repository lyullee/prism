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
- 382개 portable 검사, 자연 종료 실제 체인 1건, G1 finite-inventory liquid-jet operator-limited 사례 2건과 G3 사례 4건, steady equipment-resolved pipe campaign 2건, transient isolation success/failure pipe campaign 20건, 다섯 inventory-depletion LOC의 두 기상 조건 10건, 두 provider 출구를 결합한 양단 파열 campaign 2건, provider-resolved vertical handoff campaign 2건, provider-resolved liquid/two-phase exit의 pool·확산·피해 연결 1건, 문헌 빈도 분위수 재가중 검사를 확인했다. 현장 절대위험 검증·1 Hz 신규 계산·완전한 시설 feedback은 미완료다.
- DynamicLH2PoolX의 물/알루미늄 hold-out 반경 오차와 HSE 질량잔차를 해시 장부로 확인했지만, protocol snapshot 해시 drift가 있어 제한 구성요소 증거로만 사용한다. 설비 방출·대기확산·점화·IR/F-N 전체 체인의 물리 검증으로 확대하지 않는다.

## 단계별 작업과 통과 기준

| 단계 | 개발할 내용 | 완료 판정에 필요한 근거 |
|---|---|---|
| A. 설비 상태 | 탱크·배관·밸브·펌프·기화기·벤트의 실제 지원 모델/포트/상/에너지 기준 확인, 사고 위치와 연결, 유량 소유권 유지 | 지원표, 동일 물성·시계, 설비별 실제 계산 전달, 질량·정적/전체 에너지 장부의 구분, 미지원 설비 표시. `ResolvedLiquidRelease`로 provider flash/지면 분할 계약을 추가했지만 LayeredTank 실제 액체/2상 상태와 모든 설비 지원은 남아 있다. |
| B. 방출 경로 | 단일 구멍의 실제 종료, 차단 성공/실패, 재고 소진, 전량/600초·양단 파열·수직 벤트 전용 경로 | 통합 source의 압력 평형 자연 종료와 무연장 질량 장부, G1 SLABx-LH2 liquid-jet finite-inventory 질량 폐합, 5개 LH2 pipe area-bin 각각에 대한 합성 layered-tank/commanded-valve의 0.25초 isolation-success 및 0.5초 isolation-failure 진단 이력을 구현했다. 추가로 `ResolvedGasReleaseSet`·`equipment_two_sided_rupture`·`location_weight`를 구현해 TNO_PIPE full-bore 양단을 한 사건으로 두 번의 provider 경계에서 계산하고 Frechet 상한으로 결합했다. 이제 provider-resolved liquid/two-phase exit의 gas/ground partition과 pool/피해 연결 1건도 실행했다. barrier 확률은 합성값이고 재고 소진을 뜻하지 않는다. G1·양단·수직 handoff·liquid provider 경로는 provider 상호작용·액체/2상 feedback·실제 설비 입력의 물리 검증이 남아 있다. 수직 경로 자체는 handoff 계약과 synthetic campaign까지 구현했지만, 수직 제트 원거리 모델과 교차상호작용은 미완료다. |
| C. 시설 위험 | 모든 LOC의 경로 배정, 위치 배분, 연간 기상/인구와 점화·차단 분기, 기존 TNO IR/F-N 함수 연결 | 5개 LH2 pipe LOC의 사건 목록과 20개 물리 사례를 모두 실행하고, 조건부 확률 폐합, 빈도 1회 적용, 수용점별 IR, 개별 사건별 인구 피해/F-N을 확인했다. 합성 종료·장벽과 실제 설비 목록/위치가 없으므로 total은 보류 |
| D. 빈도 불확실성 | LH2 문헌 분포, 상관 가정별 비교, TNO 기본값의 명시적 민감도, 위험 기여/설비 순위 안정성 | 근거 없는 사전분포 금지, TNO/LH2 대안 중복 금지, 상관 가정과 미계산 범위 공개, 분포·민감도·복사율 구간 구분 |
| E. 검증·속도 | 보유 공정 자료·외부 실험 출처/분할, 관측 연산자와 독립 검증, 보존/수렴, 처리시간 | 학습/검증 누수 없음, 실측/복원/합성 구분, 적용범위별 오차, 하드웨어·신규/캐시 구분, 반복 p50/p95/p99와 실패 기록 |

600초 전량방출은 `inventory_over_600s` operator와 완전 provider 이력 계약을 구현했고, 합성 10 m³ 진단 1건에서 600초 end-to-end chain을 실행했다. 액체·2상 provider 출구는 `ResolvedLiquidRelease`로 한 건을 실행했으며, airborne liquid은 별도 adapter가 없으면 거절한다. 실제 LayeredTank 액체/2상 재고 입력·현장 검증·시설 전체 위험 연결은 아직 완료하지 않았다.

단계 C의 실행 회계는 A/B에서 아직 계산하지 못한 항목을 즉시 드러내므로 먼저 공통 실행기를 구현한다. 이것이 A/B의 실제 공정 결합이나 장시간 방출을 완료했다는 뜻은 아니다.

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

이 단계의 예제·명령·측정 결과는 별도 실행 기록에 정리한다. 이번 구현은 공개 0.6.0을 덮어쓰지 않은 개발 변경이며 새 PyPI/DOI 릴리스는 만들지 않았다.

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
  --output results/20261009/provider_release_full_chain_diagnostic/ijhe_completion_audit.json
```

현재 실제 합성 provider 경로의 판정은 `INCOMPLETE_EVIDENCE`다. 설비 모델은 `STATE_ONLY_BOUND`이고 사고 release export 0개이며, 실제 provider 사고 packet 부재, 사고 가족 미완결, 시설 IR/F-N 보류, 독립 전체 체인 물리검증 부재, 완전 시설 빈도 credible interval 부재가 차단 이유로 남는다. 이 감사기가 `READY_FOR_IJHE_SCOPE`를 내기 전에는 논문에서 전체 시설 QRA 완성으로 표현하지 않는다.

## 2026-10-12 VentStack 방출 경계 추가

외부 `VentStack.evaluate()`를 별도 사고 adapter로 호출하고, steady two-port 결과를 0.5 s·10 interval의 synthetic diagnostic gas history로 변환했다. 기본 102 kPa upstream·0.01 m bore에서 strict `ResolvedGasRelease` 질량 잔차 `0 kg`, 엔탈피 잔차 `0 J`를 얻었고, low-Mach gas packet을 최종 피해 chain까지 실행했다.

이 경계는 tank/PSV inventory, relief setpoint, field vent frequency를 제공하지 않는다. upstream 압력·bore가 커지면 compressible/underexpanded plane이 되어 현재 low-Mach scope gate에서 차단되며, 별도 compressible adapter 없이는 승격하지 않는다.

## 2026-10-12 DynamicHEMPipe 방출 경계 추가

외부 `DynamicHEMPipe`를 명시적 full-bore atmospheric outlet로 실행하는 PRISM 측 adapter를 추가했다. 유한체적 pipe 상태가 반환한 유량·엔탈피를 10개 왼쪽 유지 interval로 보존하고, `prism.resolved_release.v1` 액체/2상 packet의 질량·에너지 장부를 다시 적분했다. `0.001 s` 진단에서 질량 잔차는 `0 kg`, 에너지 잔차는 약 `-5.42e-20 J`였다.

이 packet은 잔류 pipe inventory를 보유한 고정 진단시계이며 전량 방출·현장 배관 파손 확률·차단 성공을 의미하지 않는다. `validate_lh2dt_prism_packet_chain.py`의 `radius_m=0.0001 m` 선언 sensitivity footprint를 사용해 최종 피해 체인까지 실행했지만, 이 footprint와 synthetic inlet/geometry는 현장 형상으로 승격하지 않는다.

## 2026-10-12 LayeredTank strict packet과 전체 chain

외부 `LayeredTankNetworkSimulator+CommandedValve`의 합성 양수 재고 threshold 이력을 `scripts/export_lh2dt_layered_tank_prism_packet.py`로 `prism.external_accident_history.v1`에 맞추고, 공통 strict adapter를 통해 `prism.resolved_release.v1` 액체 packet으로 변환했다. provider 16개 interval의 왼쪽 유지 시간, `inventory_depletion` 종료 basis, 누적 질량·엔탈피를 검사한 결과 8.0 s 방출, 질량 잔차 `1.73e-18 kg`, 에너지 잔차 `0 J`를 얻었다. `scripts/validate_lh2dt_prism_packet_chain.py`는 이 packet을 DynamicLH2PoolX, SLABx-LH2/SLABx, cloud, 점화, 화재·폭발 및 TNO 피해까지 실행했다.

이 실행은 선언된 `0.005 m` sensitivity pool footprint를 사용해 작은 합성 packet의 wet-cell 조건을 확인한 것이다. 외부 provider가 flash gas와 airborne liquid을 계산하지 않고, 설비 형상·개구·차단 신뢰도·현장 재고도 합성이므로 `EXECUTED_OPERATOR_LIMITED` 진단으로만 기록한다. provider packet 승격·빈도 부여·시설 IR/F-N·독립 물리검증은 계속 보류한다. 외부 `lh2dt` 각 클래스에 native 사고 export를 넣고 24개 사건과 exact-match하는 작업은 다음 단계다.

## 2026-10-11 연결 경계 보완

외부 설비 모델이 정상 상태만 계산하고 사고 이력을 내보내지 않는 문제를 명확히 분리하기 위해 `src/lh2_tno/equipment_accident_export.py`를 추가했다. `AccidentReleaseExportRequest`는 사고 포트·개구·관찰시계·provider 종료 소유권·원본 digest를 필수화하고, provider는 `export_accident_history(request)`와 `prism.external_accident_history.v1`를 제공해야 한다. `evaluate()`·`simulate()`·`advance()`만 있는 모델은 사고 packet으로 사용하지 않는다. 합성·스크리닝 결과는 strict packet 검증 뒤에도 `DIAGNOSTIC_PACKET_NOT_PROMOTED`로 남긴다.

현재 실제 `lh2dt_models` 클래스에는 이 전용 메서드가 없으므로 설비 매핑은 여전히 `STATE_ONLY_BOUND`, 실제 적격 packet은 0건이다. 2026-10-14부터 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기의 PRISM-side 진단 adapter 7건을 별도로 기록하지만, 이는 `synthetic_diagnostic` packet을 만드는 연결 시험이지 native provider export나 물리검증 완료가 아니다. 새 계약은 외부 모델이 구현될 때 사용할 PRISM 측 경계이며, 시설 IR/F-N·빈도·물리 검증 완료를 대신하지 않는다. 예시 요청은 `examples/equipment_accident_export_request.json`, 상세 규칙은 [외부 설비 사고방출 export 계약](PRISM_외부설비_사고방출_export_계약_20261011.md)에 기록했다. 새 계약 테스트를 포함한 portable suite는 382개이며, IJHE 자동 감사는 12개 검사 중 7개 차단 상태를 유지한다.

## 2026-10-14 진단 adapter의 IJHE 감사 연결

`build_ijhe_completion_audit.py`는 이제 `--diagnostic-adapter-registry`를 받을 수 있다. 이 ledger는 adapter 클래스가 catalog에서 해석되고 공통 `export_accident_history(request)` 메서드를 제공하는지만 검사한다. provider 인스턴스 수와 qualified packet 수를 별도로 표시하므로, adapter 실행 계약이 PASS여도 실제 사고 방출 provider와 시설 QRA가 완료된 것으로 해석하지 않는다.

```powershell
python scripts/build_ijhe_completion_audit.py `
  --current-status CURRENT_STATUS.json `
  --scope-matrix results/20261014/generic_mixed_accident_scope_matrix_refined_pool.json `
  --campaign-result results/20261014/generic_mixed_provider_campaign_refined_pool_result.json `
  --uncertainty-result results/20261014/generic_lh2_mixed_facility_assessment_refined_pool.json `
  --provider-worklist results/20261014/generic_lh2_provider_release_worklist_diagnostic_adapter.json `
  --diagnostic-adapter-registry results/20261014/diagnostic_adapter_registry_audit_live.json `
  --output results/20261014/ijhe_completion_audit_live_with_registry.json
```

현재 live 결과는 12개 검사 중 7개 차단, 5개 통과다. `diagnostic_adapter_execution_contract`는 7/7 클래스 해석으로 통과하지만 provider 인스턴스 0개·qualified packet 0개이며, 기존 설비 사고 packet·주요 사고 범위·시설 IR/F-N·독립 물리검증 gate는 그대로 차단된다. 결과는 `results/20261014/ijhe_completion_audit_live_with_registry.json`과 상태 장부에 기록했다.
