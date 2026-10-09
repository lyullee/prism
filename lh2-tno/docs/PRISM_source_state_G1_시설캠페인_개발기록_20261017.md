# PRISM source-state G1 시설 캠페인 개발기록 (2026-10-17)

## 목적

2026-10-15의 24개 일반 액화수소시설 진단 캠페인에서는 `ambient-vaporizer/G1`이 고속 기체 출구를 갖지만 공급자가 압축성 근접장 평면을 내보내지 않아 `FAILED`로 남았다. 이번 단계는 그 사건을 낮은 마하수 packet으로 바꾸는 것이 아니라, 외부 `lh2dt.DynamicVaporizer`가 내보낸 source/throat 상태를 이용해 별도의 provider-owned plane handoff를 만들고, 기존 사건 ID·설비·포트·문헌 빈도·시설 위치를 그대로 유지한 상태에서 전체 경로가 실행되는지 확인하는 것이다.

이 기록은 실제 설비의 고압 출구 검증이나 시설 QRA 완료를 뜻하지 않는다. 결과는 합성 진단용이며 `provider_packet_promoted=false`, `physical_validation_claim=false`, `complete_facility_qra_claim=false`를 유지한다.

## provider 재실행

선정한 사건은 다음 조건으로 외부 `lh2dt.DynamicVaporizer`를 새로 실행했다.

| 항목 | 값 |
|---|---|
| component / port | `ambient-vaporizer-01` / `vaporizer-accident-out` |
| event | `generic-lh2-full-scope-frequency-example/ambient-vaporizer/G1` |
| release mode | `instantaneous_inventory` |
| inlet pressure / temperature | `1,000,000 Pa` / `300 K` |
| fluid volume | `0.005 m³` |
| opening / discharge coefficient | `0.005 m` / `0.7` |
| provider time grid | `0.1 s`, 5 s request; positive inventory 종료 |
| returned duration / intervals | `1.1 s` / 11 |
| provider initial / final mass | `0.0040173822 kg` / `0.0004304351 kg` |
| provider mass residual | `0 kg` |
| provider result digest | `227caf76e92d93ed99e3653a2c20ccdbe81bc30c16328594c33d4c7e406ee885` |

첫 source state는 `1,000,000 Pa` upstream pressure와 `517,025 Pa` throat pressure를 갖고 choked 상태로 표시됐다. 기존 atmospheric packet의 높은 속도를 source pressure로 역산하지 않고, 이 provider 상태를 handoff 입력으로 사용했다.

## 압축성 handoff

`src/lh2_tno/compressible_source_adapter.py`는 다음을 확인한 뒤 `prism.compressible_plane_handoff.v1`을 만든다.

1. 사건·설비·포트와 upstream provider result digest가 정확히 일치한다.
2. 모든 provider interval에 source/throat 상태가 존재한다.
3. provider의 수소 질량 유량과 handoff 단면의 질량 장부가 일치한다.
4. source state에서 계산한 plane은 provider가 선언한 경계로만 전달한다. PRISM이 고속 제트의 충격파·팽창·방향을 다시 만들거나 낮은 마하수 모델로 바꾸지 않는다.

실행 결과는 다음과 같다.

- handoff source digest: `21012f6a14b1fea24c68764a27a91ac4e41fe3d068d7c8cf7da4b07448780783`
- handoff result digest: `8f5e4d88870b2145a9d6f0c1b5a95c896f1fff5bbb620bc9169d8b69cf8b58eb`
- 11/11 provider interval 소비·검증
- 최대 handoff Mach 수: `3.9982`
- 최대 에너지 잔차: `0 J/kg`
- 최대 엔트로피 잔차: `347.2523 J/(kg·K)`
- evidence status: `synthetic_diagnostic`

시설 매니페스트가 검토한 포트 위치 `[10.0, 0.0, 1.0] m`는 packet의 열역학·유량·종료 이력을 바꾸지 않는 명시적 위치 rebasing으로 적용했다. 이 rebase와 handoff의 감사 파일은 다음에 있다.

- `results/20261017/vaporizer_g1_source_state_rebased/attach_audit.json`
- `results/20261017/vaporizer_g1_source_state_rebased/handoff_validation.json`
- `results/20261017/vaporizer_g1_reexport_source_state/chain/verification.json`

## 24개 사건 재실행

기존 24개 사건 캠페인의 주파수·사건 ID·연간 기상·시설 포트 배치를 복사하고, G1의 `resolved_release`만 source-state handoff packet으로 엄격하게 교체했다. 이것은 기존 공식 결과 파일을 덮어쓰지 않는 별도 `source_state_rebound` 진단이다.

입력과 결과:

- 입력: `results/20261017/generic_mixed_provider_campaign_source_state_rebound_worklist.json`
- 결과: `results/20261017/generic_mixed_provider_campaign_source_state_rebound_result.json`
- 빈도 시나리오: `results/20261017/frequency_scenarios_source_state_rebound.json`
- 빈도 재가중 CLI 결과: `results/20261017/frequency_uncertainty_source_state_rebound_cli.json`
- 빈도 분포 시나리오: `results/20261017/frequency_distribution_scenarios_source_state_rebound.json`
- 빈도 로그정규 표본 CLI 결과: `results/20261017/frequency_distribution_source_state_rebound_cli.json`

