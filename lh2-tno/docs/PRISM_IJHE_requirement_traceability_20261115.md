# PRISM v0.6.3 IJHE 요구사항 추적표 (2026-11-15)

이 문서는 PRISM의 선언된 일반 옥외 액화수소시설 범위를 요구사항 단위로 다시 확인한 최신 추적표다. 계산 결과가 존재하는 것과 실제 시설 QRA로 승격할 수 있는 것은 분리한다. 현재 권위 원장은 **34개 event, 44개 case, 176개 risk atom**이며 최신 vertical/inventory/isolation union IJHE 감사는 **60개 검사 중 55 PASS, 5 BLOCKED**인 `INCOMPLETE_EVIDENCE`다. 최신 감사에는 예측 facility-campaign quantitative-evidence gate와 외부 설비 모델 release intake가 포함되어, 증거가 없는 예측 요청이나 자격화되지 않은 모델 출력을 downstream 시설 집계로 넘기지 않는지 확인한다.

외부 `lh2dt` 모델 정본에서 탱크·배관·펌프·밸브·기화기·재액화기·벤트의 release-shaped export 7개를 확인했다. 이 7개는 포트·방출시간·질량·종료근거를 보존하지만 모두 `model_prediction` 원점이고 exact qualification sidecar가 없으므로, 모델 연결 진단 근거로만 기록하고 provider·빈도·물리검증·시설 QRA 승격에는 사용하지 않는다.

SLABx-LH2 FFI Test 6의 실제 소스는 40,960→81,920 격자 재검증에서 모든
모니터링 항목의 변화율이 2% 미만으로 수렴하여 수치 게이트가 승인됐다.
이는 수치해석 수렴 근거이며 독립 물리검증이나 시설 QRA 승격을 의미하지
않는다.

각 export의 같은 폴더에 있는 `provider_response.json`도 함께 대조한다. 7/7 행에서 event·component·port ID, 방출시간, 가용·누적 방출질량, 종료근거, provider source digest와 canonical provider result digest가 `resolved_release.json`과 일치한다. 이 정규화는 모델 출력과 PRISM 경계가 서로 다른 사고나 포트를 가리키지 않는지 확인하는 진단 단계다. 질량 잔차가 남거나, `synthetic_diagnostic_horizon`인 경우는 그대로 열린 근거로 남기며, 잔여 재고를 0으로 고치거나 빈도·물리검증·시설 QRA를 승격하지 않는다. 상세 규칙은 [`external release-response normalization`](PRISM_external_release_response_normalization_en.md)에 기록했다.

## 요구사항별 판정

