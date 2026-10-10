# native 일반 LH2 전체 설비 빈도·IR/F-N 연결 기록 (2026-10-26)

이번 실행은 일반 옥외 액화수소 시설의 7개 사고 대상 설비를 하나의 PRISM 시설 캠페인으로 계산했다. 대상 설비는 저장탱크, 이송배관, 밸브, 압력방출 벤트, 펌프, 기화기, 재액화기이며, receiving boundary는 사고 빈도 대상에서 명시적으로 제외했다.

## 재현 명령

```powershell
python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261023/native_generic_scope_campaign_v11.json `
  --backend-config results/20261009/backend_config_current.json `
  --output-dir results/20261026/native_full_scope_frequency_assessment
```

캠페인 실행 시 `RiskCampaign`이 `FrequencyPlan`의 24개 사건을 생성하고, 각 provider 방출 요청에 동일한 사건의 문헌 빈도를 `bind_event()`로 붙인다. provider packet은 방출 지속시간·종료 basis·질량 장부를 제공하고, 빈도는 별도의 문헌 catalogue가 제공한다. 따라서 어느 한쪽 자료가 다른 쪽을 대신하지 않는다.

## 실행된 연결

| 항목 | 결과 |
|---|---:|
| 설비 컴포넌트 | 8개 (사고 대상 7개 + 경계 1개) |
| 문헌 빈도 사건 | 24개 |
| 물리 계산 case | 24개 |
| 수치 결과가 나온 case | 24개 |
| 완전 상태 `EXECUTED` | 5개 |
| 운전자 제한 `EXECUTED_OPERATOR_LIMITED` | 19개 |
| risk atom | 96개 |
| 빈도 불확실성 시나리오 | 중앙·p05·p95 3개 |
| provider 방출 worklist | 24개 사건 요청·24개 정합 (`ALIGNED`), 실제 qualified packet 0개 |
| 조건부 시설 IR/F-N | 계산됨 |
| 적격 시설 전체 위험도 | 보류 |

5개 완전 상태는 벤트 1개와 기화기 3개, 재액화기 1개다. 나머지 19개도 방출부터 SLABx-LH2/SLABx, 점화, 피해, 시설 원장까지 숫자는 통과했지만 provider가 일정 상태 또는 열린 물리 경계를 선언했기 때문에 시설 전체 합산의 완전 증거로 승격하지 않았다.

합성 near-receptor 진단 조건에서 `worker-01`의 조건부 연간 IR은 양 끝점 모두 `4.68e-5 / year`이고, 기대 사망자 `N=1` F/N 점의 조건부 빈도도 `4.68e-5 / year`였다. 이 값은 시설 전체의 인증된 위험도가 아니라, 현재 평가된 96개 atom의 계산 연결이 닫혔다는 진단값이다.

## 사고군 범위

`scope_matrix.json`은 다음을 분리한다.

- `provider_worklist.json`은 각 문헌 빈도 사건에 필요한 방출 패킷의 사건 ID·사고군·방출 모드·종료 기준·필수 필드를 1:1로 요청한다. 이번 실행은 24/24 사건이 캠페인과 정합하지만 실제 적격 packet은 0개라서 worklist 자체는 `READY_FOR_PROVIDER_PACKETS`로 남는다.

- `vessel_hole`, `pipe_hole`, `valve_hole`, `pump_hole`, `liquid_two_phase`, `inventory_depletion`, `two_sided_rupture`는 사건과 결과가 있으나 운전자 제한 때문에 `PARTIAL`이다.
- `vent_hole`, `vaporizer_hole`, `reliquefier_hole`, `inventory_over_600s`는 이번 선언 범위에서 계산 경로를 확인했다. 해당 사건의 완전성은 각 case 상태와 종료 장부를 함께 읽어야 한다.
- `vertical_handoff`는 적용 가능한 설비가 있지만 이번 24개 사건에 별도 handoff 사건이 생성되지 않아 `NO_EVENT_GENERATED`로 남겼다. 다른 사건으로 대신 계산하지 않는다.

따라서 `facility_total_risk_available=false`, `complete_facility_qra_claim=false`, `provider_packet_promoted=false`, `physical_validation_claim=false`가 의도적으로 유지된다. 문헌 p05/p95는 저장된 risk atom의 빈도만 재가중하며, 시설 신뢰구간이나 현장 빈도 학습을 의미하지 않는다.

