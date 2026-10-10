# PRISM LH2 consequence backend chain 감사

## 목적

시설 위험 원장에 stage 이름만 남으면 어떤 모델이 어느 단계에서 사용되었는지와
양단 파열 같은 예외 경로가 빠졌는지를 한눈에 확인하기 어렵습니다. 이 감사는 저장된
campaign case와 별도 계약을 대조해 방출 이후 연결을 명시합니다.

표준 옥외 경로는 다음과 같습니다.

`LH2 설비 방출 → DynamicLH2PoolX pool/증발 → SLABx-LH2 near-field·확산 → cloud/receptor 관측 → PRISM 점화·피해 risk`

양단 파열은 두 출구를 공유 재고로 보존하므로 다음 별도 경로를 사용합니다.

`endpoint_a → endpoint_aggregation → endpoint_b → risk atoms`

## 실행

```powershell
python scripts/audit_consequence_backend_chain.py `
  --campaign-result results/20261026/native_full_scope_union_assessment/campaign_result.json `
  --backend-contract examples/lh2_consequence_backend_chain_contract.json `
  --output results/20261026/native_full_scope_union_assessment/consequence_backend_chain_audit.json
```

계약은 `prism.consequence_backend_chain_contract.v1`, 결과는
`prism.consequence_backend_chain_audit.v1`입니다. 감사는 각 case에서 선택된 경로의
stage elapsed time이 유한하고 0 이상인지, backend와 adapter digest가 있는지,
provider identity·종료·질량 장부·domain 결과가 있는지, 해당 event의 risk atom에
수용점 피해와 예상 사망 필드가 있는지를 확인합니다.

현재 결과는 다음과 같습니다.

- 44개 case 중 44개가 선언된 경로를 닫음
- 표준 경로 42개, 양단 파열 endpoint 경로 2개
- 필수 stage 8개, 차단 사유 0개
- `FULL_CONSEQUENCE_BACKEND_CHAIN_DIAGNOSTIC`

이는 저장된 실행의 연결과 처리시간을 검증하는 진단 결과입니다. provider packet이
합성·operator-limited이면 그대로 제한 상태를 유지하고, initiating frequency를
만들거나, SLABx-LH2의 제한된 component 검증을 전체 물리검증으로 확대하거나,
시설 IR/F-N을 승격하지 않습니다.