| 요구사항 | 현재 증거 | 판정 |
|---|---|---|
| 설비 상태와 운전 모드를 HAZOP 입력으로 사용 | HAZOP selection/event binding, operating-mode evidence, observed runtime audit | **진단 완료** (`PASS`) |
| 현장 설비 ID와 provider 모델 ID의 결합 경계를 명시 | `FacilityRealtimeBinding.provider_component_id`, digest-recomputed runtime translation, explicit identity test | **진단 완료**, provider 자격화와는 별도 |
| 실시간 설비 프레임에서 HAZOP 선택과 provider/SLABx-LH2 호출을 한 경계로 연결 | `FacilityRealtimeConsequenceMonitor.update_from_runtime_frames_with_hazop`, `prism.realtime_hazop_facility_bridge.v1`, reconstructed inspection-centre chain (1/1 diagnostic case) | **진단 완료**, 연간 시설 IR/F-N은 보류 |
| 문헌 빈도를 사고 event에 명시적으로 연결 | frequency port binding 34/34, release-boundary case 44/44, 5개 문헌 시나리오; event-level P05/P95는 35/44 | **진단 완료**, 9개 point-rate event는 별도 민감도 범위로만 해석 |
| 설비 방출 포트·지속시간·차단·재고를 피해계산에 전달 | `results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/campaign_result.json` 및 risk-atom chain audit | **진단 완료**, 일부 provider 경계 제한 |
| 방출부터 SLABx-LH2·점화·최종 피해까지 연결 | facility aggregate closure와 risk atom chain audit | **진단 완료** (`PASS`) |
| 기상·인구·IR/F-N 조건부 계산 | facility assessment의 conditional diagnostic view | **조건부 진단만 허용** (`PASS`) |
| 빈도 불확실성·상관 가정·순위 안정성 | 5개 문헌 frequency scenario 및 uncertainty audit | **진단 완료** (`PASS`) |
| 실시간 처리시간과 캐시/신규 계산 구분 | realtime benchmark 및 case timing fields | **처리시간 근거 확보**, 1 Hz fresh-physics 주장은 보류 (`PASS`) |
| 현재·예측 공정 상태를 동일 HAZOP/provider/SLABx-LH2 경계로 연결 | `run_hazop_integrated_risk`, `prism.hazop_forecast_risk_scan.v1`, explicit `model_prediction` origin/time, forecast facility-aggregator gate | **진단 완료**, 예측 시설 F/N은 명시적 aggregator 전까지 보류 |
| 예측 정량 트리거를 시설 원장으로 명시적으로 결합 | `build_hazop_forecast_facility_campaign_result`, `forecast_campaign_bindings`, `component_id|scenario_id|forecast_time_s` trace, completion-audit structure check | **진단 완료**, 누락 trigger는 0 위험으로 대체하지 않고 보류 |
| 미계산·운영자 제한·영역 제한을 숨기지 않음 | facility evidence request, release-boundary audit, scope ledger | **진단 완료**, 미계산/제한 상태 보존 |
| 실제 시설 QRA 승격 | qualified packet, independent validation, complete release boundary | **차단** (`BLOCKED`) |
| 상태 스냅샷–provider 재고 수치 일관성 | runtime gate, campaign binder gate, explicit rebaseline reconciliation | **진단상 해결**, 권위 union 교체는 보류 |

## 전체 연결에서 확인된 것

1. 공정 상태와 `operating_mode`가 HAZOP 선택에 함께 들어간다.
2. HAZOP event identity가 문헌 frequency event와 연결된다.
3. provider packet의 포트, 개구, 상태 snapshot, 방출 시간, 질량 장부가 case에 보존된다.
4. 방출 packet은 SLABx-LH2/풀·확산·점화·피해 계산으로 전달된다.
5. 결과는 사건·설비·수용점·문헌 빈도 시나리오별로 facility ledger에 집계된다.
6. 조건부 IR/F-N은 계산되지만, 시설 전체 공식 위험값은 자격화 조건이 충족될 때까지 보류된다.

재구성 검사센터 데이터에 대해서는 공급 모드 고압 이탈 1건을 명시적
문헌 event와 연결하여 provider packet, SLABx-LH2/TNO consequence service,
현재 기상 risk atom까지 진단 실행했다. 이 실행은 `model_prediction` packet과
진단 geometry를 사용하므로 실제 시설 provider 자격, 독립 검증, 시설 전체
IR/F-N 승격의 증거로 사용하지 않는다.

## 현재 다섯 가지 엄격한 차단 검사

| 차단 검사 | 의미 | 필요한 다음 증거 |
|---|---|---|
| `facility_release_boundary` | 44개 case 모두의 종료·차단·재고 경계가 닫히지 않음 | 실제 설비 provider의 종료 시계, isolation feedback, 재고·질량 잔차 packet |
| `actual_provider_release_packet` | 합성/model-prediction packet만 있음 | 실제 시설 geometry·운전조건을 계산한 qualified accident export와 qualification sidecar |
| `declared_major_accident_scope` | 수치 계산은 있으나 사고군 전체의 적격 증거가 없음 | 사고군별 독립 검증자료와 provider packet |
| `facility_ir_fn_available` | 시설 전체 IR/F-N을 공식값으로 표시할 수 없음 | 위 세 증거와 완전한 시설 목록·위치·인구·방호정책 |
| `facility_case_provider_packet_coverage` | 44개 case와 정확히 일치하는 qualified provider packet이 없음 | case/event/component/port/source-result digest가 일치하는 provider packet과 qualification sidecar |

