# PRISM native LayeredTank 문헌 빈도–격리 branch 연결 (2026-11-15)

## 이번 보완의 목적

기존 문헌 빈도 사례는 caller가 정한 짧은 시간에서 멈추는
`synthetic_diagnostic_horizon`을 사용했다. 이번 보완에서는 같은 문헌 사건과
같은 native LayeredTank를 사용하되, provider에 명시적인 격리 명령 시각과
격리 후 관찰 시각을 전달했다.

```text
문헌 LH2_VESSEL AREA_0.01% 빈도
  → exact 0.0127 m 저장탱크 사건
  → LayeredTank native outlet
  → 0.00005 s 격리 명령
  → 0.00005 s provider 관찰
  → strict liquid packet
  → SLABx-LH2/피해 chain
```

이 branch는 현장 차단 신뢰도를 추정하지 않는다. provider가 계산한 짧은
진단 branch를 그대로 전달했다는 의미이며, upstream 잔여 재고를 0으로 만들지
않는다.

## 재현 명령

프로젝트 폴더 `lh2-tno`에서 실행한다.

```powershell
python scripts/run_lh2dt_native_frequency_case.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --compiled-campaign results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/campaign.json `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output-dir results/20261115/native_lh2dt_frequency_case_isolation_current `
  --isolation-time-s 0.00005 `
  --post-isolation-observation-s 0.00005
```

결과는 `results/20261115/native_lh2dt_frequency_case_isolation_current/`에
저장된다. `verification.json`이 이 기록의 요약이며, `provider_response.json`과
`resolved_release.json`이 provider 원문과 strict 변환을 보존한다.

## 확인된 값

| 항목 | 결과 |
|---|---|
| 상태 | `PARTIAL_DECLARED_SCOPE` |
| 사건 | `generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%` |
| 문헌·provider 개구 | 모두 `0.0127 m` |
| 문헌 빈도 | campaign의 `LH2_VESSEL AREA_0.01%` 행 사용 |
| provider에서 빈도 추정 | `false` |
| provider 종료 basis | `reviewed_isolation_success` |
| 격리 명령 시각 | `0.00005 s` |
| 격리 후 관찰 시각 | `0.00005 s` |
| provider isolation success | `true` |
| provider 방출 지속시간 | `0.0001 s` |
| 초기 재고 | 약 `71.7644006 kg` |
| 격리 후 잔여 재고 | 약 `71.7643992 kg` |
| provider 질량 잔차 | `0 kg` |
| native export 시간 | 약 `155.7 ms` |
| 전체 campaign chain | 약 `146.1 s` |
| 방출→피해 chain | 실행됨 |
| 시설 전체 IR/F-N | 사용 불가 (`false`) |

## 해석

이 실행으로 한 사건에서 다음 세 가지를 함께 확인했다.

1. 문헌 사고빈도가 provider 결과에서 새로 만들어지지 않고 기존 빈도 원장에서
   그대로 전달된다.
2. 설비 provider가 계산한 격리 시각·관찰 시각·종료 basis와 질량 장부가 strict
   liquid release packet에 보존된다.
3. 해당 packet이 SLABx-LH2 기반 피해계산과 조건부 facility campaign까지
   도달한다.

그러나 이 결과만으로 전체 시설의 모든 사고가 격리된다고 볼 수 없다. 초기상태와
형상은 합성이고, branch의 격리 신뢰도·현장 차단자료·액적 비산 검증·전체 사고범위가
없다. 따라서 `provider_packet_promoted=false`, `physical_validation_claim=false`,
`facility_qra_claim=false`를 유지한다. 잔여 재고가 크므로 이번 결과는
`inventory_depletion` 사례가 아니며, 실제 재고 소진을 의미하지 않는다.

기존 bounded-horizon 결과는 `native_lh2dt_frequency_case_current/`에 역사적
진단으로 보존하고, 이번 격리 branch 결과를 최신 비교 대상으로 사용한다.