실행 요약:

| 지표 | 결과 |
|---|---:|
| 생성 사건 / 실행 case | 24 / 24 |
| `EXECUTED` | 4 |
| `EXECUTED_OPERATOR_LIMITED` | 20 |
| `FAILED` | 0 |
| 별도 `EXECUTED_DOMAIN_INCOMPLETE` 원장 | 1 (미계산 원인 중복 표시) |
| 생성 빈도 합 | `0.01376848 /year` |
| 완전 실행 case 가중 빈도 | `0.01107 /year` |
| 빈도 coverage | `0.8040103` |
| case 최소 / 중앙 / 최대 | `1536.1 / 8291.9 / 65707.0 ms` |
| case p95 / p99 | `20475.2 / 55335.4 ms` |
| 전체 campaign 시간 | `261411.1 ms` |

G1은 이제 low-Mach guard에서 실패하지 않고 `EXECUTED_OPERATOR_LIMITED`가 되었다. G1 case의 provider duration은 `1.1 s`, mass ledger residual은 `0 kg`, case 시간은 `7981.8 ms`다. 제한 사유는 source operator의 constant-state/open physical closure이다. 따라서 실패 한 건을 성공으로 숨긴 것이 아니라, 정확한 source-state handoff를 소비한 뒤 남은 모델 한계를 별도 상태로 기록했다.

## 빈도 불확실성

24개 사건에는 문헌 `p05/p95`와 로그정규 `mu/sigma`가 있는 저장탱크·이송배관·이송밸브 자산과, 공개 분위수 근거가 없는 기화기·PSV·펌프·재액화기 자산이 함께 있다. 이번 결과에는 다음 원칙을 적용했다.

- 문헌 경계가 있는 자산은 `p05`, `published`, `p95`를 계산한다.
- 경계가 없는 자산은 새 분포를 만들지 않고 `fixed`로 선언된 catalogue 빈도를 그대로 둔다.
- shared-asset와 independent-event 방향을 별도 시나리오로 비교한다.
- 로그정규 `mu/sigma`가 있는 사건은 shared-asset/independent-event 표본화를 수행하고, 나머지 사건은 `fixed_event_policy=hold_published`로 선언된 catalogue 빈도를 각 표본에서 그대로 유지한다.
- 빈도 재가중은 저장된 risk atom의 initiating frequency만 바꾸며 물리 계산을 다시 하지 않는다.
- worker-01의 이번 진단 known IR은 모든 시나리오에서 `[0.0, 0.0]`이었다. 이는 해당 합성 수용점 배치에서 산출된 값이며 안전 또는 시설 위험 0을 뜻하지 않는다.
- 전체 시설 IR/F-N은 `null`로 유지한다. 20개 operator-limited case, 합성 종료시계, 실제 설비 형상 및 독립 물리검증이 남아 있기 때문이다.

이번 혼합 분포 표본은 1,000회씩 두 시나리오를 계산했으며 `fresh_physics_executed=false`, `frequency_distribution_credible_interval=true`, `facility_credible_interval=false`를 기록했다. 이는 빈도 모델만 흔든 known-atom 진단 구간이고, 피해 물리·기상·장벽·점화와 미계산 범위는 그대로 고정한다.

최신 IJHE 완료 감사(`results/20261017/ijhe_completion_audit_source_state_rebound.json`)는 13개 검사 중 7개를 통과하고 6개를 차단했다. 공개 실험 hold-out과 질량 장부를 가진 `DynamicLH2PoolX` 풀/확산 구성요소 근거를 별도 통과로 기록했으며, 이는 전체 chain 물리검증으로 승격하지 않는다. 실제 qualified provider packet, 전체 사고범위, 시설 IR/F-N, 완전 시설 빈도 credible interval은 아직 충족되지 않았다. 이 감사 결과는 기능이 실행됐다는 사실과 IJHE용 완성 주장을 분리하는 현재 기준점이다.

이 혼합 catalogue를 위해 `LiteratureFrequencyScenario`에 `fixed` 선택지를 추가했다. `fixed`는 빈도를 0으로 만드는 값이 아니라 사건의 선언된 중앙 빈도를 보존하는 명시적 선택이다. 경계가 없는 사건에 `p05`/`p95`를 요청하면 기존과 같이 오류로 중단한다.

## 판단

이번 단계에서 완성된 것은 다음 연결이다.

`lh2dt.DynamicVaporizer source/throat state` → `compressible plane handoff` → `SLABx-LH2/SLABx` → `cloud` → `ignition/fire/explosion` → `receptor harm` → `risk atom` → `문헌 빈도 재가중`.

아직 완성되지 않은 것은 provider의 고압/underexpanded plane 독립 검증, 실제 설비의 source pressure·재고·차단 조건, operator-limited closure 제거, 모든 사고 family의 qualified packet, 실제 시설 IR/F-N 승격이다. 따라서 이번 결과는 IJHE용 방법·연결 증거와 남은 검증항목을 제공하지만, 실제 시설 안전판정이나 검증된 전체 QRA 결과로 인용할 수 없다.
