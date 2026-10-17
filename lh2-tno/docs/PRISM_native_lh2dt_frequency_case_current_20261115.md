# PRISM 최신 native LayeredTank–문헌 빈도–시설 chain 진단 (2026-11-15)

## 목적

이번 실행은 한 개의 저장탱크 사고 사건에서 다음 연결을 현재 외부 모델 소스와
PRISM 코드로 다시 확인하기 위한 진단이다.

```text
검토된 문헌 사고빈도
  → exact opening 사건 선택
  → 외부 lh2dt LayeredTank 사고 방출 이력
  → PRISM strict ResolvedLiquidRelease
  → SLABx-LH2/풀·확산·점화·피해
  → 조건부 시설 campaign 원장
```

빈도는 provider나 센서에서 추정하지 않고, 이미 검토된 campaign의
`LH2_VESSEL AREA_0.01%` 행에서 읽었다. 따라서 이 실행은 현장 빈도 학습이나
시설 전체 QRA 승격이 아니다.

## 재현 명령

프로젝트 폴더 `lh2-tno`에서 다음을 실행한다.

```powershell
python scripts/run_lh2dt_native_frequency_case.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --compiled-campaign results/20261114/native_isolation_catalog_facility_chain_fullscope_hazop_port_bound/campaign.json `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output-dir results/20261115/native_lh2dt_frequency_case_current
```

외부 모델 root는 로컬 환경에 맞게 바꿔야 한다. 실행은 compiled campaign의
`generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%` route를
찾아 해당 route의 위치·기상·빈도 원장을 유지하고, 방출 이력만 현재 native
`LayeredTank.export_accident_history()`에서 생성한다.

## 실제 결과

결과 원본은 다음 다섯 파일이다.

- `results/20261115/native_lh2dt_frequency_case_current/provider_response.json`
- `results/20261115/native_lh2dt_frequency_case_current/resolved_release.json`
- `results/20261115/native_lh2dt_frequency_case_current/campaign.json`
- `results/20261115/native_lh2dt_frequency_case_current/campaign_result.json`
- `results/20261115/native_lh2dt_frequency_case_current/verification.json`

`verification.json`의 핵심 값은 다음과 같다.

| 항목 | 결과 |
|---|---|
| 실행 상태 | `PARTIAL_DECLARED_SCOPE` |
| 정확히 매칭한 사건 | `storage-shell/AREA_0.01%` |
| 문헌 개구 직경 | `0.0127 m` |
| provider 개구 직경 | `0.0127 m` |
| opening exact match | `true` |
| 문헌 빈도 사용 | `true` |
| provider에서 빈도 추정 | `false` |
| provider 질량 잔차 | `0 kg` |
| native source digest | `d7bec406d1c7b1a9c8b803b2dfd8a5c1f98a4c233c99b4330383ca08a4c462ce` |
| native 방출 계산시간 | 약 `263.7 ms` |
| 전체 campaign chain 시간 | 약 `176.1 s` |
| 방출→피해 chain 실행 | `true` |
| 시설 전체 IR/F-N 사용 가능 | `false` |
| provider 승격 | `false` |
| 물리검증 주장 | `false` |

### State-to-release inventory rebaseline

The compiled route contained an older state snapshot with an inventory of
`0.0284920619 kg`, while the current native LayeredTank initialization used by
the provider contains `71.76440057 kg`. The runner now constructs the snapshot
from the exact native initialization that produced the release, binds its new
digest into the accident request and consequence request, and records the old
digest and mass in `verification.json`. The regenerated packet reports
`state_snapshot_release_mass_match=true`; no value is silently copied into the
old artifact. The one-case mass audit is retained in
`examples/native_lh2dt_frequency_case_state_mass_audit_20261115.json`.

campaign 결과는 선택된 저장탱크 사건을 `EXECUTED_OPERATOR_LIMITED`로 기록하고,
문헌 빈도 `6.5×10^-4 year^-1`을 조건부 risk atom에 보존한다. 저장탱크의
방출 이력은 SLABx-LH2와 풀·확산·점화·피해 계산을 거쳐 risk atom으로 들어갔다.
조건부 facility campaign 전체의 `total_facility_annual_ir_low_high`와 F/N 값은
`null`이며, 이는 미계산·합성·운영자 제한 사례를 0 위험으로 바꾸지 않는
fail-closed 동작이다.

## 이 결과가 증명하는 것

1. 문헌 frequency row와 provider event ID가 같은 사고 key로 묶인다.
2. 문헌 opening과 native provider opening이 exact-match된다.
3. provider가 계산한 시간 이력과 질량 장부가 PRISM strict liquid packet으로
   변환된다.
4. 방출 packet이 SLABx-LH2 기반 피해 chain과 시설 campaign에 실제로 소비된다.
5. 상태·운전 모드·설비·port·HAZOP scenario ID가 campaign case에 보존된다.

## 이 결과가 아직 증명하지 않는 것

- 현재 시설의 실제 탱크 형상·재고·대기경계가 정확하다는 것
- 모든 시설 사고 개구와 주요 사고군이 계산되었다는 것
- 외부 provider가 현장용으로 qualified되었다는 것
- `synthetic_diagnostic_horizon` 종료가 실제 차단 또는 재고 소진을 의미한다는 것
- 액적 비산·airborne liquid과 pool footprint가 현장 자료로 검증되었다는 것
- 시설 전체 연간 IR/F-N이 완성되었다는 것
- 상태가 바뀔 때 fresh physics를 1 Hz로 계산할 수 있다는 것

특히 이번 exact `AREA_0.01%` 저장탱크 분기는 짧은 caller-declared horizon을
사용해 잔여 재고를 보존한다. 따라서 이 한 사건의 연결 성공을 전체 시설의
방출 종료 근거로 확대하지 않는다. 최신 전체 union에서 별도로 감사된 엄격한
방출경계·provider 자격·독립 물리검증·시설 IR/F-N 네 gate는 계속 닫혀 있다.

## IJHE에서의 사용 위치

이 결과는 방법론 논문에서 다음 그림 또는 표의 재현 사례로 사용할 수 있다.

- 문헌 initiating frequency와 digital-twin provider의 분리
- equipment release contract와 질량 보존 검사
- SLABx-LH2 consequence bridge
- 조건부 facility ledger와 fail-closed promotion gate
- native 계산시간과 전체 chain 처리시간

논문에서는 이를 `diagnostic integration case` 또는 `conditional campaign case`로
표기해야 하며, qualified facility-QRA 결과나 현장 검증값으로 표현하면 안 된다.