수치적으로는 44개 case 모두가 risk-atom chain을 통과했고, 최신 case-level
release audit은 **42개를 numerically closed**, **2개를 numerically open**으로
분류한다. 이 수치는 provider 자격화가 끝났다는 뜻이 아니다. 29개는
`NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED`이고, 2개는 emergency-relief
및 600 s horizon 종료 경계가 아직 열려 있으므로 strict facility-QRA gate는
계속 닫혀 있다. 예측 상태 스캔도 동일한 사고·피해 필드를 사용하지만,
시설 F/N 집계는 `WITHHELD_FORECAST_FACILITY_AGGREGATOR_REQUIRED`로 남긴다.

두 열린 case의 다음 입력은 [`PRISM open release-boundary evidence requests`](PRISM_open_release_boundary_requests_en.md)와
`results/20261115/open_release_boundary_evidence_requests_current.json`에
기계판독 가능한 형태로 고정했다. PSV 요청에는 setpoint·capacity·완료 사건을,
600 s 요청에는 추가 이력 또는 provider 소유의 명시적 물리 종료근거를 요구한다.
두 요청 모두 종료시간·빈도·시설 QRA를 추정하지 않는다.

공급자 결과를 받은 뒤에는 [`PRISM release-boundary response intake`](PRISM_release_boundary_response_intake_en.md)의
`prism.release_boundary_evidence_response.v1` 계약으로 먼저 응답을 검사한다.
응답 검사는 event/case/component/port/운전모드/HAZOP ID와 원본 digest를
대조하고, PSV와 600 s horizon에 서로 다른 종료 규칙을 적용한다.
`RELEASE_BOUNDARY_REAUDIT_READY`는 case-level 재감사가 가능하다는 뜻일 뿐,
provider 자격화·독립 물리검증·시설 IR/F-N 승인을 뜻하지 않는다.

## 추가된 다설비 결합 진단

별도의 일반 옥외 시설 예제로 펌프와 밸브를 하나의 facility campaign에
연결했다. 펌프는 native liquid/two-phase packet, 밸브는 native compressible
gas handoff packet을 사용한다. 두 packet의 component·port·개구가 문헌 빈도
사건과 exact-match되고, 각 실행 사건은 case와 risk atom까지 연결되었는지
실행기 자체가 확인한다.

| 항목 | 결과 |
|---|---:|
| packet / component | 2 / 2 |
| 생성 빈도 event | 7 |
| 실행 case | 2 |
| `UNCOMPUTED` opening bin | 5 |
| risk atom | 8 |
| 문헌 빈도 시나리오 | 3 (valve p05/published/p95, pump fixed) |
| 방출→case→risk atom chain | `true` |
| campaign 측정시간 | 약 10.6 s |

상세 실행 원장은 [`PRISM_native_multi_equipment_facility_campaign_20261016.md`](PRISM_native_multi_equipment_facility_campaign_20261016.md)와
[`generic_lh2_native_pump_valve_facility_replay_20261016.json`](../examples/generic_lh2_native_pump_valve_facility_replay_20261016.json)에 있다.
설비별 기여와 빈도 민감도 재계산 감사는 [`generic_lh2_native_pump_valve_facility_audit_20261016.json`](../examples/generic_lh2_native_pump_valve_facility_audit_20261016.json)에 기록했다.
이 감사는 최신 IJHE 완료 감사에도 `diagnostic_native_provider_multi_equipment_audit: PASS`로 연결했다. 전체 감사 상태는 `INCOMPLETE_EVIDENCE`이며, qualified provider·release boundary·독립 물리검증·시설 IR/F-N 차단은 그대로 남아 있다.
이 결과는 다설비 연결과 fail-closed 누락 회계를 검증하는 진단 증거이며,
qualified provider·독립 물리검증·시설 전체 IR/F-N 승격을 의미하지 않는다.

