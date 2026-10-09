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

소스 파일은 모두 발견되며, `DynamicVaporizer`, `DynamicReliquefier`, `StrokeLimitedCommandedValve`, `VentStack`, `LayeredTank`, `DynamicHEMPipe`, `MappedPump`가 `export_accident_history(request)`를 구현했다. 유한체적 기화기·재액화기는 명시된 기체 상태와 대기 경계, 개구, 밸브 개방시간, 유한 관찰시계를 받아 `prism.external_accident_history.v1` 이력과 질량 장부를 반환한다. `LayeredTank` 경계는 초기 압력·액체 체적분율·실패 개구·대기 경계를 받아 유한체적 탱크 상태를 전진시키고, 출구 등엔탈피 flash의 기체/액체 분할, 지상 액체 장부, 질량 잔차, 재고소진 또는 진단시계 종료 근거를 함께 반환한다. `DynamicHEMPipe` 경계는 명시적 파손 개구를 적용해 기체 유체·벽 상태를 전진시키고, `MappedPump` 경계는 H-Q-N 운전점을 메타데이터로 보존하면서 상류가 제공한 재고·종료 장부와 사고 개구 방출을 분리한다. 배관 액체/2상 입력은 아직 별도 provider 계약이 없어 거부한다. 밸브·벤트·펌프처럼 자체 재고가 없는 경계는 상류가 `available_mass_kg`와 종료 근거를 명시해야 한다. 관찰시계가 남은 재고를 가진 채 끝나면 `synthetic_diagnostic_horizon`으로 표시하고 qualified 승격을 막는다. 경계 컴포넌트는 PRISM 인터페이스이므로 외부 native 대상에서 제외한다. 정적 감사 상태는 `NATIVE_ACCIDENT_EXPORT_METHODS_FOUND`이다.

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

정적 감사 테스트 2건과 방출 ledger domain/withheld 분리 테스트를 포함한 PRISM portable suite는 441건 통과했고, 외부 `lh2dt_models` 전체 회귀시험은 373건 통과했다. 이 결과는 native method 존재를 확인한 것이며, qualified provider packet·현장 빈도·시설 IR/F-N·독립 물리검증을 승격하지 않는다.

## native export 재감사 후속 기록

외부 저장소 커밋 `4b1ea87`에서 일곱 native 사고 export를 검증했다. `LayeredTank` 시험은 등엔탈피 출구 flash의 기체/액체 분할, 지상 액체 보존, 탱크 질량 잔차 0을 확인하고, `DynamicHEMPipe` 시험은 명시적 파손 개구의 기체 재고수지와 액체 입력 거부를 확인한다. `MappedPump` 시험은 H-Q-N map 운전점과 상류 재고 장부를 분리해 보존하는지 확인한다. 밸브·벤트 시험은 개방 명령 또는 고정 출구가 상류 재고 장부 없이 유량을 만들지 않도록 확인한다. 이 경계는 PRISM의 기존 합성 adapter를 자동으로 대체하지 않으며, 실제 차단·재고소진·시설 형상 결합과 qualified provider packet 생성이 완료될 때까지 시설 완료 감사는 계속 제한된다.

## native LayeredTank strict smoke

`scripts/run_lh2dt_native_layered_tank_smoke.py`는 외부 `LayeredTank.export_accident_history(request)`를 직접 호출한 뒤 PRISM의 `export_equipment_liquid_accident_history()`와 strict `ResolvedLiquidRelease` 검증을 통과시킨다. 2026-10-18 최신 실행은 외부 커밋 `4b1ea87` 소스 digest `79a621dd…`, 0.05 s 이력, strict 질량 잔차 0 kg, 엔탈피 잔차 0 J, native export 약 1.79 s를 기록했다. 같은 packet을 `validate_lh2dt_prism_packet_chain.py`에 넣은 전체 consequence chain도 `END_TO_END_DIAGNOSTIC_EXECUTED`로 약 23.38 s에 끝났다. 이 결과는 방출→피해 연결 코드가 실제 native 탱크 응답을 소비했다는 증거지만, 합성 형상·초기상태·개구·기상과 airborne-liquid 미구현 때문에 qualified provider packet, 현장 빈도, 시설 IR/F-N으로 승격하지 않는다. 결과는 `results/20261018/native_layered_tank_smoke_chain/verification.json`에 보존한다.

