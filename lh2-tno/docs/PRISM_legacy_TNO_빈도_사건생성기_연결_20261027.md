# PRISM의 기존 TNO 빈도·사건 생성기 연결

기준일 2026-10-27. 이번 변경은 기존 외부 TNO taxonomy의 `resolve_frequency()`와
`enumerate_scenarios()`가 만든 결과를 PRISM의 `FrequencyEvent` 계약으로 넘기는
선택형 경계를 추가한 것이다. 외부 TNO 코드를 복사하거나 수정하지 않는다.

## 연결 방식

기존 TNO가 먼저 설비 목록과 운전 조건에서 사고 시나리오를 생성한다.
그 결과를 JSON으로 내보내고, PRISM에 다음 두 가지를 명시적으로 공급한다.

1. 각 `scenario_id`를 PRISM 시설의 `component_id`로 연결하는 매핑
2. 실행한 외부 taxonomy 파일의 SHA-256

PRISM은 이 경계에서 연간 빈도를 다시 계산하지 않는다. 기존 generator가 이미
적용한 개수·길이·2차 파손 계수를 그대로 보존하고 `exposure_multiplier=1`로
기록한다. `CONTINUOUS`는 기존 구멍 직경을 가진 `hole`, `INSTANTANEOUS`는
`instantaneous_inventory`로만 옮긴다. `release_path`, `physics_route`, 등급,
proxy 출처는 별도 sidecar에 남긴다.

주요 구현은 다음과 같다.

- `src/lh2_tno/legacy_frequency_bridge.py` — 외부 scenario export를 `FrequencyEvent`로 변환
- `attach_precomputed_events()` — 변환된 사건을 기존 `FrequencyPlan`에 명시적으로 부착
- `ResearchPipeline.legacy_frequency_events()` — 시설 ID를 확인하는 내부 진입점
- `ResearchPipeline.legacy_frequency_plan()` — 사건을 붙인 campaign용 plan과 감사 sidecar를 함께 생성
- `scripts/bridge_legacy_tno_frequency.py` — 일반 JSON export 연결 CLI
- `scripts/audit_legacy_tno_frequency_bridge.py` — 지정한 외부 `taxonomy.py`를 실제 실행하는 감사 CLI

간단한 campaign 연결 예시는 다음과 같다.

```python
from lh2_tno.legacy_frequency_bridge import attach_precomputed_events, bridge_digest
from lh2_tno.frequency import FrequencyPlan

events, bridge_audit = pipeline.legacy_frequency_events(
    legacy_rows, exact_scenario_to_component,
    source_sha256=legacy_taxonomy_sha256,
    basis=per_scenario_basis,
)
plan = attach_precomputed_events(
    FrequencyPlan.model_validate_json(frequency_plan_json),
    events,
    provenance=(
        f"legacy bridge; source_sha256={bridge_audit['source_sha256']}; "
        f"bridge_digest={bridge_digest(bridge_audit)}"
    ),
)
campaign = RiskCampaign(..., frequency_plan=plan, event_routes=routes)
result = pipeline.facility_risk(campaign)
```

`routes`에는 event ID별로 provider 방출 요청 또는 명시적 `uncomputed_reason`을
넣는다. 따라서 사건을 부착하는 것과 피해 계산을 완료하는 것은 별도 단계이며,
빠진 provider 경계는 0으로 바뀌지 않는다.

## 실제 감사 결과

현재 외부 TNO 프로젝트의 `TNO_SYSTEM/코드/taxonomy.py`를 직접 실행해 합성 LH2
인수기지 예제를 만들었다. `taxonomy.enumerate_scenarios()`가 생성한 **65개
시나리오를 65개 PRISM event로 변환**했고, 저장탱크·이송라인·펌프·밸브·기화기
5개 설비 ID를 명시적으로 매핑했다.

결과 파일:

[`results/20261027/legacy_frequency_bridge/verification.json`](../results/20261027/legacy_frequency_bridge/verification.json)

외부 event를 기존 campaign에 실제로 부착해 공통 binding→피해→IR/F-N 경계를
통과시킨 계약 검사는 [`campaign_integration_verification.json`](../results/20261027/legacy_frequency_bridge/campaign_integration_verification.json)에 기록했다. 이 검사는 합성 1개 사건의 연결 확인이며, provider 자격·독립 물리검증·시설 전체 QRA를 열지 않는다.

재현 명령:

```powershell
python scripts/audit_legacy_tno_frequency_bridge.py `
  --legacy-code "C:\\Users\\lyul\\Desktop\\DocuData\\TNO_위험분석모듈\\TNO_SYSTEM\\코드" `
  --output results/20261027/legacy_frequency_bridge/verification.json
```

감사 원장은 외부 taxonomy의 source hash, generator/resolver 이름, event 수,
방출 종류, 설비 매핑, 각 event의 원래 빈도를 보존한다. `frequency_inference_performed=false`,
`provider_packet_created=false`, `facility_qra_promotion=false`도 함께 기록한다.

## 이 연결이 의미하는 것

이제 PRISM의 선택형 LH2 경로가 자체 catalogue뿐 아니라 **기존 TNO 사건 생성
결과를 같은 event 계약으로 받아 기존 campaign 실행기에 직접 넣을 수 있다.**
`precomputed_events`가 붙은 `FrequencyPlan`은 이벤트만 외부 결과로 대체하고,
설비 scope·제외 목록·port 방향 검사는 PRISM이 다시 확인한다. 그 다음 provider
방출 이력, 차단·재고 소진 근거, SLABx-LH2, 점화·기상·인구·IR/F-N 계산은
기존 PRISM 계약을 그대로 사용한다. 결과에는 `event_catalog.mode`, 외부 rate
산술의 주체, PRISM consequence/IR-FN 실행 주체, 이벤트 catalogue digest가
함께 남는다.

따라서 이 연결에서 각 모델의 역할은 분리되어 있다. 외부 TNO generator는
사건과 빈도를 제공하고, 설비 provider/공정 모델은 실제 방출 경계와 종료를
제공하며, SLABx-LH2와 점화·기상·인구 모델은 피해를 계산하고, PRISM campaign
evaluator는 이 결과를 한 번씩 가중해 위험도와 F-N을 합산한다. PRISM이 외부
빈도를 다시 계산하거나 단순한 사건명으로 설비를 추정하지 않는다.

원시 입력만 있고 provider 방출이 없는 경우에는 저장탱크/압력용기 primitive만
검토된 vessel source-input binding으로 연결된다. 배관·밸브·플랜지·계기 등은
provider-resolved release가 없으면 `UNCOMPUTED`로 남는다. 외부 catalogue가
선택된 설비 중 일부만 포함하면 결과의 `scope_gap_component_ids`에 남기고
선언 범위와 시설 전체 QRA를 완전하다고 표시하지 않는다.

다만 scenario export만으로 실제 누출 방출이 만들어지는 것은 아니다. 설비별
provider packet과 명시적 종료 근거가 없으면 피해 계산은 `UNCOMPUTED` 또는
증거 요청으로 남는다. 외부 TNO proxy 빈도도 실측 사고빈도로 승격하지 않는다.
이 연결은 기존 사건 생성기를 사용할 수 있게 한 것이며, 독립 물리검증·qualified
provider·엄격한 사고범위·시설 전체 QRA의 네 가지 문턱을 닫았다는 뜻이 아니다.
