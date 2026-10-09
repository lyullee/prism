# PRISM provider packet coverage gate

`provider_worklist.py`는 문헌 빈도 사건 24건을 모두 만들지만, provider packet이 없으면 어떤 사건도 물리 계산으로 보내지 않는다. 외부 digital twin이 packet을 제출하면 먼저 작업목록과 정확히 대조해야 한다. 이를 위해 `provider_catalog_coverage.py`와 `audit_provider_catalog_coverage.py`를 추가했다.

## 사용하는 순서

먼저 작업목록을 만든다.

```powershell
$env:PYTHONPATH = "src"
python scripts/build_provider_release_worklist.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --model-binding examples/generic_lh2_model_binding.json `
  --output worklist.json
```

provider가 `prism.resolved_release.v1` 사고 packet을 내보내면 다음으로 대조한다.

```powershell
python scripts/audit_provider_catalog_coverage.py `
  --provider-worklist worklist.json `
  --provider-release-catalog provider_releases.json `
  --release-kind accidental_leak `
  --output provider_coverage.json
```

양단 파열은 `--release-kind two_sided_rupture`와 `prism.resolved_release_set.v1` catalog를 사용한다. 비상 릴리프는 `--release-kind emergency_relief`로 분리한다. 세 catalog를 섞으면 안 된다.

## 무엇을 검사하는가

각 packet의 `event_id`, `component_id`, 사고 포트, release family, 기체/액체 경계, 실패 개구를 작업목록과 비교한다. `hole` 사건은 provider의 `failure_opening_diameter_m`가 빈도 사건의 구경과 정확히 같아야 한다. `inventory_over_600s`는 선언된 600초 이력과 같아야 하며, 양단 파열은 두 포트가 모두 있는 release set이어야 한다. 액체·2상 packet은 작업목록에 액체 경계가 선언된 경우에만 exact match가 된다.

| 상태 | 의미 |
| --- | --- |
| `FULLY_MATCHED` | 모든 작업목록 사건에 packet이 exact match됨. 아직 빈도·종료 문맥·물리 검증을 승인한 것은 아님 |
| `PARTIAL_EXACT_MATCH` | 일부 사건만 exact match됨. 나머지는 시설 계산에서 `UNCOMPUTED`로 남겨야 함 |
| `NO_EXACT_MATCH` | packet은 있지만 작업목록과 exact match된 사건이 없음 |

작업목록에 없는 packet도 `extra_packets`로 기록한다. 이는 설비나 문헌 빈도 범위가 먼저 검토되어야 한다는 뜻이며 자동으로 시설에 추가하지 않는다. 이 도구는 빈도를 부여하지 않고, request defaults를 붙이지 않으며, 정상 유량·센서 시계열을 사고 packet으로 승격하지 않는다. `FULLY_MATCHED` 뒤에도 `build_equipment_campaign.py --provider-release-catalog`의 strict context 검증과 별도 facility IR/F-N·물리 검증 gate가 필요하다.

실제 일반 LH2 설비에 대해 적격으로 승인된 provider packet은 0건이므로 실제 시설 coverage는 계속 `NO_EXACT_MATCH`다. 별도 합성 진단에서는 `lh2dt.LayeredTankNetworkSimulator→SLABx-LH2` 결과를 저장탱크 다섯 area-bin의 설비·포트·개구에 맞춰 `PARTIAL_EXACT_MATCH`(5/24)로 반복 재현했다. 다섯 case 모두 provider 질량 잔차와 5% 유량 gate를 통과했지만, 합성 threshold·종료시계·재고·기상 때문에 실제 방출 이력이나 시설 위험으로 승격하지 않는다. 배관·밸브·벤트·펌프 등 나머지 19개 사건은 packet 없이 남아 있다. 상세 결과는 `results/20261010/layered_tank_worklist_packets/provider_catalog_coverage.json`과 `campaign_verification.json`이다. 기존 단일 사건 재현 결과도 `results/20261009/provider_evidence/generic_lh2_provider_catalog_coverage_layered_exact.json`에 보존한다.

2026-10-14에는 `MappedPump` G1과 `Valve` transfer-valve 5개를 포함한 기존 19개 accidental-leak packet과 `VentStack` G1 emergency-relief packet에 더해, `DynamicVaporizer` G1/G2 재고 방출과 `DynamicReliquefier` G4/G5 양단 파열 set을 추가했다. 결합 결과는 `results/20261014/combined_provider_catalog_family_coverage_v5.json`이며, `provider_packet_count=24`, `exact_match_count=24`, `unmatched_event_count=0`, `extra_packet_count=0`이다. accidental leak, emergency relief, two-sided rupture를 서로 다른 loader와 operator로 검사하므로 한쪽 endpoint나 relief packet을 다른 사건에 재사용할 수 없다. 모든 packet은 `synthetic_diagnostic`이고 실제 적격 provider packet은 0건이다. G2 inventory-over-600s는 synthetic facility에서 source→SLABx-LH2→cloud→점화·피해 chain까지 실행했고 질량 잔차는 약 `3.4e-21 kg`이다. G1은 고압·작은 진단 면적에서 low-Mach exit scope을 넘어 fail-closed했고, G4/G5는 반대 방향 endpoint가 현재 handoff의 상류 제트 제한에 걸려 consequence chain을 실행하지 않았다. 따라서 `FULLY_MATCHED`는 구조 계약 완료를 뜻하며, 실제 시설 coverage·빈도 결합·IR/F-N 승격을 뜻하지 않는다.

### 재고 방출과 양단 파열의 추가 계약

`InventoryReleaseExportRequest`(`prism.equipment_inventory_export_request.v1`)는 기화기·재액화기처럼 사고 시 설비 재고가 방출되는 사건을 위한 요청이다. `instantaneous_inventory`는 provider가 `inventory_depletion`을 선언해야 하고, `inventory_over_600s`는 정확히 600초 이력과 `inventory_over_600s` 종료근거를 요구한다. 두 모드 모두 PRISM이 누출 구경이나 지속시간을 역산하지 않는다. 새 adapter의 대기 밸브 면적은 진단 계산에만 사용되고 failure opening으로 packet에 기록되지 않는다. 이전 packet이 진단 면적 메타데이터를 가지고 있는 경우에도 frequency binding은 그 값을 문헌 hole 구경과 비교하지 않는다.

`TwoSidedReliquefierProvider`는 하나의 공유 finite-volume 상태와 두 개의 명시적 대기 endpoint를 계산한다. 두 endpoint는 같은 `event_id`, component, 재고, duration을 가지지만 서로 다른 port와 방향을 유지하며 `prism.resolved_release_set.v1`로 묶인다. 양단 set의 두 endpoint가 모두 있어야 coverage에 들어가며, 한 endpoint를 복제해 양단 파열을 흉내 낼 수 없다. 현재 consequence worker는 바람과 반대인 endpoint의 upwind handoff를 자동 회전하지 않고 거부한다. 압축성·고마하 출구와 양방향 plume 상호작용은 후속 개발 항목이다.

검증 명령은 다음과 같다.

```powershell
$worklist = "results/20261009/provider_evidence/generic_lh2_provider_release_worklist.json"
python scripts/audit_provider_catalog_family_coverage.py `
  --provider-worklist $worklist `
  --accidental-catalog results/20261014/combined_accidental_provider_release_catalog_v5.json `
  --emergency-relief-catalog results/20261012/structural_emergency_relief_provider_catalog.json `
  --two-sided-catalog results/20261014/structural_two_sided_provider_catalog.json `
  --output results/20261014/combined_provider_catalog_family_coverage_v5.json
```


