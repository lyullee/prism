# PRISM 외부 LH2 설비 provider 검증 감사 기록 (2026-10-09)

## 목적

외부 액화수소 디지털트윈이 자체적으로 물리모델 검증을 통과했는지와, 그 모델이 실제 설비의 방출·피해 계산에 바로 연결될 수 있는지는 서로 다른 질문이다. 이 기록은 두 질문을 분리해 PRISM이 자동으로 판정하도록 만든 `provider_evidence` 경계의 결과를 보존한다.

감사기는 외부 solver를 import하지 않는다. 외부 provider가 내보낸 JSON과 검증 노트의 상태, 개수, 원자료 해시만 읽는다. 따라서 이 단계에서 screening 기본값이나 관측 후보를 PRISM `Facility`로 승격하지 않는다.

## 실행

```powershell
python lh2-tno/scripts/audit_external_provider.py `
  --provider-root "<외부 LH2 디지털트윈 모델 루트>" `
  --output provider_evidence_audit.json
```

실제 검사센터 provider 실행 결과는 다음 파일에 저장했다.

`results/20261009/provider_evidence/center_provider_audit.json`

사고 방출 계약을 재귀적으로 확인한 최신 결과는 다음 파일이다.

`results/20261009/provider_evidence/center_provider_audit_with_release_inventory.json`

외부 원자료는 저장소에 복사하지 않고 다음 모델 루트에서 읽었다.

`C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델`

## 판정

| 항목 | 결과 |
|---|---:|
| PRISM 감사 상태 | `PARTIAL_PROVIDER_EVIDENCE` |
| provider 자체 전체 회귀 | 822건 통과 기록 |
| 센터 자산 바인딩 | `false` |
| 전방 비교 허용 | `false` |
| 파라미터 요청 | 89건, 값·검토상태 미확정 |
| 운전시퀀스 | 4개 시나리오, 52행 |
| 물리 명령시간 미확정 | 52행 |
| 확인된 명령 tag map | 0건 |
| 사고 방출 packet 후보 | 0건 |
| 사고 방출 계약 적격 packet | 0건 |
| 운전·스크리닝 유량만 있는 JSON | 24개 |
| 시설 전체 연간 위험 | 보류 |

`center_port_mappings.json`에 `confirmed`와 `candidate_mapping`이 함께 존재하더라도, 이는 일부 포트 역할 관찰의 상태이다. 전체 ordered component chain, 실제 끝점, 밸브 명령, 수치 파라미터와 전방 비교 계약이 모두 준비되었다는 뜻으로 해석하지 않는다. 감사기는 각 상태를 원자료 그대로 집계하고, provider가 명시한 `center_binding_ready`와 `forward_comparison_allowed`를 승격 관문으로 사용한다.

## 차단 사유

현재 결과의 차단 사유는 다음과 같다.

1. provider가 센터 자산 바인딩 준비를 선언하지 않았다.
2. provider가 전방 비교를 허용하지 않았다.
3. 파라미터 값과 외부 검토 상태가 미확정이다.
4. 검토 완료된 운전 명령 tag map과 절차–P&ID/PLC map이 없다.
5. 운전시퀀스의 물리 명령 시간이 없다.
6. provider 루트에서 `event_kind=accidental_leak`와 고장 개구·시간 이력·질량/엔탈피 장부를 함께 가진 사고 방출 packet을 찾지 못했다. 유량 열만 있는 정상 운전·스크리닝 JSON 24개는 사고 방출로 승격하지 않았다.

이 차단은 오류가 아니라 안전한 `fail-closed` 결과다. 확인되지 않은 항목을 0, 정상, 또는 자동 계산 가능으로 바꾸지 않는다.

## PRISM에서 허용되는 다음 단계

provider가 다음 자료를 외부 검토와 함께 보강하면 같은 감사기를 다시 실행할 수 있다.

- 자산별 실제 모델 파라미터와 출처·개정·검토자
- P&ID/PLC 기준의 ordered component chain과 양 끝 포트
- 명령 tag, 명령값, 실제 적용 시간축, 응답·차단 상태
- 방출 포트의 위치·방향·상(액체/기체/2상)·종료 조건
- provider 질량·에너지 장부와 방출 이력의 source digest
- `provider_export_schema`가 명시된 사고 방출 packet: `event_kind=accidental_leak`, 고장 개구, 설비·포트·위치, `steps`, 지속시간, 누적 질량·엔탈피, source/result digest를 포함해야 한다.
- 비교에 승인된 관측 시간축과 압력 기준·단위·센서 위치

