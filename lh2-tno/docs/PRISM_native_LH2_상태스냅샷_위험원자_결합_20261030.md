# PRISM native LH2 상태 스냅샷 결합 개발기록 (2026-10-30)

## 이번에 완성한 연결

기존 native LH2 결과에는 설비 상태가 `verification.json`에 있었지만, 위험 원자(`risk_atoms`)에는 상태가 직접 들어 있지 않은 경우가 있었다. 이제 각 사건의 설비 상태가 다음 네 단계를 모두 통과한다.

1. 설비 모델이 상태 스냅샷을 만든다. 예: 압력, 온도, 액체 비율, 상태 시각.
2. 액화수소 방출 모델이 그 스냅샷을 받아 방출 패킷을 만든다.
3. 방출 모델이 같은 스냅샷의 SHA-256 해시를 다시 보낸다.
4. PRISM 위험 원자가 방출 패킷과 함께 상태 스냅샷·해시를 저장한다.

따라서 나중에 결과를 볼 때 “어떤 설비 상태에서 나온 방출인가?”와 “그 방출 결과가 같은 상태를 사용했는가?”를 다시 확인할 수 있다. 이 결합은 계산 추적성을 높이는 기능이며, 합성 모델을 실제 현장 검증 자료로 바꾸거나 시설 전체 QRA를 자동 승인하지 않는다.

## 양단 파열 처리

재액화기 양단 파열처럼 한 사건에서 방출 종단이 두 개인 경우에는 `provider_state_snapshot_digests`에 종단별 확인 해시를 모두 기록한다. 두 해시는 같은 설비 상태 스냅샷과 일치해야 하며, 하나라도 다르면 캠페인 생성이 중지된다. 기존 단일 종단 사건은 호환성을 위해 `provider_state_snapshot_digest`를 계속 사용한다.

## 구현 파일

- `src/lh2_tno/consequences.py`: 상태 스냅샷과 다중 공급자 echo 해시 계약.
- `src/lh2_tno/campaign.py`: 위험 원자에 상태 스냅샷과 다중 echo를 기록.
- `scripts/bind_native_campaign_state_snapshots.py`: 검증된 packet 디렉터리와 캠페인을 결과 digest로 결합하는 fail-closed 컴파일러.
- `scripts/run_native_full_scope_union_assessment.py`: 이미 목표 시설 namespace로 결합된 확장 결과를 다시 namespace를 붙이지 않고 그대로 사용하도록 보완.

## 재현 방법

```powershell
python scripts/bind_native_campaign_state_snapshots.py `
  --campaign results/20261030/native_near_receptor_scope_packets_state_bound/campaign.json `
  --packet-root results/20261027/native_generic_scope_packets_state_bound `
  --output results/20261030/native_near_receptor_scope_packets_state_bound/campaign_state_bound.json `
  --audit-output results/20261030/native_near_receptor_scope_packets_state_bound/state_snapshot_campaign_binding_audit.json
```

그 다음 24개 기본 사건을 실행하고, 수직 벤트·재고 소진 확장 결과를 union한다. 최신 진단 원장은 다음 위치에 저장한다.

`results/20261026/native_full_scope_union_assessment/`

현재 확인값은 기본 24개 사건·96개 위험 원자와 확장 10개 사건을 합친 34개 사건·44개 case·176개 위험 원자다. 상태 스냅샷 결합은 34/34 사건에서 확인되었다.

## 현재 해석

- 문헌 빈도는 PRISM frequency catalogue에서 입력한다. 상태 스냅샷이나 센서 신호가 사고 빈도를 자동으로 학습하지 않는다.
- 캐시된 결과는 실시간 화면에 빠르게 제공할 수 있지만, 매번 새로 계산하는 SLABx-LH2 물리는 현재 1 Hz를 보장하지 않는다.
- 19개 case는 수치 결과가 있어도 공급자 경계가 operator-limited이므로 qualified provider packet으로 승격하지 않는다.
- 독립 물리검증, qualified provider evidence, 엄격한 전체 사고범위, 시설 전체 IR/F-N은 계속 차단 상태로 표시한다.

