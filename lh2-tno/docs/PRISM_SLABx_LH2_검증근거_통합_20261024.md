# PRISM의 SLABx-LH2 검증근거 통합 기록

## 목적

PRISM은 설비 상태에서 사고 방출, 누출 확산, 점화·피해 원자까지의 경로를 진단한다. 외부
`SLABx-LH2` 결과는 이 경로 중 **극저온 수소 풀과 옥외 확산·LFL 결과를 비교하는 피해영향
구성요소**의 근거로 통합한다. 이 기록은 외부 결과를 PRISM의 사고 방출원이나 사고빈도로
승격하지 않도록 경계를 고정한다.

## 입력과 재현

통합 명령은 다음과 같다.

```powershell
python scripts/audit_slabx_lh2_validation.py `
  --results "C:\Users\lyul\Desktop\DocuData\SLABx_LH2\slabx-lh2-v0.1.2-rc\slabx-lh2\paper_results\results.json" `
  --audit "C:\Users\lyul\Desktop\DocuData\SLABx_LH2\논문화\KCI_pool_source_2026-10-09\results\audit.json" `
  --source-root "C:\Users\lyul\Desktop\DocuData\SLABx_LH2" `
  --source-file "slabx-lh2-v0.1.2-rc\slabx-lh2\paper_results\results.json" `
  --source-file "slabx-lh2-v0.1.2-rc\slabx-lh2\paper_results\pytest_full.txt" `
  --source-file "slabx-lh2-v0.1.2-rc\slabx-lh2\paper_results\run_manifest.txt" `
  --source-file "논문화\KCI_pool_source_2026-10-09\results\audit.json" `
  --source-file "핸드오프\VALIDATION.md" `
  --output results/20261024/slabx_lh2_validation_audit_v1.json
```

결과는 [`slabx_lh2_validation_audit_v1.json`](../results/20261024/slabx_lh2_validation_audit_v1.json)에
저장한다. 결과·재현감사·선택한 원자료의 SHA-256을 함께 보존하므로, 파일이 바뀌면 같은
근거로 간주하지 않는다.

## 확인된 값

| 항목 | 결과 |
|---|---:|
| SLABx-LH2 / SLABx 버전 | 0.1.2 / 1.0.6 |
| 재현성 감사 | PASS, 12개 check |
| FFI 비교 사례 | 6 |
| FLACS 비교 행 | 6 |
| 측정자료 설치 플래그 | true |
| 풀 반경 중앙 비율 | 1.0305005693 |
| LNG 음성 대조 변화 | 0.0% |
| 최대 시나리오 질량잔차 | 1.77×10⁻¹² kg |
| 반복 실행 inventory 차이 | 0 kg |

따라서 이 입력은 `RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE` 상태로 기록된다. 이는
SLABx-LH2 결과가 선언된 적용범위에서 재현·비교·질량 보존 검사를 통과했다는 뜻이다.

## PRISM 완료 감사 연결

`build_ijhe_completion_audit.py`에
`--slabx-validation-evidence results/20261024/slabx_lh2_validation_audit_v1.json`을
주면 `diagnostic_slabx_lh2_validation_evidence` 검사가 추가된다. 최신
[`ijhe_completion_audit_native_generic_scope_vertical_v20.json`](../results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v20.json)은
29개 PASS 검사·5개 BLOCKED 검사(상위 차단사유 4개)인 `INCOMPLETE_EVIDENCE`다. exact-cache realtime benchmark 진단도 별도로 소비해 20/20 cache hit, 중앙 31.47 ms, p95 33.23 ms를 기록하지만 fresh physics 2,685.50 ms에는 1 Hz 주장을 하지 않는다. SLABx 검사는 PASS이지만
`diagnostic_only=true`이다.

이 연결로 닫히는 범위는 다음과 같다.

- 극저온 수소 풀 반경·증발 및 옥외 확산/LFL 비교 결과의 추적성
- 외부 모델의 질량 보존과 반복 실행 차이의 추적성
- 외부 결과 파일, 재현 감사, 원자료의 해시 기반 재현성

다음 항목은 여전히 닫히지 않는다.

- 설비 사고 방출 packet의 적격 provider 판정과 개시 빈도
- 점화·화재·폭발·blast·IR/F-N의 독립 검증
- 시설 전체 QRA와 현장 사고빈도 학습
- 실내, DDT/폭굉, 장애물·지형 등 SLABx 선언범위 밖의 물리

따라서 SLABx 결과는 29개 진단 사건의 방출→최종피해 연결에 사용되는 **피해영향 구성요소
근거**이며, 시설 연간 IR/F-N이나 IJHE 완성 판정을 직접 열지 않는다. 상태 장부에는
`physical_validation_claim=false`, `frequency_inference_performed=false`,
`facility_qra_claim=false`를 보존한다.