감사 상태가 `EXECUTABLE_PROVIDER`가 된 뒤에도 PRISM의 일반 `EquipmentManifest`와 `FrequencyPlan` 관문을 통과해야 한다. 이후에만 방출 이력을 `ConsequenceRequest`에 연결하고, 시설 IR/F-N 합산을 시도한다. 문헌 빈도는 별도의 입력으로 유지하며 센서 신호로 자동 학습하지 않는다.

## 방출 packet을 PRISM request로 연결하는 단계

provider가 flat JSON `provider_export_schema=prism.resolved_release.v1`을 제공하면 `src/lh2_tno/provider_release.py`의 `load_provider_release()`가 `ResolvedGasRelease` 또는 `ResolvedLiquidRelease`로 strict 검증한다. 이어 `build_consequence_request_from_provider_release()`가 설비 ID·포트·위치·재고·provider 지속시간을 request에 복사하고, 사용자가 선언한 weather·ignition·domain·평가시계·종료근거를 결합한다. 이 함수는 source 입력, initiating frequency, 다른 release set을 defaults에서 받지 않으며, 충돌은 오류 또는 `uncomputed`로 남긴다.

여러 packet은 다음 CLI로 request catalog로 만들 수 있다.

```powershell
python lh2-tno/scripts/build_provider_request_catalog.py `
  --provider-release-catalog provider_releases.json `
  --request-defaults lh2-tno/examples/provider_request_defaults.json `
  --output provider_request_catalog.json
```

이 결과는 아직 시설 위험 계산이 아니다. `EquipmentManifest`의 outward port/phase·좌표와 `FrequencyPlan`의 사고 크기가 `bind_event()`로 exact-match되어야 하며, 그 뒤에야 provider request가 방출→확산→점화→피해→IR/F-N campaign으로 전달된다. provider duration과 종료근거가 맞지 않는 packet, 정상 vent, 양단 파열 set을 단일 packet으로 표현한 자료는 자동 보정하지 않는다.

`examples/provider_release_catalog_synthetic.json`은 위 adapter의 동작만 재현하는 합성 입력이다. 실제 센터 또는 일반 액화수소시설의 방출·빈도 증거로 사용하지 않는다.

추가로 합성 액체 packet을 `provider_release → EquipmentManifest/FrequencyPlan exact-match → campaign backend`까지 전달했다. `LH2_VESSEL AREA_0.01%` 한 건이 실행되어 source, SLABx-LH2/DynamicLH2PoolX, 확산, 점화·피해와 known IR 기여가 생성되었고, 다른 9개 문헌 개구는 `UNCOMPUTED`로 남았다. case 약 1.61초, campaign 약 1.81초이며 `EXECUTED_OPERATOR_LIMITED`, 시설 전체 IR/F-N `WITHHELD`이다. 이 결과는 adapter와 전체 연결의 합성 진단이지 실제 설비 QRA가 아니다. 실행 기록은 `results/20261009/provider_release_full_chain_diagnostic/`에 둔다.

이 진단의 저장된 risk atom에 문헌 빈도 불확실성도 적용했다. `examples/provider_full_chain_frequency_uncertainty.json`은 네 시나리오(자산별 shared p05/p95와 사건별 independent p05/p95)를 선언하고 물리는 재실행하지 않는다. known-contribution IR 범위는 p05 `3.7383e-06`/년에서 p95 `1.1303e-03`/년으로 바뀌지만, 미계산 사건과 합성 경계가 있으므로 시설 credible interval로 승격하지 않는다.

## 재현·해석 주의

- provider의 822개 회귀 통과는 provider 내부 단위·상태식·연결 보존성 검증의 범위다.
- 이는 검사센터 실측 일치, 실제 누출 빈도, 실제 시설 방출량, 시설 전체 IR/F-N 검증을 의미하지 않는다.
- screening closure의 전달 가능한 기본값은 후보 계산과 데이터 요청 우선순위에만 사용할 수 있다.
- 누락된 parameter, tag, 위치, 방향, 명령시간은 PRISM이 추정하지 않는다.
- 외부 provider가 갱신되면 감사 결과의 `source_digest`를 비교하고, 이전 결과와 섞지 않고 새 실행으로 기록한다.
- 감사기의 `release_evidence`는 JSON 구조와 키를 세는 1차 증거 인벤토리이며, 적격 후보에는 이제 `load_provider_release()`의 전체 PRISM 경계 검증(출구 연속성, 질량·엔탈피 장부, 시간 순서, 수직 handoff와 유한값)을 다시 적용한다. 따라서 형식만 비슷한 packet은 `strict_validation_failures`로 남고 승격되지 않는다. 적격 packet이 생겨도 PRISM 계약 검증과 `FrequencyPlan` exact-match를 별도로 통과해야 한다.