## 처리시간

이번 한 번의 24-case 실행은 약 266초였다. case 시간 중앙값은 약 4.12초, 최대 약 65.7초였다. 이는 반복 실행의 처리율이나 실시간 1 Hz 보장이 아니며, 디지털트윈 실시간 적용을 위해서는 이후 캐시·저감모델·case 선택 정책을 별도로 검증해야 한다.

## 산출물

- `results/20261026/native_full_scope_frequency_assessment/verification.json`: 실행 요약·게이트·빈도 일치 검사
- `campaign_result.json`: 24개 사건, case, 방출 종료·재고 장부, 96개 risk atom
- `facility_assessment.json`: 조건부 시설 IR/F-N과 문헌 빈도 민감도
- `scope_matrix.json`: 설비별·사고군별 완전/부분/미생성 상태
- `provider_worklist.json`: 24개 빈도 사건과 provider 방출 packet 요청의 1:1 정합표
- `frequency_scenarios.json`: 자산별 shared central/p05/p95 가정
- `binding_provenance.json`: 사건 빈도와 provider packet의 분리·digest 기록
- `ijhe_completion_audit.json`: 15개 검사와 현재 4개 차단 사유

이 기록은 IJHE 방법론의 “설비 상태 → 방출·종료 → 확산·피해 → 시설 IR/F-N” 연결을 보여주는 진단 근거다. 실제 일반 시설 결과로 사용하려면 설비별 검토 형상·운전 재고·차단 신뢰도, qualified provider packet, 독립 물리검증, vertical handoff 사건을 추가해야 한다. 현재 감사는 16개 검사 중 12개 통과, 4개 차단이며, worklist 정합성은 통과했지만 packet 자격·사고군 완전성·시설 전체 위험도는 계속 fail-closed다.

## 2026-11-05 일반 설비 crosswalk·빈도 연결 재검증

일반 시설용 합성 manifest에 설비 종류와 사고 포트를 명시한 facility-neutral crosswalk를 적용해 별도 연결 감사를 실행했다. 이 결과는 액화수소검사지원센터의 P&ID를 일반 시설에 복사한 것이 아니라, PRISM의 일반 설비 계약이 어떤 입력을 요구하는지 검증하는 기준 사례다.

| 단계 | 결과 |
|---|---:|
| crosswalk 대상 설비 | 7개 |
| resolved 설비 identity | 7개 |
| 선언된 사고 family | 12개 |
| 문헌 빈도 사건 | 24개 |
| 유효하게 결합된 빈도 사건 | 24개 |
| 빈도 사건이 없는 family | `vertical_handoff` 1개 |
| 사고 방출 packet 승격 | false |
| 시설 QRA 승격 | false |

이번 재검증에서 기존 catalog의 `two_sided_rupture` 적용 설비가 배관·밸브로만 기록되어 있던 오류를 수정했다. 일반 빈도 원장의 재액화기 G4/G5는 약한 shell 열교환기의 양단 파열 사건이므로 `reliquefier`도 같은 family에 포함해야 24개 문헌 사건이 모두 일관되게 바인딩된다. 이 수정은 빈도와 사고 family의 구조적 정합성만 고친 것이며, provider 방출 packet이나 시설 QRA를 만들지 않는다.

재현 입력은 [`generic_lh2_full_scope_equipment_model_audit.json`](../examples/generic_lh2_full_scope_equipment_model_audit.json)과 [`generic_lh2_full_scope_equipment_kind_crosswalk.json`](../examples/generic_lh2_full_scope_equipment_kind_crosswalk.json)이다. 결과는 [`generic_lh2_full_scope_equipment_scenario_coverage.json`](../results/20261105/generic_lh2_full_scope_equipment_scenario_coverage.json) 및 [`generic_lh2_full_scope_equipment_frequency_binding.json`](../results/20261105/generic_lh2_full_scope_equipment_frequency_binding.json)에 저장했다. 실제 시설에서는 이 crosswalk를 P&ID·포트 일정·설비 자료로 대체하고, `vertical_handoff` provider packet과 모든 사고 family의 방출 장부를 추가해야 한다.