## 최신 native full-scope replay 추적

별도 최신 replay는 generic outdoor manifest의 24개 reviewed event를 모두
case로 만들고, 각 방출을 SLABx-LH2/TNO consequence path까지 전달했다.
13개 case는 동적 종료 원장이 준비된 진단 행이고 11개는
`EXECUTED_OPERATOR_LIMITED`로 보류된다. G1은 잔류 재고가 있는 상태를
잘못된 `inventory_depletion`으로 해석하지 않고 `inventory_over_600s`로
재생했다. 이 결과의 범위·family·case별 증거요청은 다음 원장에 고정했다.

| 증거 | 최신 결과 |
|---|---:|
| native full-scope event / case / risk atom | 24 / 24 / 96 |
| dynamic closure ready / operator-limited | 13 / 11 |
| scope matrix | 12 family, 9 family blockers |
| facility evidence request | 24 case requests, 12 family requests |
| provider qualification readiness | 24 packet candidates, 13 exact diagnostic matches, 0 qualified packets |
| strict facility QRA | `false`, 14 explicit blockers |
| processing-time record | 24 fresh-physics cases, total 814,290.39 ms, case p95 105,548.90 ms |

이 replay는 기존 34-event/44-case 권위 union의 보완 진단 원장이다. 두 원장을
혼합해 사건 빈도를 중복 합산하지 않으며, provider qualification·독립 물리검증·
시설 IR/F-N 승격을 열지 않는다.

## 해석 규칙

- `EXECUTED`는 계산 경로가 실행되었다는 뜻이고, 실제 시설에 검증된 모델이라는 뜻이 아니다.
- `EXECUTED_OPERATOR_LIMITED`와 `EXECUTED_DOMAIN_INCOMPLETE`는 `UNCOMPUTED`로 합치지 않는다.
- 문헌 빈도는 provider나 센서에서 추정하지 않는다.
- 지원되지 않은 사고를 다른 사고로 대체하지 않는다.
- 조건부 IR/F-N을 시설 전체 QRA로 표현하지 않는다.
- 현장 사고빈도 학습, 실내, 폭굉, 전체 도미노는 이번 필수 범위에 포함하지 않는다.

## 권위 산출물

- 최신 facility union: `results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/campaign_result.json`
- 최신 IJHE audit: `results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`
- 최신 handoff audit: `examples/inspection_center_facility_ijhe_handoff_audit.json`
- 최신 audit metadata verifier: `results/20261115/latest_ijhe_audit_verification.json`
- 최신 release-boundary audit: `results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json`
- 최신 provider termination catalog: `results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff_isolation_current.json`
- 현재 열린 종료경계 증거요청: `results/20261115/open_release_boundary_evidence_requests_current.json`
- 현재 열린 종료경계 응답 템플릿: `results/20261115/open_release_boundary_evidence_response_template.json`
- 종료경계 응답 intake 계약: [`PRISM_release_boundary_response_intake_en.md`](PRISM_release_boundary_response_intake_en.md)
- 최신 case-level release-boundary audit: `results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json`
- 현재·예측 HAZOP 연결 계약: [`PRISM_current_forecast_hazop_contract_en.md`](PRISM_current_forecast_hazop_contract_en.md)
- 최신 native full-scope campaign: `results/20261115/native_external_facility_full_scope_campaign_current/campaign_result.json`
- native full-scope scope matrix: `results/20261115/native_external_facility_full_scope_campaign_current/scope_matrix.json`
- native full-scope evidence request: `results/20261115/native_external_facility_full_scope_campaign_current/facility_evidence_request.json`
- native full-scope provider qualification readiness: `results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_readiness.json`
- native full-scope processing-time record: `results/20261115/native_external_facility_full_scope_campaign_current/processing_time_summary.json`
- 현재 상태 원장: `CURRENT_STATUS.json`