## native packet과 문헌 빈도를 함께 쓰는 저장탱크 진단

`scripts/run_lh2dt_native_frequency_case.py`는 한 단계 더 좁은 연결시험이다. 기존 혼합 캠페인의 `LH2_VESSEL AREA_0.01%` 문헌 빈도(중앙값 `6.5×10⁻⁴ item⁻¹ year⁻¹`)는 그대로 읽고, 그 사건의 방출 이력만 native `LayeredTank.export_accident_history()`로 다시 생성한다. 개구 직경 `0.0127 m`를 exact-match로 확인한 뒤 provider packet을 `ResolvedLiquidRelease`로 변환하고, 동일한 facility manifest·기상·점화·IR/F-N 계산기에 넣는다. 따라서 이 실행은 **문헌 빈도 → native 방출 → SLABx-LH2/풀 → 분산·점화·피해** 연결을 실제로 확인한다.

2026-10-18 실행 결과는 `results/20261018/native_lh2dt_frequency_case/verification.json`과 추적 가능한 요약본 `examples/native_lh2dt_frequency_case_verification.json`에 저장되어 있다. native export는 약 0.29 s, 전체 혼합 캠페인 재실행은 약 23.8 s였고, 해당 저장탱크 사건은 `EXECUTED_OPERATOR_LIMITED`로 끝났다. provider 질량 잔차는 0 kg이며 문헌 빈도는 provider packet에서 추정하지 않았다. 이 결과도 합성 초기상태·형상·대기경계·선언된 작은 풀 footprint를 사용하고, 나머지 사고가족이 부분/미계산이므로 qualified provider와 시설 총 IR/F-N으로 승격하지 않는다. 이 구분을 보존하기 위해 `qualified_provider_packet_count=0`, `provider_packet_promoted=false`, `facility_qra_claim=false`를 고정한다.

## native DynamicHEMPipe 액체·2상 방출과 배관 빈도 진단

외부 저장소 `lh2dt_models` 커밋 `78e1af1`에서 `DynamicHEMPipe.export_accident_history(request)`가 명시적 `initial_quality`를 받도록 확장됐다. 품질이 0이면 액체, 0과 1 사이면 균질 2상 상태로 시작하고, 대기압 flash 결과를 기체 질량·지상 액체 질량으로 나눠 반환한다. airborne liquid은 독립 액적 검증 전까지 0으로 고정하며, 질량·엔탈피 장부와 종료시계를 packet에 남긴다. 기존 기체 경로는 그대로 보존한다.

`scripts/run_lh2dt_native_dynamic_pipe_frequency_case.py`는 `LH2_PIPE AREA_0.01%`의 문헌 개구 `0.00025 m`와 정확히 일치하는 native 배관 packet을 생성해 strict liquid adapter와 전체 consequence chain에 넣는다. 2026-10-18 실행은 `phase_basis=two_phase`, provider 질량 잔차 `0 kg`, 엔탈피 잔차 약 `-2.78×10⁻¹⁷ J`, native export 약 `0.24 s`, consequence chain 약 `16.8 s`를 기록했다. 파이프의 다른 네 개 개구 bin은 `UNCOMPUTED`로 명시했고, 다른 설비는 이 단일 진단에서 제외 사유를 기록했다.

결과는 `results/20261018/native_lh2dt_dynamic_pipe_frequency_case/verification.json`과 [추적 요약](../examples/native_lh2dt_dynamic_pipe_frequency_case_verification.json)에 보관한다. 이 실행은 문헌 빈도를 provider packet에서 추정하지 않고 그대로 적용한 부분 진단이다. 10 m 합성 배관의 한 검토 위치에만 위치 가중치 `0.1`을 배분했으며, 잔류 재고가 있는 0.01 s 진단시계·합성 형상·선언된 작은 풀 footprint를 사용했다. 따라서 qualified provider packet, 현장 빈도, 시설 전체 IR/F-N, 물리검증을 승격하지 않는다.
