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

실제 일반 LH2 설비에 대해 적격으로 승인된 provider packet은 0건이므로 실제 시설 coverage는 계속 `NO_EXACT_MATCH`다. 별도 합성 진단에서는 `lh2dt→SLABx-LH2` 결과를 저장탱크 `AREA_0.01%` 사건의 설비·포트·개구에 맞춰 `PARTIAL_EXACT_MATCH`(1/24)를 재현했다. 이 결과는 구조 연결을 확인하는 개발 증거이며, 합성 종료시계·재고·기상 때문에 실제 방출 이력이나 시설 위험으로 승격하지 않는다. 상세 결과는 `results/20261009/provider_evidence/generic_lh2_provider_catalog_coverage_storage_exact.json`이다.