이 표는 완료를 선언하는 문서가 아니라, 계산 연결과 승격 증거를 한눈에 구분하는 IJHE 제출용 추적성 문서다.


The current full-scope readiness audit now emits a provider-qualification request
catalog at
`results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_requests.json`.
The readiness audit found 20 packet-level closure-ready identities and 6
identities that still need release-closure evidence. The request builder checks
each packet's family-specific termination ledger before assigning the
qualification-only label. The current catalog therefore contains 20
qualification-only requests and 6 closure-and-qualification requests. This catalog
preserves packet identity and blocking reasons; it does not infer rates,
physical validation or facility IR/F-N.

The same request catalog can be converted into a fillable sidecar manifest with
`scripts/build_provider_sidecar_manifest_template.py`. The current native
full-scope template has 26 release identities from 24 event rows; all entries
remain `TEMPLATE_ONLY` and `promotion_allowed=false` until a reviewed sidecar
binds the exact packet digests and independent validation evidence.

The native request catalog now has a direct audit adapter at
`scripts/audit_native_full_scope_provider_qualification.py`. It flattens grouped
event rows into release identities without changing packet data, then reuses
the exact digest and sidecar checks. The current audit reports 24 rows, 26
release identities, 0 exact matches and 26 missing sidecars; it keeps frequency
inference and facility QRA disabled.

The native audit is now consumed by
`scripts/reconcile_native_provider_qualification_assessment.py`, which rebuilds
the facility assessment gate from the saved risk ledger and frequency scenarios.
The derived current assessment preserves conditional IR/F-N while explicitly
reporting provider gate completeness and keeps qualified facility QRA false.

## 2026-10-18 current-code realtime cache recheck

The near-receptor diagnostic monitor path was measured again with the current code. The exact-state cache and changed-weather fresh-physics paths were kept separate.

- Five unchanged-state cache lookups all met the 1 s diagnostic deadline. The cache median was `33.71 ms` and p95 was `36.41 ms`.
- The first fresh-physics call took `3050.95 ms`; three changed-weather calls through one persistent worker had a steady p95 of `3027.41 ms`.
- Therefore the cached diagnostic path is suitable for a 1 Hz polling target in this run, while fresh physics remains a background calculation. No fresh-physics 1 Hz claim is made.
- The benchmark used the synthetic near-receptor diagnostic facility and does not qualify a full-facility service level, provider evidence, frequency, physical validation, or facility QRA.
- A separate attempt against the 24-case full-scope campaign exceeded the configured backend deadline on its first fresh-physics request. Its partial process was terminated and no result was promoted; this does not change the authoritative campaign or risk ledger.

The machine-readable recheck is [`examples/native_lh2_realtime_cache_recheck_20261018.json`](../examples/native_lh2_realtime_cache_recheck_20261018.json).

## 2026-10-18 exact AREA_100% native pipe current-code recheck

The latest `lh2dt_models` source (`7072374`, source digest `3b186dff…`) was replayed for the exact `LH2_PIPE AREA_100%` event used by the generic full-scope campaign. The provider state snapshot digest and provider result digest matched the previous candidate replay. The provider again terminated at `model_pressure_equalization` after `0.24005155145460036 s`, with a mass residual of approximately `1.39×10⁻¹⁷ kg` and an explicit `0.2 s` post-equalization observation with zero flow.

The packet passed the PRISM strict adapter and reached a one-event consequence campaign with one executed case and four risk atoms. The chain took `32.87 s` on this run. This confirms reproducibility of the state→native release→release ledger→SLABx-LH2/consequence path for this exact event. It remains a diagnostic candidate: no qualification sidecar or independent full-chain validation is present, the spatial grid and receptors are synthetic, and the packet was not rebound into the authoritative 34-event/44-case/176-atom union. The machine-readable record is [`examples/native_dynamic_pipe_exact_area100_current_recheck_20261018.json`](../examples/native_dynamic_pipe_exact_area100_current_recheck_20261018.json).

