# PRISM 외부 LH2 모델 native 사고계약 감사

## 목적

액화수소 디지털트윈을 위험도 계산에 연결할 때 `simulate()`나 `step()`이 있다는 사실과 실제 사고 방출 이력을 제공한다는 사실을 혼동하면 안 된다. 이 감사는 외부 소스 코드를 실행하지 않고 클래스 정의를 읽어 다음 두 경계를 따로 기록한다.

- 정상 공정상태 계산 메서드: `simulate`, `step`, `evaluate`, `run`
- 사고 방출 계약: `export_accident_history(request)`와 종료·재고 장부 메서드
- PRISM-side 진단 adapter: 외부 native 클래스가 아니라 PRISM 저장소가 합성 진단을 감싼 wrapper

감사 결과만으로 사고 packet, 빈도, SLABx-LH2 검증, 시설 IR/F-N을 승격하지 않는다.

## 재현 명령

```powershell
python scripts/audit_lh2dt_native_contract.py `
  --binding examples/generic_lh2_model_binding.json `
  --external-root "C:\path\to\lh2_models" `
  --output results/20261018/lh2dt_native_contract_audit.json
```

`--prism-root`를 생략하면 현재 PRISM checkout을 사용한다. 감사기는 외부 Python 모듈을 import하거나 solver를 실행하지 않으므로, 소스 구조를 확인하는 계약 감사와 실제 provider 실행을 분리한다.

## 현재 결과

기록 `results/20261018/lh2dt_native_contract_audit.json`의 요약은 다음과 같다.

| 항목 | 결과 |
|---|---:|
| 외부 binding | 8개 |
| 외부 `lh2dt` 설비 native 사고 export | 7/7 |
| 정상 상태 메서드가 확인된 외부 설비 | 7/7 |
| PRISM-side 진단 adapter 계약 확인 | 7/7 |
| qualified provider packet 승격 | 아니오 |

소스 파일은 모두 발견되며, `DynamicVaporizer`, `DynamicReliquefier`, `StrokeLimitedCommandedValve`, `VentStack`, `LayeredTank`, `DynamicHEMPipe`, `MappedPump`가 `export_accident_history(request)`를 구현했다. 유한체적 기화기·재액화기는 명시된 기체 상태와 대기 경계, 개구, 밸브 개방시간, 유한 관찰시계를 받아 `prism.external_accident_history.v1` 이력과 질량 장부를 반환한다. `LayeredTank` 경계는 초기 압력·액체 체적분율·실패 개구·대기 경계를 받아 유한체적 탱크 상태를 전진시키고, 출구 등엔탈피 flash의 기체/액체 분할, 지상 액체 장부, 질량 잔차, 재고소진 또는 진단시계 종료 근거를 함께 반환한다. `DynamicHEMPipe` 경계는 명시적 파손 개구와 초기 품질을 적용해 기체 또는 액체/2상 유체·벽 상태를 전진시키고, 대기 flash의 기체·지상 액체 장부를 반환한다. airborne liquid은 독립 액적 검증 전까지 0으로 제한한다. `MappedPump` 경계는 H-Q-N 운전점을 메타데이터로 보존하면서 상류가 제공한 재고·종료 장부와 사고 개구 방출을 분리한다. 단일 배관 export는 결합 release-set 없는 양단 파열을 거부한다. 밸브·벤트·펌프처럼 자체 재고가 없는 경계는 상류가 `available_mass_kg`와 종료 근거를 명시해야 한다. 관찰시계가 남은 재고를 가진 채 끝나면 `synthetic_diagnostic_horizon`으로 표시하고 qualified 승격을 막는다. 경계 컴포넌트는 PRISM 인터페이스이므로 외부 native 대상에서 제외한다. 정적 감사 상태는 `NATIVE_ACCIDENT_EXPORT_METHODS_FOUND`이다.

이 결과는 현재 병목을 구체화한다. 기화기·재액화기·밸브·벤트에 native 사고경계가 생겼지만, 다음 연결은 나머지 설비 solver도 다음을 자기 모델에서 반환하도록 하는 것이다.

1. 명시된 사고 포트와 고장 mode
2. 시간별 질량·엔탈피·상 분할
3. 검출·차단 branch와 실제 종료시각
4. 남은 재고와 질량 잔차
5. provider source/state digest

그 결과를 `prism.external_accident_history.v1`로 내보내면 PRISM strict adapter가 검증할 수 있다. 진단 wrapper는 개발·회귀 확인용으로 유지하고 native packet으로 자동 대체하지 않는다.

## 판정 정책

- 클래스에 `export_accident_history`가 있어도 qualified packet은 아니다.
- 정상 메서드의 유량·압력·온도를 사고 지속시간이나 재고 소진으로 추정하지 않는다.
- PRISM-side adapter가 같은 이름의 메서드를 제공해도 외부 모델 native 기능으로 기록하지 않는다.
- source digest와 계약 감사는 재현성 자료이며, 독립 물리검증이나 현장 빈도 근거를 대신하지 않는다.

정적 감사 테스트 2건과 방출 ledger domain/withheld 분리 테스트를 포함한 PRISM portable suite는 최신 변경 후 447건 통과했고, 외부 `lh2dt_models` 전체 회귀시험은 375건 통과했다. 이 결과는 native method 존재를 확인한 것이며, qualified provider packet·현장 빈도·시설 IR/F-N·독립 물리검증을 승격하지 않는다.

## native export 재감사 후속 기록

외부 저장소 커밋 `3d9b982`에서 일곱 native 사고 export를 검증했다. `LayeredTank` 시험은 등엔탈피 출구 flash의 기체/액체 분할, 지상 액체 보존, 탱크 질량 잔차 0을 확인하고, `DynamicHEMPipe` 시험은 명시적 파손 개구의 기체 재고수지와 액체 입력 거부를 확인한다. `MappedPump` 시험은 H-Q-N map 운전점과 상류 재고 장부를 분리해 보존하는지 확인한다. 밸브·벤트 시험은 개방 명령 또는 고정 출구가 상류 재고 장부 없이 유량을 만들지 않도록 확인한다. 이 경계는 PRISM의 기존 합성 adapter를 자동으로 대체하지 않으며, 실제 차단·재고소진·시설 형상 결합과 qualified provider packet 생성이 완료될 때까지 시설 완료 감사는 계속 제한된다.

## native LayeredTank strict smoke

`scripts/run_lh2dt_native_layered_tank_smoke.py`는 외부 `LayeredTank.export_accident_history(request)`를 직접 호출한 뒤 PRISM의 `export_equipment_liquid_accident_history()`와 strict `ResolvedLiquidRelease` 검증을 통과시킨다. 2026-10-18 최신 실행은 외부 커밋 `6ed5689` 소스 digest `239439eb…`, 0.05 s 이력, strict 질량 잔차 0 kg, 엔탈피 잔차 0 J, native export 약 1.70 s를 기록했다. 같은 packet을 `validate_lh2dt_prism_packet_chain.py`에 넣은 전체 consequence chain도 `END_TO_END_DIAGNOSTIC_EXECUTED`로 약 31.65 s에 끝났다. 이 결과는 방출→피해 연결 코드가 실제 native 탱크 응답을 소비했다는 증거지만, 합성 형상·초기상태·개구·기상과 airborne-liquid 미구현 때문에 qualified provider packet, 현장 빈도, 시설 IR/F-N으로 승격하지 않는다. 결과는 `results/20261018/native_layered_tank_smoke_chain/verification.json`에 보존한다.

## 2026-10-22 외부 소스 기준 재실행

현재 `lh2dt_models` 소스 digest `1b9503c459470b899f684b8883ed3fe155a0900d0eb335011a74de770ae5ce52`로 `run_lh2dt_native_layered_tank_smoke.py --run-consequence-chain`을 다시 실행했다. 결과는 `results/20261022/native_layered_tank_smoke_current_chain/verification.json`에 있다.

- native `LayeredTank.export_accident_history(request)` 실행: 약 1.83 s
- strict packet 이력: 0.05 s
- 질량 잔차: 0 kg
- 엔탈피 잔차: 0 J
- 전체 방출→SLABx-LH2/풀→점화→피해 chain: 약 19.53 s
- chain 상태: `END_TO_END_DIAGNOSTIC_EXECUTED`

현재 소스에서 실제 native 응답이 PRISM strict packet과 피해 chain에 소비된 것을 재확인했다. 입력은 여전히 합성 탱크 형상·초기상태·개구·대기경계이며 airborne liquid은 0으로 제한된다. 따라서 이 결과는 설비별 현장 packet, 현장 빈도, 독립 물리검증 또는 시설 IR/F-N을 열지 않는다.

같은 소스에서 `DynamicHEMPipe` full-bore도 재실행했다. `results/20261022/native_dynamic_pipe_full_bore_current/verification.json`은 0.01 m 개구, 2상 상태, provider 자연 종료 `model_pressure_equalization`, 방출 지속시간 `0.03141380098 s`, 최종 압력 `101325.000000004 Pa`, 질량 잔차 `0 kg`, native export 약 `0.69 s`, 전체 consequence chain 약 `34.63 s`를 기록한다. 상태는 `END_TO_END_DIAGNOSTIC_EXECUTED`이다. 이 실행은 최신 native 배관 응답도 PRISM strict packet과 방출→피해 chain에서 소비됨을 확인하지만, 합성 1 m 배관과 선언형 pool footprint를 사용하므로 현장 차단 신뢰도·빈도·시설 전체 IR/F-N을 승격하지 않는다.

## native packet과 문헌 빈도를 함께 쓰는 저장탱크 진단

`scripts/run_lh2dt_native_frequency_case.py`는 한 단계 더 좁은 연결시험이다. 기존 혼합 캠페인의 `LH2_VESSEL AREA_0.01%` 문헌 빈도(중앙값 `6.5×10⁻⁴ item⁻¹ year⁻¹`)는 그대로 읽고, 그 사건의 방출 이력만 native `LayeredTank.export_accident_history()`로 다시 생성한다. 개구 직경 `0.0127 m`를 exact-match로 확인한 뒤 provider packet을 `ResolvedLiquidRelease`로 변환하고, 동일한 facility manifest·기상·점화·IR/F-N 계산기에 넣는다. 따라서 이 실행은 **문헌 빈도 → native 방출 → SLABx-LH2/풀 → 분산·점화·피해** 연결을 실제로 확인한다.

2026-10-18 실행 결과는 `results/20261018/native_lh2dt_frequency_case/verification.json`과 추적 가능한 요약본 `examples/native_lh2dt_frequency_case_verification.json`에 저장되어 있다. native export는 약 0.29 s, 전체 혼합 캠페인 재실행은 약 23.8 s였고, 해당 저장탱크 사건은 `EXECUTED_OPERATOR_LIMITED`로 끝났다. provider 질량 잔차는 0 kg이며 문헌 빈도는 provider packet에서 추정하지 않았다. 이 결과도 합성 초기상태·형상·대기경계·선언된 작은 풀 footprint를 사용하고, 나머지 사고가족이 부분/미계산이므로 qualified provider와 시설 총 IR/F-N으로 승격하지 않는다. 이 구분을 보존하기 위해 `qualified_provider_packet_count=0`, `provider_packet_promoted=false`, `facility_qra_claim=false`를 고정한다.

## native DynamicHEMPipe 액체·2상 방출과 배관 빈도 진단

외부 저장소 `lh2dt_models` 커밋 `6ed5689`에서 `DynamicHEMPipe.export_accident_history(request)`가 명시적 `initial_quality`를 받도록 확장됐다. 품질이 0이면 액체, 0과 1 사이면 균질 2상 상태로 시작하고, 대기압 flash 결과를 기체 질량·지상 액체 질량으로 나눠 반환한다. airborne liquid은 독립 액적 검증 전까지 0으로 고정하며, 질량·엔탈피 장부와 종료시계를 packet에 남긴다. 기존 기체 경로는 그대로 보존한다.

`scripts/run_lh2dt_native_dynamic_pipe_frequency_case.py`는 `LH2_PIPE AREA_0.01%`의 문헌 개구 `0.00025 m`와 정확히 일치하는 native 배관 packet을 생성해 strict liquid adapter와 전체 consequence chain에 넣는다. 2026-10-18 실행은 `phase_basis=two_phase`, provider 질량 잔차 `0 kg`, 엔탈피 잔차 약 `-2.78×10⁻¹⁷ J`, native export 약 `0.24 s`, consequence chain 약 `16.8 s`를 기록했다. 파이프의 다른 네 개 개구 bin은 `UNCOMPUTED`로 명시했고, 다른 설비는 이 단일 진단에서 제외 사유를 기록했다.

결과는 `results/20261018/native_lh2dt_dynamic_pipe_frequency_case/verification.json`과 [추적 요약](../examples/native_lh2dt_dynamic_pipe_frequency_case_verification.json)에 보관한다. 이 실행은 문헌 빈도를 provider packet에서 추정하지 않고 그대로 적용한 부분 진단이다. 10 m 합성 배관의 한 검토 위치에만 위치 가중치 `0.1`을 배분했으며, 잔류 재고가 있는 0.01 s 진단시계·합성 형상·선언된 작은 풀 footprint를 사용했다. 따라서 qualified provider packet, 현장 빈도, 시설 전체 IR/F-N, 물리검증을 승격하지 않는다.

## native DynamicHEMPipe full-bore 유한 방출의 자연 종료 연결

외부 `DynamicHEMPipe` 커밋 `3d9b982`에는 finite-bore 방출의 압력 평형 종료와 스텝 내부 이벤트 보정이 추가됐다. provider는 매 시간 간격의 유량·엔탈피·flash 결과를 반환하고, 대기압에 도달하거나 유량이 유한재고 기준 이하가 되면 `termination_basis=model_pressure_equalization`과 최종 압력을 함께 기록한다. adaptive step은 RK4 중간 상태가 음의 재고가 되지 않도록 간격을 줄인다. 기존 명시적 격리 시계는 같은 경로에서 유지된다.

`scripts/run_lh2dt_native_dynamic_pipe_full_bore_case.py`는 합성 일반 LH2 매니페스트의 이송배관 full-bore (`0.01 m`)를 이 native provider에 연결하고, `source_duration_mode=model_natural`로 PRISM의 `equipment_liquid_release` validator와 consequence chain을 실행한다. 2026-10-18 기록 `results/20261018/native_dynamic_pipe_full_bore/verification.json`은 provider duration `0.0314138 s`, 최종 압력 `101,325.000000004 Pa`, `pressure_equalized=true`, 질량 잔차 `0 kg`, native export 약 `722 ms`, consequence chain 약 `54.9 s`, `END_TO_END_DIAGNOSTIC_EXECUTED`를 보인다. 이는 요청된 시간까지 유량을 연장하지 않고 provider가 반환한 자연 종료까지만 계산했다는 증거다.

이 시험은 **방출→SLABx-LH2/풀→피해 chain의 연결 회귀**를 보강하지만, 1 m 합성 배관·초기상태·대기경계·선언된 pool footprint·airborne liquid 0 가정만 사용한다. 따라서 full-bore 사고가 시설 전체에 적용됐거나 현장 빈도·차단 신뢰도·시설 IR/F-N이 확보됐다고 해석하지 않는다. 현재 상태는 `END_TO_END_DIAGNOSTIC_EXECUTED`, `frequency_applied=false`, `facility_qra_claim=false`, `physical_validation_claim=false`이다.

## native DynamicHEMPipe full-bore와 문헌 빈도 결합

같은 provider packet에 문헌 빈도를 붙이는 경로도 별도 진단으로 확인했다. `scripts/run_lh2dt_native_dynamic_pipe_full_bore_frequency_case.py`는 합성 1 m·0.025 m 배관의 full-bore packet을 만들고, 빈도 계획에서 `generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%`를 생성한다. 배관 빈도는 길이 기반이므로 10 m 문헌 노출에 위치 가중치 `0.1`을 적용해 검토한 한 출구의 exposure multiplier를 정확히 `1`로 만든 뒤, `FrequencyEvent`의 개구 `0.025 m`와 provider opening을 exact-match한다.

2026-10-18 실행 결과는 provider 자연 종료 `0.03141380098 s`, 최종 압력 `101325.0000000035 Pa`, 질량 잔차 약 `−1.7×10⁻¹⁸ kg`, native export 약 `751 ms`, consequence chain 약 `49.3 s`이다. 연간 빈도 `1.9×10⁻⁷ year⁻¹`은 Brooks, Ehrhart & LaFleur (2021) Table 2의 `LH2_PIPE AREA_100%` 행에서 읽었고, provider packet으로부터 추정하지 않았다. 결과 요약은 [native full-bore frequency verification](../examples/native_lh2dt_dynamic_pipe_full_bore_frequency_case_verification.json)에 보관한다.

이 결합은 “문헌 initiating frequency → native 설비 방출 → 자연 종료 → SLABx-LH2/TNO 피해 chain”을 한 사건에서 확인한 것이다. 합성 형상·초기 상태·대기 경계·선언 pool footprint를 사용하므로 현장 빈도 보정, 차단 신뢰도, 물리검증, 시설 전체 IR/F-N으로 승격하지 않는다. 전체 감사의 새 검사 `diagnostic_native_full_bore_frequency_binding`은 `PASS` 진단 전용이며, 최신 감사는 24개 검사·3개 차단 이유를 유지한다.

같은 사건을 `scripts/run_lh2dt_native_dynamic_pipe_full_bore_facility_frequency_case.py`로 `RiskCampaign`에도 넣었다. campaign에는 5개 배관 opening bin이 남고, `AREA_100%` 1건만 실행되어 4개 bin은 `UNCOMPUTED`로 보존된다. 실행된 사건은 4개 risk atom과 조건부 IR/F-N 장부에 도달했지만 `facility_total_risk_available=false`, `complete_facility_qra_claim=false`로 유지된다. 요약은 [native full-bore facility-frequency verification](../examples/native_lh2dt_dynamic_pipe_full_bore_facility_frequency_case_verification.json)이다. 이 결과는 시설 risk ledger 구조에 들어간 범위를 보여주며, 부분 범위를 전체 시설 위험으로 합산하지 않는다.

## provider-resolved pool footprint 경계

액체 packet이 지면 액체를 반환하는 것만으로는 풀의 반경을 알 수 없다. 기존 진단은 `PoolBoundary.footprint_origin=declared_sensitivity`를 사용해 작은 민감도 footprint를 명시했으며, 이 값은 시설 형상이나 적격 provider 증거가 아니다.

이를 구분하기 위해 `prism.resolved_pool_footprint.v1` 계약을 추가했다. provider가 `origin=provider_resolved`, 충돌 위치, 반경, 근거, `provider_result_digest`와 같은 결과 digest를 반환하면 PRISM adapter가 thermal pool context의 반경과 provenance를 덮어쓴다. digest가 다르거나 thermal pool context가 없으면 요청을 거부한다. `reviewed_design`·`measured`도 provenance 없이는 받을 수 없다. 기존 packet에 footprint가 없으면 declared-sensitivity 진단만 허용되며, qualified 승격으로 바뀌지 않는다.

이 경계는 풀 solver가 provider의 실제 바닥 형상을 대신 계산한다는 뜻이 아니다. 향후 provider가 위치별 wet area, 표면 재질, 배수·방호 형상을 함께 내보낼 때 확장할 수 있는 최소 계약이며, 현재 native LayeredTank·DynamicHEMPipe 결과는 해당 footprint를 제공하지 않아 `operator-limited` 상태로 남는다.

## 2026-10-18 최신 DynamicHEMPipe facility ledger 재검증

기존 실행기의 전체 캠페인 입력에는 다른 설비의 `precomputed_events`와 저장탱크 성공·실패 분기가 함께 들어 있었다. 배관 단일 진단에서 이 행을 그대로 사용하면 제외된 설비가 선택 범위에 다시 들어가거나, 저장탱크 분기 결과를 배관 결과로 잘못 해석할 수 있다. 실행기를 다음처럼 보완했다.

- 배관만 선택한 frequency scope에 맞춰 다른 설비의 사전 계산 행을 명시적으로 제거한다.
- 전체 시설 manifest에 없는 제외 component를 frequency plan에서 제거한다.
- 저장탱크 분기 중 첫 번째 명시적 request는 배관 consequence request의 형식 템플릿으로만 복사하고, 저장탱크 결과·확률·고장 상태를 계산하거나 합치지 않는다.
- 선택 branch ID와 scope filtering provenance를 결과에 기록한다.

전용 단일 설비 manifest로 최신 외부 commit `7072374`를 재실행한 결과는 [machine-readable verification](../examples/native_dynamic_pipe_full_bore_facility_frequency_case_recheck_20261018.json)에 보존했다.

| 항목 | 결과 |
|---|---:|
| provider termination | `model_pressure_equalization` |
| provider duration | `0.03141380098 s` |
| pressure-equalization observation | `0.2 s`, post-stop max flow `0 kg/s` |
| mass residual | `−1.73×10⁻¹⁸ kg` |
| literature frequency | `1.9×10⁻⁷ year⁻¹`, LH2_PIPE AREA_100% exact match |
| facility campaign | 5 opening bins, 1 executed, 4 `UNCOMPUTED` |
| risk atoms | 4 conditional atoms |
| facility total IR/F-N | withheld |

이 재검증은 “문헌 빈도 → provider 자연 종료 방출 → PRISM release ledger → SLABx-LH2/TNO 피해 chain → 설비 campaign risk atom”의 실행을 확인한다. 합성 배관·수용점·초기상태와 provider qualification sidecar가 사용되지 않았으므로 시설 전체 QRA나 현장 사고빈도 승인으로 승격하지 않는다.

## 2026-10-18 권위 AREA_100% 상태의 최신 provider 재실행

이전 실행과 외부 모델 소스가 바뀌었는지 확인하기 위해, 현재 권위 캠페인의 `liquid-transfer-line-01` `AREA_100%` 검증 입력을 다시 읽고 외부 `lh2dt_models` `7072374`의 `DynamicHEMPipe`로 동일 상태를 재생성했다. 상태 snapshot digest는 `37a284a47ad8c32a3d81f3c5685fc55b3e7aa37f9c02a84a170e4827c32e4194`로 기존 행과 일치했다. provider 결과 digest는 `4100182fdb209f3e264dcc750c8aeefa01973c61ecb41012d9ddc7e74e58ee3f`이며, 자연 종료 근거는 `model_pressure_equalization`, 방출 시간은 `0.24005155145460036 s`, 질량 잔차는 약 `1.39×10⁻¹⁷ kg`이다. provider는 압력 평형 시각 `0.24005155145460036 s`, 후속 관찰 `0.2 s`, 최종 압력 `101324.99999999831 Pa`, 후속 최대 유량 `0 kg/s`를 명시했다.

재생성 packet은 PRISM strict release adapter를 통과한 뒤, 단일 사건 `RiskCampaign`에 연결했다. 축소 선언 감도 격자에서 1개 event·1개 case·4개 risk atom이 `DECLARED_SCOPE_EXECUTED`로 완료되었고, 이번 실행의 연결 처리시간은 약 `29.07 s`였다. 기록은 [machine-readable candidate](../examples/native_dynamic_pipe_exact_area100_reduced_grid_candidate_20261018.json), 실행기는 [`run_lh2dt_native_dynamic_pipe_exact_area100_candidate.py`](../scripts/run_lh2dt_native_dynamic_pipe_exact_area100_candidate.py)이다.

이 결과는 최신 외부 provider가 동일 권위 상태를 재현하고 방출→PRISM release ledger→SLABx-LH2/풀→피해 risk atom 경로를 소비한다는 진단 증거다. 축소 격자, 합성 수용점·기상, qualification sidecar 부재 때문에 시설 전체 IR/F-N·QRA나 물리검증으로 승격하지 않는다. 대형 격자 재실행은 backend `180 s` 실행 한계에 도달했으므로 full-grid 처리시간으로 사용하지 않는다. 현재 권위 24-event campaign은 변경하거나 새 digest로 묵시적 재결합하지 않았고, SLABx-LH2 소스도 수정하지 않았다.