### provider 종료근거와 실제 지속시간 바인딩

branch packet의 `termination_basis`와 `duration_s`는 이제 피해 계산 요청에 직접 연결된다. `examples/provider_request_defaults_liquid_provider_duration.json`의 `provider_declared/provider_duration` 문맥을 사용할 때만 이 연결이 활성화된다. basis가 없거나 고정 시간과 provider 시간이 충돌하면 요청을 거절한다. provider의 시계 breakpoint는 `evaluation_times_s`에 합치지만 source history를 연장하지 않는다. 이 규칙으로 `reviewed_isolation_success` branch는 0.15 s, `synthetic_diagnostic_horizon` branch는 0.50 s를 보존한다. 한 저장탱크의 두 branch는 `EXECUTED_OPERATOR_LIMITED`로 실제 chain까지 실행되었지만, 합성 확률은 현장 차단 신뢰도가 아니다. 전체 catalog는 24개 initiating event 중 7개 branch만 request에 exact-match되고 21개 branch가 미계산이다.

## 차단 성공·실패 branch catalog 진단

`build_layered_tank_isolation_branches.py`는 하나의 initiating event 아래에 조건부 `isolation-success`와 `isolation-failure` provider packet을 함께 만드는 구조를 시험한다. branch 확률은 catalog에서 별도로 기록하며, 합이 1이 되지 않으면 누락분을 자동으로 물리 계산하지 않고 coverage gate에서 보류해야 한다. 이번 합성 실행은 저장탱크 5개 event에 성공·실패 10개 branch를 요청했다. 7개 branch가 생성되었고 3개는 외부 solver의 양수 셀 질량 오류로 `UNCOMPUTED`에 남았다. event 기준으로는 24개 중 4개가 적어도 한 branch와 exact-match되었다.

성공 branch는 provider의 `isolation_success` 종료근거와 닫힘 뒤 0 유량 확인을 요구하고, 실패 branch는 `isolation_failure_diagnostic_horizon`을 사용한다. 성공확률 0.99·실패확률 0.01은 branch 합계 계약을 시험하기 위한 합성 입력이다. 이 catalog는 문헌 initiating-event 빈도를 새로 만들지 않으며, provider packet 승격·현장 차단 신뢰도·시설 IR/F-N 계산을 허용하지 않는다. 결과는 `results/20261011/layered_tank_isolation_branches_all/provider_branch_catalog_coverage.json` 및 `campaign_verification.json`에서 확인한다.