## 2026-10-18 exact AREA_100% qualification-intake drift check

The re-exported current packet was passed through the external release-artifact intake contract. Its response normalized successfully: identity, clock, mass ledger, source digest, state snapshot digest, and canonical provider result digest all matched. The packet is therefore `CLOSURE_READY_FOR_QUALIFICATION` at the structural release boundary.

The intake still reports **zero qualified sidecars** and `input_origin=model_prediction`; native isolation success is not a valid release-boundary termination for this packet. The current source/result digests (`3b186dff…` / `4100182f…`) also differ from the older digests in the saved full-scope provider request (`cef8e196…` / `b5be97f3…`). This is recorded as digest drift and requires an explicit request rebaseline before any authoritative campaign rebinding. No digest was silently substituted, and no frequency or facility QRA value was promoted. See [`examples/native_dynamic_pipe_exact_area100_qualification_intake_recheck_20261018.json`](../examples/native_dynamic_pipe_exact_area100_qualification_intake_recheck_20261018.json).

## 2026-10-18 explicit provider-request rebaseline

The new `provider_request_rebaseline` contract was applied to the exact `LH2_PIPE AREA_100%` request after the identity tuple (`event_id`, component, port, and event kind) matched. The request now carries the current source/result digests (`3b186dff…` / `4100182f…`), while the previous request digests (`cef8e196…` / `b5be97f3…`) remain in the rebaseline record. The command requires an explicit acknowledgement and preserves `OPEN` qualification status; it does not synthesize a sidecar, infer a frequency, or open facility IR/F-N/QRA promotion. The implementation is covered by three focused tests and the applied record is [`examples/native_dynamic_pipe_exact_area100_request_rebaseline_20261018.json`](../examples/native_dynamic_pipe_exact_area100_request_rebaseline_20261018.json).

## 2026-10-18 latest-source full-scope recheck

All 24 generic outdoor events were exported again from external model commit `7072374` using the same declared isolation branch (`0.2 s` command plus `0.3 s` observation) used by the previous full-scope campaign. The latest source produced 24 exact packets with no uncomputed exports. Reconnecting those packets through PRISM reproduced the earlier diagnostic accounting: 13 `EXECUTED`, 11 `EXECUTED_OPERATOR_LIMITED`, and 96 risk atoms. The basic bounded-horizon export is retained as a diagnostic comparison only; it produced 22 operator-limited cases because it omitted the isolation branch.

Every one of the 24 provider result digests changed relative to the stored campaign, so the result is not silently substituted into the authoritative 34-event/44-case/176-atom union. The latest recheck still has no qualified sidecar, no independent physical-validation claim, and no facility IR/F-N/QRA promotion. The comparison, timing, and digest map are recorded in [`examples/native_external_full_scope_latest_source_recheck_20261018.json`](../examples/native_external_full_scope_latest_source_recheck_20261018.json).

The full campaign rebaseline contract was then applied with explicit previous and current source-tree digests. All 24 event/component/port identities matched and all 24 current result digests were rebound in a diagnostic record. The previous digest map remains embedded for audit, while the authoritative union was deliberately left unchanged and all promotion flags remain false. The applied record is [`examples/native_external_full_scope_campaign_rebaseline_20261018.json`](../examples/native_external_full_scope_campaign_rebaseline_20261018.json); the reusable implementation is `src/lh2_tno/facility_campaign_rebaseline.py` with CLI `scripts/rebaseline_facility_campaign.py`.

The provider qualification request catalog was also rebound at request granularity. The batch contract updated 24 event requests plus the two reliquefier endpoint requests (26 identity matches) to the current provider digests. It preserves the prior catalog as the source of the rebaseline, creates no qualification sidecar, and leaves frequency and facility-QRA promotion false. The compact audit record is [`examples/native_external_full_scope_provider_request_rebaseline_20261018.json`](../examples/native_external_full_scope_provider_request_rebaseline_20261018.json); the full generated catalog is retained in the local intake workspace for evidence review.

