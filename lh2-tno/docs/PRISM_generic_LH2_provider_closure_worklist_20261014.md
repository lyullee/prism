# 일반 LH2 설비 방출 종료 증거 작업목록

이 문서는 2026-10-14 현재 일반 옥외 LH2 예제의 provider 방출 종료 감사를 기준으로 작성했다. 현재 24개 사건 중 23개는 provider 종료 시계와 질량 장부가 확인되어 `CLOSURE_READY_FOR_QUALIFICATION` 상태이고, 1개는 물리적 종료 근거가 없어 `CLOSURE_EVIDENCE_OPEN`으로 남아 있다.

## 열린 사건

| 사건 | 현재 종료 상태 | 현재 관찰시간 | 방출 질량 | 열려 있는 핵심 입력 |
|---|---|---:|---:|---|
| `ambient-vaporizer/G2` | `inventory_over_600s` | 600 s | 2.70255e-05 kg | 공정측 상태 이력, 연결 재고, 실제 차단 응답 |

G3과 G6은 새 외부 `lh2dt` packet으로 재실행하여 다음처럼 종료 근거를 닫았다.

| 사건 | 종료 근거 | provider 시간 | 방출 질량 | 개구 |
|---|---|---:|---:|---:|
| `ambient-vaporizer/G3` | `inventory_depletion` | 0.1 s | 2.88876e-05 kg | 0.0100 m |
| `reliquefier/G6` | `inventory_depletion` | 0.4 s | 5.42353e-06 kg | 0.0025 m |

두 packet은 provider 전체 재고와 경계의 방출 가능 재고를 구분한 질량수지를 포함하며, 정확한 사고 개구를 보존한다. 이 두 건은 종료 경계만 닫힌 것이고, provider 자격화·독립 물리검증·시설 QRA 승격은 여전히 보류다.

G2 packet의 `provider_result_digest`와 전체 질량수지는 기록되어 있지만, 잔류 재고가 있는 고정 관찰창을 실제 방출 종료로 바꾸지는 않는다. 따라서 G2의 빈도, 시설 연간 IR/F-N, 물리검증 자격은 자동으로 열리지 않는다.

G2를 같은 동적 증발기에서 `inventory_depletion`으로 다시 계산하는 것은 별도 후보 packet을 만들 수 있지만, 현재 문헌 빈도 행은 `inventory_over_600s` 사건으로 정의되어 있다. 새 종료근거를 기존 빈도 유형에 임의로 끼워 넣지 않도록 이 후보는 캠페인에 결합하지 않는다. G2를 닫으려면 provider 종료근거와 함께 해당 사고 유형에 맞는 검토 빈도 포트가 필요하다.

## 다음에 받아야 할 provider 자료

각 사건은 아래 조건을 모두 만족하는 새 `prism.resolved_release.v1` packet과 같은 결과를 가리키는 `verification.json`을 요구한다.

1. 설비 provider가 소유한 공정측 상태 이력과 사고 포트 ID
2. 연결된 액체·기체 재고의 초기 질량, 유입·유출, 최종 잔류 질량
3. 차단 명령 시각, 실제 개도/유량 응답, 차단 성공 또는 실패 상태
4. 방출 종료를 결정한 provider 방법·버전·증거 ID
5. packet과 정확히 일치하는 결과 SHA-256
6. 독립 검증 자료 또는 명시적 검증 공백

재액화기 G6은 한쪽 출구만 확인해서 닫을 수 없다. 고장 모드가 영향을 준 모든 endpoint의 방출 이력과 공통 재고 장부가 함께 있어야 한다.

## 재현 명령

저장소 루트에서 다음처럼 `--packet-root lh2-tno`를 명시한다. packet evidence의 상대 경로가 `lh2-tno/results/...` 아래에 있기 때문이다.

```powershell
python lh2-tno/scripts/audit_generic_provider_release_closure.py `
  --packet-evidence lh2-tno/results/20261014/generic_lh2_provider_worklist_packet_evidence_isolation_contract_v4.json `
  --packet-root lh2-tno `
  --output lh2-tno/results/20261014/generic_lh2_provider_release_closure_isolation_contract_v4.json

python lh2-tno/scripts/export_generic_provider_closure_requests.py `
  --packet-evidence lh2-tno/results/20261014/generic_lh2_provider_worklist_packet_evidence_isolation_contract_v4.json `
  --packet-root lh2-tno `
  --output lh2-tno/results/20261014/generic_lh2_provider_closure_requests_isolation_contract_v4.json
```

두 결과는 각각 `23/24 ready, 1 open`과 `1 open provider request`를 반환해야 한다. 이 요청 파일은 기간·재고·빈도·자격을 추정하지 않으며, 자료가 들어오기 전에는 시설 QRA 승격을 허용하지 않는다.

## 완료 판정

G2에 provider-owned 종료 근거가 추가되면 24건 모두 `CLOSURE_READY_FOR_QUALIFICATION`으로 바꾼다. 이것만으로 실제 시설 위험도가 완성되는 것은 아니다. 이후에는 provider qualification, SLABx-LH2 독립 비교, 문헌 빈도 연결, 기상·점화·인구·IR/F-N 시설 원장의 별도 문턱을 통과해야 한다.

새 packet을 포함한 24건 재실행 결과는 [`generic_lh2_campaign_rebound_inventory_closure_v4_result.json`](../results/20261014/generic_lh2_campaign_rebound_inventory_closure_v4_result.json)에서 확인할 수 있다. G3·G6은 `EXECUTED`로 SLABx-LH2 경로까지 도달했고, 전체 캠페인은 다른 설비의 실패·운영제한·영역 미완료 상태를 그대로 보존한다.

