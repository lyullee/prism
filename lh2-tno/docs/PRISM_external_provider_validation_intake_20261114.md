# PRISM 외부 provider 검증근거 intake (2026-11-14)

이번 intake는 액화수소 디지털트윈과 공개 실험자료에서 발견한 검증 결과를
provider 사고 방출 자격으로 잘못 승격하지 않도록 분리해 기록한다. 입력은
PRESLHY 고정 노즐 기체 방출, NASA LH2 탱크 outflow·venting, ortho-para
열역학, K-Site 조건 전이, 검사센터 검증 gate 자료다.

실행 결과는
[`external_provider_validation_intake.json`](../results/20261114/external_provider_validation_intake.json)이다.

| 항목 | 결과 |
|---|---:|
| 검토한 외부 근거 | 8건 |
| 외부 provider artifact | 7건 |
| `actual` 원점 artifact | 0건 |
| `model_prediction`/합성 artifact | 7건 |
| provider qualification sidecar | 0건 |
| exact provider 검증 매칭 | 0건 |
| provider 승격 가능 근거 | 0건 |

자료별로 지원 범위와 제외 범위를 모두 저장했다. 예를 들어 NASA D-3256은
LH2 탱크의 열입력·정압 outflow 경계를 비교하는 데 쓸 수 있지만, 현재 시설의
사고 event·component·port와 일치하는 release packet이나 차단·재고소진
qualification은 아니다. PRESLHY E31 자료는 기체 고정노즐 비교로 유용하지만
LH2 PSV capacity 근거가 아니다. 검사센터 자료는 raw historian과 approved
field record gate가 아직 닫혀 있음을 확인하는 증거다.

따라서 intake의 최상위 플래그는 모두 `false`다.

- `provider_qualification_claim=false`
- `accident_release_validation_claim=false`
- `independent_physical_validation_claim=false`
- `facility_qra_claim=false`
- `frequency_inference_performed=false`

통합 validation matrix에도 이 intake를 별도 domain으로 연결했다.
[`validation_evidence_matrix_with_provider_intake.json`](../results/20261114/validation_evidence_matrix_with_provider_intake.json)은
8개 domain을 보존하고 `FACILITY_QRA_WITHHELD`를 유지한다. 새 domain은
component/boundary evidence의 추적성만 추가하며, 방출 지속시간·격리·재고소진,
문헌 빈도, 시설 IR/F-N을 만들어 내지 않는다.

재현 명령:

```powershell
python scripts/audit_external_provider_validation.py `
  --manifest examples/external_provider_validation_manifest.json `
  --provider-artifact-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델\tmp_native_contract" `
  --output results/20261114/external_provider_validation_intake.json

python scripts/build_validation_evidence_matrix.py `
  --pool-record results/20261009/validation_evidence/dynamiclh2poolx_stage_c_prism_record_git_blob.json `
  --equipment-audit results/20261009/validation_evidence/equipment_validation_audit_live.json `
  --facility-assessment results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/facility_assessment.json `
  --native-contract results/20261022/lh2dt_native_contract_audit_native_catalog.json `
  --slabx-validation results/20261106/slabx_lh2_validation_audit_recomputed.json `
  --ijhe-audit results/20261114/ijhe_completion_audit_union_fullscope_hazop_port_bound_state_bound.json `
  --dynamiclh2poolx-evidence results/20261014/dynamiclh2poolx_evidence_audit.json `
  --external-provider-validation results/20261114/external_provider_validation_intake.json `
  --output results/20261114/validation_evidence_matrix_with_provider_intake.json
```

이 결과는 기존 네이티브 모델의 계산 경로를 폐기하지 않는다. 대신 실제
시설용 provider 자료가 들어올 때 같은 event/component/port와 source/result
digest를 대조하고, 같은 운전 영역의 독립 물리검증을 통과해야만 다음 단계로
갈 수 있다는 입구를 명확히 한다.
