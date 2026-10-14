# HAZOP 운전 모드–설비 방출–문헌 빈도–SLABx-LH2 연결 기록

## 무엇을 연결했나

이번 진단은 현장 입력에 압력값과 운전 모드가 함께 들어오는 경우를 대상으로 한다.

```text
상태값 + operating_mode=receiving
  → HAZOP 이탈 판정
  → liquid_two_phase / hole 시나리오 선택
  → 설비 provider의 ResolvedLiquidRelease packet
  → 명시적 문헌 빈도 event binding
  → SLABx-LH2·DynamicLH2PoolX·점화·수용점 피해
  → 현재 기상 조건 IR 원자
  → 명시적 연간 조건·인구·점화 branch를 가진 조건부 시설 IR/F-N handoff
```

예측 경로도 같은 시나리오 ID와 설비 ID를 사용한다.

```text
공정 시뮬레이션 frame(model_prediction)
  → HAZOP 위험조건 최초 진입 확인
  → 같은 provider/frequency/consequence callback 실행
  → 미래 시점 위험 원장
```

여기서 PRISM은 단일 물리 모델이 아니다. HAZOP, 설비 공정 provider, 문헌 빈도, SLABx-LH2, 풀 확산, 점화 및 피해 모델을 같은 사건·설비·운전 모드로 묶고 실행 순서를 관리하는 통합 계층이다.

## 재현 명령

```powershell
python scripts/run_hazop_lh2_provider_diagnostic.py `
  --provider-packet results/20261031/native_generic_scope_packets_pipefix/events/000_storage-tank-01_AREA_0.01pct/resolved_release.json `
  --backend-config results/20261009/backend_config_current.json `
  --output results/20261014/hazop_provider_bound_integrated_risk.json
```

입력은 다음 네 가지를 명시한다.

1. `generic_hazop_tables_by_component_provider_bound.json`: `receiving` 모드의 압력 이탈과 `liquid_two_phase` 사고 family.
2. `resolved_release.json`: 외부 LayeredTank provider가 계산한 액체 방출량·지속시간·재고 소진 종료.
3. `generic_lh2_full_scope_frequency_plan.json`: `storage-shell/AREA_0.01%` 문헌 사건과 p05/published/p95 빈도.
4. `equipment_consequence_template.json` 및 backend pin: 기상·점화·공간영역·SLABx-LH2 실행 컨텍스트.

provider packet에 지면 액체가 있지만 풀 경계가 없으므로, 실행기는 `declared_sensitivity` 풀 반경 0.005 m를 코드에 명시해 넣는다. 이 값은 센서·압력·빈도에서 추정한 값이 아니며, 실제 시설 결과로 승격할 수 없는 합성 민감도 가정이다. 풀 경계가 없는 액체 packet을 조용히 0 풀로 바꾸지 않는 fail-closed 조건을 확인하기 위한 것이다.

예측 frame이 다른 generic facility ID를 가지고 있으면 HAZOP 표의 facility ID로 복사해 정규화한다. 이 정규화는 시설 간 혼합을 허용하는 것이 아니라, 선택 대상 표와 frame의 ID를 반드시 일치시키는 경계 검사다.

## 확인된 결과

출력 파일: `results/20261014/hazop_provider_bound_integrated_risk.json`

`build_ijhe_completion_audit.py --hazop-integrated-risk` 재검사에서 `diagnostic_hazop_integrated_risk`는 PASS가 되었다. 전체 감사는 qualified provider, 사고범위, 물리검증과 시설 전체 IR/F-N 때문에 계속 `INCOMPLETE_EVIDENCE`이며, 이 진단 PASS가 전체 완료를 의미하지는 않는다.

| 항목 | 결과 |
|---|---|
| 통합 상태 | `INTEGRATED_DIAGNOSTIC_COMPLETE` |
| 현재 상태 | `FACILITY_HAZOP_RUNTIME_EVALUATED` |
| 현재 위험 원자 | 1건 |
| 예측 위험조건 진입 | 1건 |
| 예측 정량평가 | 1건 실행, 0건 보류 |
| 문헌 빈도 | 명시적 event binding, 센서/시뮬레이션 추정 없음 |
| provider 자격 | 합성·operator-limited, 물리검증 주장 없음 |
| 시설 campaign handoff | `HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED` |
| 조건부 시설 IR | 계산됨 (`conditional_diagnostic_facility_risk_available=true`) |
| 조건부 시설 F/N | 계산됨 (`conditional_diagnostic_facility_expected_death_fn_low_high`) |
| 시설 연간 IR/F-N 승격 | 보류 (`facility_total_risk_available=false`) |
| 처리시간 | 통합 호출 약 26.29 s, 현재 provider consequence 약 12.75 s; 1 Hz 보장 아님 |

현재 위험 원자는 `storage-tank-01`, `receiving`, `liquid_two_phase`로 기록된다. 문헌 사건의 published frequency와 p05/p95 민감도 구간은 원자 안에 provenance와 source digest와 함께 남는다. 이어서 동일한 원자의 branch별 피해와 명시적 합성 인구 조건을 기존 시설 campaign에 넘겨 조건부 IR과 F/N 곡선을 만들었다. 이 곡선은 선언한 한 조건과 한 수용점의 진단 결과이며, 전체 시설 연간 IR/F-N이 아니다.

## 이 결과가 의미하는 것

이제 “운전 모드가 포함된 현장 입력 → HAZOP 판단 → 설비별 액체 방출 → 문헌 빈도 → SLABx-LH2 피해 → 현재/예측 위험 원자”의 소프트웨어 연결은 한 번 재현된다. 설비별 결합도 유지된다. `component_id`와 `(component_id, scenario_id)` resolver key가 다른 설비의 방출 packet을 섞지 않는다.

아직 완성으로 표시하지 않는 이유는 명확하다.

- provider packet이 합성 진단이고 qualified facility release가 아니다.
- 풀 반경·점화 확률·시설 위치·수용점은 실제 시설 검토값이 아니다.
- 전체 사고 family, 차단 성공/실패, 양단 파열, 벤트, 재고 소진 경계가 모두 qualified packet으로 닫히지 않았다.
- 시설 전체 기상·인구·방호 조건을 모두 덮는 IR/F-N ledger가 완성되지 않았다.
- 독립 실험 또는 검증 데이터로 SLABx-LH2와 provider의 방출·flash·지면 액체 분할을 검증하지 않았다.

따라서 이 기록은 IJHE 개발 단계의 연결 증거이며, 시설 안전 의사결정이나 완성된 QRA 인증 결과가 아니다. 미계산 사고와 증거 부족은 이후 완료 감사에서 계속 별도 상태로 남긴다.