## 2026-10-18 inspection-centre source recheck

The current inspection-centre files were hashed and re-audited against the prior
read-only evidence records. The three operating-sequence CSV files and three
ten-run workbooks have the same hashes as the previous check. The external
`lh2dt` source tree also remains unchanged at commit `7072374` and digest
`3b186dff…`. The recomputed summary remains 52 scenario rows (41 outdoor
screening candidates and 11 outside the declared outdoor scope), 17 workbooks,
78 sheets, 8,955 state samples, and 522 numeric signals with unconfirmed
engineering units. The core summary matches the stored evidence ledger and no
new release, frequency, provider-qualification, physical-validation, or
facility-QRA evidence was found. The machine-readable record is
[`examples/inspection_center_current_source_recheck_20261018.json`](../examples/inspection_center_current_source_recheck_20261018.json).

The same source tree was also tested directly with its current Python test
suite: 377 tests passed with one deprecation warning. This is a source-level
regression check only; it does not turn the external model into qualified
facility accident evidence. The test receipt is
[`examples/external_lh2dt_source_test_recheck_20261018.json`](../examples/external_lh2dt_source_test_recheck_20261018.json).

## 2026-10-18 NASA pump test-point intake

The two NASA pump PDFs were reviewed at the source-text level and eight
unit-bound candidate points were recorded: four for the 1959 five-cylinder
piston pump and four for the 1991 LH2 centrifugal-pump configuration. The
manifest preserves the PDF page, source locator, value, unit, test condition,
and configuration identifier for every point. Both document SHA-256 hashes
match the current files. The points are still candidate comparison inputs:
the generic PRISM mapped-pump component has not been shown to match either
NASA configuration, and no independent no-fit holdout comparison has been
performed. Consequently physical validation, accident-release qualification,
frequency, and facility QRA remain closed. The audit and source manifest are
[`examples/external_pump_test_point_audit_20261018.json`](../examples/external_pump_test_point_audit_20261018.json)
and [`examples/external_pump_test_point_manifest_20261018.json`](../examples/external_pump_test_point_manifest_20261018.json).

The configuration crosswalk makes the remaining comparison decision explicit:
the current generic `liquid-transfer-pump-01` has no reviewed exact match to
either NASA test article. It therefore cannot use either document as a fitted
pump map or as an independent validation result. The crosswalk and required
evidence are recorded in
[`examples/external_pump_configuration_crosswalk_20261018.json`](../examples/external_pump_configuration_crosswalk_20261018.json).

The same pump audit is now an optional, explicit check in the IJHE completion
audit (`diagnostic_external_pump_test_point_audit`). This keeps the candidate
points visible in the readiness report while requiring configuration review and
an independent holdout before any validation or facility-QRA promotion.

## 2026-10-18 NASA TN D-4171 HEM benchmark recheck

The current external model workspace contains a newly generated, untracked
benchmark document for NASA TN D-4171. Its result file was copied into the
PRISM evidence ledger and checked against 21 unfitted tests. The homogeneous
equilibrium baseline under-predicts pressure-rise rates in every test, with a
mean predicted/observed ratio of 0.480, MAPE of 52.0%, and NRMSE of 0.370;
upper-heating cases average only 0.232 of the observed rate. This is negative
model-limit evidence for storage and vent pressure dynamics, not a facility
validation result. The completion audit now exposes it as
`diagnostic_nasa_tn_d4171_hem_benchmark`, with all provider, frequency,
physical-validation, and facility-QRA promotion flags fixed to false.

The hash-bound audit is
[`examples/external_nasa_tn_d4171_hem_audit_20261018.json`](../examples/external_nasa_tn_d4171_hem_audit_20261018.json);
the copied result table is
[`examples/external_nasa_tn_d4171_hem_results_20261018.json`](../examples/external_nasa_tn_d4171_hem_results_20261018.json).
