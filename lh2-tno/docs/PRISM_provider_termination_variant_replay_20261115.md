# 동일 사고 ID의 provider replay 선택 규칙 (2026-11-15)

새 `LayeredTank` isolation branch는 기존 `LH2_VESSEL AREA_0.01%`와 같은 사건 ID를
사용하지만 provider 결과 digest와 종료 기준이 다르다. 기존 증거 카탈로그는 사건 ID가
같으면 무조건 중복으로 차단했기 때문에, 동일 개구의 서로 다른 provider replay를
시설 case가 정확히 선택할 수 없었다.

이번 변경에서는 다음 규칙을 적용했다.

1. 같은 사건 ID라도 `provider_result_digest`가 다르면 모두 catalog에 보존한다.
2. 같은 사건 ID와 같은 digest가 반복되면 여전히 오류로 처리한다.
3. 방출경계 감사는 consuming case의 `provider_result_digests`와 정확히 일치하는
   catalog row를 선택한다.
4. digest가 하나로 선택되지 않으면 `provider_termination_evidence_ambiguous`로
   fail-closed 한다.

따라서 이번 union의 `AREA_0.01%` case는 새 isolation packet digest
`3d737384a6d02cad8877da680ccaaf78dbe751d57b3ccc2b14683d51ecaef6fd`를 선택하고,
provider `reviewed_isolation_success` 경계가 `VALID`로 확인된다. 기존 재고소진 replay도
삭제하거나 덮어쓰지 않는다.

## 최신 재감사 결과

- provider termination catalog: 35 rows, 34 event IDs, errors 0
- 시설 release-boundary audit: 44 cases, 32 provider-evidence-valid, 10 not supplied,
  2 invalid, strict eligible 3, blocked 41
- IJHE audit: 53 checks, 48 PASS, 5 BLOCKED, `INCOMPLETE_EVIDENCE`
- facility IR/F-N promotion: `false`

새 isolation packet을 추가로 보존한 것이 provider qualification이나 독립 물리검증을
의미하지는 않는다. 기존 사건의 대체가 아니라, 동일 사건 ID 아래의 provider replay를
digest로 구분하는 추적성 개선이다.

재현 명령은 다음과 같다.

```powershell
python scripts/build_provider_termination_evidence_catalog.py `
  --storage-catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --additional-storage-catalog-dir results/20261115/vertical_inventory_handoff_campaign/termination_evidence `
  --additional-storage-catalog-dir results/20261115/native_lh2dt_frequency_case_isolation_current `
  --inventory-provider-responses results/20261009/equipment_inventory_campaign/provider_responses.json `
  --inventory-resolved-releases results/20261009/equipment_inventory_campaign/resolved_releases.json `
  --output results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff_isolation_current.json

python scripts/audit_release_boundary_cases.py `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --facility-evidence-request results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json `
  --provider-termination-evidence results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json
```
