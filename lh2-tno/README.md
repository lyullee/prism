# PRISM

**Process Risk Integration and Scenario Modeling**

공정·설비 상태, 사고 시나리오, 발생 빈도와 피해영향을 연결하는 위험 분석 시스템.

**2026-10-27 상태 snapshot 방출경계 보완:** 일반 옥외 LH2 매니페스트의 24개
문헌 사건을 외부 `lh2dt_models` 사고 exporter로 다시 실행해 **24/24 exact
native packet**을 만들었습니다. 저장탱크·이송배관·밸브·벤트·펌프·기화기·재액화기
양단 파열 어댑터가 모두 `prism.equipment_state_snapshot.v1` 원문을 요청에 넣고,
provider가 같은 digest를 echo하는지 검사합니다. 별도
`results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json`
은 24개 중 24개를 `BOUND_AND_ECHOED`, digest 불일치 0건으로 기록합니다.
이 결과는 상태 원문→사고 방출→SLABx-LH2/피해 chain의 진단 입력 보존을 닫은
것이며, 합성 상태·문헌 빈도·operator-limited 방출·독립 물리검증·qualified
provider·시설 IR/F-N을 실제 시설 근거로 승격하지 않습니다. 재현 명령과 제한은
[native 전체범위 상태 snapshot 감사](docs/PRISM_native_전체범위_상태snapshot_방출경계_감사_20261027.md)를
참조합니다.

같은 24개 catalog packet을 `rebind_campaign_to_worklist_packets.py`로 기존
문헌 campaign에 다시 넣어 재실행한 결과도 보존합니다. `results/20261027/native_generic_scope_packets_state_bound/native_packet_campaign_ledger.json`은
24/24 event·case가 native packet identity를 소비하고 24/24 consequence chain을
실행했으며, snapshot event set 24개와 campaign event set 24개가 재결합됐음을
기록합니다. 19개 case는 여전히 `EXECUTED_OPERATOR_LIMITED`이고 qualified
provider·독립 물리검증·시설 전체 IR/F-N은 열리지 않습니다.

**버전 0.6.2 / 기준일 2026-10-24** — 기본 `standard` 분석과 선택형 `lh2` 분석을 공통 실행기에서 선택합니다.
범용 액화수소시설에 적용하는 인터페이스이며 특정 실증센터의 설비·태그를 필수로 요구하지 않습니다.

**2026-10-22 최신 개발 기준점:** 밸브 5개 면적 구간과 두 기상 조건을 포함한 7개 캠페인 시설 원장은 41개 사건·80개 case·312개 risk atom을 보존한다. 최신 IJHE 감사는 `INCOMPLETE_EVIDENCE`(18개 검사 중 4개 차단)이며, 시설 원장에는 조건부 수치 결과 78건과 `UNCOMPUTED` 2건이 함께 남아 있다. 이전 시점의 범위표와 원장 namespace가 달랐던 문제는 `build_ledger_scope_matrix.py`로 원장 기반 범위표를 재생성해 해소했으며, 새 `scope_ledger_consistency` 감사는 `CONSISTENT_SCOPE_LEDGER`를 반환한다. 문헌 빈도 불확실성 5개 시나리오도 보정 원장에 연결되어 조건부 known-atom 민감도를 다시 계산했지만 `facility_credible_interval=false`를 유지한다. 엄격한 시설 범위는 여전히 부분 상태이고 적격 provider packet·독립 검증·시설 IR/F-N은 보류된다. 검증근거 통합장부도 6개 영역으로 생성되어 모든 승격 주장을 분리한다. 현재 상태 파일과 [밸브 결합 개발기록](docs/PRISM_밸브_방출패킷_시설결합_개발기록_20261021.md)에 기록된다. 시설 원장에는 12개 설비별 `component_coverage`가 있어 설비별 사건·조건부 실행·엄격 보류·risk atom을 따로 확인할 수 있다. 전체 portable test suite는 **548개 통과**다.

**2026-10-24 현재 일반 LH2 전체범위 기준:** 24개 문헌 사건을 현재 외부 `lh2dt_models` native 사고 exporter로 재실행해 **24/24 exact packet**을 만들고, 24개 요청 branch를 방출→SLABx-LH2/SLABx→점화·피해 chain까지 연결했다. 여기에 기존 수직 벤트 handoff의 5개 개구면적 사건과 10개 기상·case를 같은 시설 원장으로 결합해 최신 병합 진단은 29개 event, 34개 case, 136개 risk atom을 기록한다. 최신 IJHE 감사 [`ijhe_completion_audit_native_generic_scope_vertical_v20.json`](results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v20.json)은 29개 PASS 검사·5개 BLOCKED 검사(상위 차단사유 4개)인 `INCOMPLETE_EVIDENCE`다. `diagnostic_combined_chain_closure`는 24개 packet-subset 사건과 5개 vertical operator-limited 사건의 29/29 방출→최종피해 연결을 확인하고, 새 `diagnostic_domain_recovery_audit`는 이전 6개 domain-incomplete 사건을 0개로 회복했다. 22/24 사건은 conservative outside-LFL proof를 통과했으며, 영역 밖 inventory는 계속 별도 장부로 보존한다. 별도 packet subset 24개와 vertical handoff 5개를 합친 union closure가 29/29 event를 닫았다는 뜻이며, 두 증거군을 하나의 qualified provider packet으로 합친다는 뜻은 아니다. 이는 fire/explosion domain gate를 닫는 진단 근거이지 provider 자격·시설 IR/F-N·전체 QRA 승격이 아니다. `diagnostic_slabx_lh2_validation_evidence`와 exact-cache realtime benchmark도 기존 제한 범위로 유지한다. 34개 facility case 중 qualified provider packet 연결은 0개다. 상세 기록은 [native 일반 LH2 전체범위 패킷·캠페인 기록](docs/PRISM_native_일반LH2_전체범위_패킷캠페인_20261023.md), [계산영역·가연성 경계 감사](docs/PRISM_domain_recovery_개발기록_20261024.md), [SLABx-LH2 검증근거 통합 기록](docs/PRISM_SLABx_LH2_검증근거_통합_20261024.md), [facility case packet coverage 기록](docs/PRISM_시설case_provider_packet_coverage_개발기록_20261009.md)이다.
시설 평가 원장에도 case 자격 gate를 직접 기록하도록 보완했다. [`native_generic_scope_vertical_merged_facility_assessment_population_v6.json`](results/20261024/native_generic_scope_vertical_merged_facility_assessment_population_v6.json)은 34개 요청 case와 0개 qualified provider case를 대조해 `facility_case_packet_coverage_complete=false`와 `qualified_facility_qra_available=false`를 남긴다. 이 값은 빈도를 추정하거나 risk atom을 0으로 만드는 기능이 아니며, 시설 IR/F-N 승격을 막는 증거 상태 표시다. 구현과 재현 명령은 [시설 평가 case coverage gate 개발기록](docs/PRISM_시설평가_case_coverage_gate_개발기록_20261009.md)에 있다.
시설 원장의 `component_risk_ranking`은 같은 조건부 risk atom에서 설비별 최대 수용점 IR을 계산해 우선 확인할 설비를 정렬한다. 수용점을 합산하거나 빈도를 재할당하지 않고 `facility_ir_fn_promotion=false`를 유지하는 진단용 장부다. 규칙과 예시는 [설비별 조건부 위험 순위 장부](docs/PRISM_설비별_조건부위험순위_개발기록_20261010.md)에 있다.

계산영역 감사는 대표 액체 pool 사건의 긴 SLABx finite-puff 지지영역을 추적하고, 풍하측·횡풍·높이별 marginal outside mass와 provider 지지경계를 보존한다. 대표 사건의 outside-domain mole-fraction upper bound는 `5.09375×10⁻⁵`로 수소 LFL `0.04`보다 작아, 영역 밖 질량을 삭제하지 않은 채 fire/explosion branch의 outside-LFL proof를 통과시켰다. 전체 recovery campaign에서는 이전 6개 domain-incomplete 표지가 0개가 되었고 22/24 사건이 flammability proof를 남겼다. 상세 기록은 [계산영역·가연성 경계 감사](docs/PRISM_domain_recovery_개발기록_20261024.md)에 있다.


시설 IR/F-N 연결 자체를 0값 결과에 의존하지 않도록, 별도의 합성 near-receptor 진단도 실행했다. 저장탱크 `AREA_0.01%` 한 건을 설비→방출→pool/SLABx→점화·피해→수용점까지 새로 계산하고, 수용점을 source에서 0.5 m로 둔 결과 조건부 IR은 `4.68×10⁻⁵`로 나타났다. 나머지 23개 LOC는 명시적 `UNCOMPUTED`로 남겼고 시설 전체 IR/F-N은 승격하지 않았다. 이 결과는 [near-receptor chain 검증 요약](examples/native_lh2_near_receptor_ir_fn_chain_verification.json)에서 확인한다.

> 현재는 연구용 진단 계산 시스템입니다. 방출부터 최종 피해까지 실행하는 경로는 구현했지만,
> 새 LH2 경로의 전체 시설 QRA, 현장 정확도와 매초 신규 물리 계산은 아직 검증되지 않았습니다.
> v0.6.2는 v0.6.0 이후의 설비 경계·문헌 빈도·매니페스트 진단을 포함한 연구용 알파 릴리스입니다. 전체 시설 QRA와 독립 물리 검증은 여전히 별도 상태로 표시됩니다.

**개발 소스 추가 사항 (2026-10-09):** 다중 LOC·기상·방호 분기 실행기와 기존 TNO IR/F-N 합산 연결, 빈도 민감도, 문헌 p05/중앙/p95 빈도 구간 재가중, 통합 LH2 source의 압력 평형 자연 종료, G1 instantaneous-inventory용 명시적 SLABx-LH2 liquid-jet operator, 외부 설비 twin의 PH/network 출구를 `ResolvedGasRelease`로 받아 시설 campaign에 연결하는 경로를 추가했습니다. 추가로 `LayeredTankNetworkSimulator`와 `CommandedValve`를 이용해 탱크 상태→밸브 차단 성공·실패→기체 출구 종료/진단시계까지 연결하고, `HomogeneousTank`의 양수 재고 threshold 종료를 문헌 `LH2_PIPE` 5개 누출 크기와 두 기상 조건에 연결해 **10건을 모두 실행**했습니다. 자연 종료는 모델이 반환한 실제 시간 이력만 사용하며 요청 시간까지 유량을 연장하지 않습니다. G1은 구멍 누출로 대체하지 않고 2초 finite-inventory 질량 폐합을 수행하지만 일정 upstream·open spray-energy 가정 때문에 operator-limited로 표시합니다. transient 설비 경로는 차단 성공·실패 두 분기를 두 기상 조건에 전달해 **20건을 모두 실행**했습니다. `TNO_PIPE` full-bore 양단은 `ResolvedGasReleaseSet`의 두 provider 출구를 한 사건으로 결합하고, 위치 배분은 `location_weight`로 명시합니다. 수직 전용 출구는 provider가 수평 handoff 단면·방향·혼합상태를 명시한 `VerticalGasHandoff`가 있을 때만 downstream 경로로 연결하며, PRISM이 수직 제트를 임의로 회전시키지 않습니다. **새로 provider가 계산한 액체·2상 대기 출구를 `ResolvedLiquidRelease`로 받아 flash 기체·지면 액체·액적 도착 시계를 그대로 SLABx-LH2/SLABx와 DynamicLH2PoolX에 전달하는 한 건의 전체 진단도 실행했습니다. ground liquid이 없다는 provider 증거가 있으면 `prism.no_rainout_evidence.v1`을 사용해 기본 declared pool 반경을 끄고, ground liquid이 있는데 no-rainout을 선언하면 계약을 거부합니다. airborne liquid은 검증된 별도 adapter가 없으면 거절합니다.** 이 액체 경계의 실제 개구가 문헌 `LH2_VESSEL` 0.01% bin과 일치하는 별도 campaign에서는 저장탱크·격리밸브·이송배관 15개 문헌 LOC를 생성하고, 정확히 일치하는 저장탱크 한 건만 빈도와 결합했습니다. 나머지 14개 LOC는 provider 이력 부재 또는 개구 불일치로 두 기상 조건에서 미계산 처리했습니다. `bind_event()`는 이제 `resolved_liquid_release`의 provider 개구를 직접 검사합니다. 장벽 성공확률 `0.99`와 재고 threshold·탱크 입력은 합성 진단값이며 현장 신뢰도·현장 재고 추정이 아닙니다. 추가로 DynamicLH2PoolX의 풀/확산 구성요소 hold-out 지표와 원자료 해시를 별도 장부로 확인했지만, protocol hash drift 때문에 제한 증거로만 기록했습니다. 빈도 구간은 자산별 공유 분위수 시나리오와 독립 event-bound 시나리오를 비교하고, catalogue에 공개된 로그정규 mu/sigma가 있는 LH2 사건에는 known-contribution p05/p50/p95 표본 구간도 계산할 수 있습니다. 이 구간은 물리 계산을 반복하지 않으며 불완전한 시설을 완전한 시설 신뢰구간으로 표시하지 않습니다. **추가로 일반 설비 매니페스트의 모든 부품을 명시적 문헌 FrequencyPlan으로 선택하거나 제외하고, 개구가 일치하는 방출 요청만 RiskCampaign에 연결하는 컴파일러를 넣었습니다.** 이번 0.6.2 개발 기능입니다. **523개 portable 테스트 통과** 및 LayeredTank-SLABx·문헌빈도 시설 연결 진단을 확인했습니다. [완성 목표](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_IJHE_완성목표_20261009.md) / [사용·검증·실패 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_시설위험_실행기_개발기록_20261009.md) / [액체·2상 경계 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_설비액체2상_연결_개발기록_20261009.md) / [LayeredTank 문헌빈도 연결 기록](docs/PRISM_LayeredTank_문헌빈도_시설연결_20261009.md) / [재고 소진 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_재고소진_연결_개발기록_20261009.md) / [물리 검증 근거](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_물리검증_근거_20261009.md). 실제 시설 연간 위험은 설비·운전·물리 검증 자료가 없으므로 계속 별도로 보류합니다.
**시설 증거 요청 장부 (개발 소스):** `scripts/build_facility_evidence_request.py`는 현재 사고범위와 설비별 provider 근거 요청을 생성합니다. 매니페스트에 해당 설비가 없어서 `NOT_APPLICABLE`로 분류된 사고군은 범위 장부에는 남기되 `evidence_required=false`와 빈 요청으로 기록합니다. 실제 설비가 존재하는 사고군의 누락·미계산 상태는 계속 provider 근거 요청과 승격 차단으로 유지합니다. 이 기능은 문헌 빈도를 바꾸거나 센서 빈도를 학습하지 않으며 시설 IR/F-N을 자동으로 열지 않습니다.

**provider 재고 소진 연결 (개발 소스):** 설비 provider가 기체 전체 재고 소진 이력을 계산한 경우 `equipment_inventory_depletion`을 사용하고, 액체·2상 전체 재고 이력은 `equipment_liquid_release`를 사용해 `instantaneous_inventory` 문헌 사건과 결합할 수 있습니다. 정확히 600초 이력을 반환한 기체·액체 provider는 각각 `equipment_inventory_over_600s`·`equipment_liquid_over_600s`와 `inventory_over_600s` 종료근거를 사용합니다. PRISM은 짧은 누출을 전량 방출로 늘리거나 센서값에서 재고·빈도를 추정하지 않습니다.

**차단 branch 빈도 연결 (개발 소스):** 하나의 initiating event에 대한 provider 방출 이력(예: isolation-success/isolation-failure)은 `--request-branch-catalog`으로 조건부 확률과 함께 입력할 수 있습니다. 물리 개구가 맞는 branch만 연결하고, 확률 합이 1보다 작으면 누락분을 `UNCOMPUTED`로 보존하며 1을 넘으면 거부합니다.

**일반 설비 매니페스트 연결 (개발 소스):** `EquipmentManifest`는 특정 검사센터의 태그를 코드에 고정하지 않고, 임의의 옥외 액화수소 설비 모델이 부품·포트·연결·운전 시나리오를 내보내는 공통 JSON 계약입니다. 위치·물성 기준·포트·제어 신호가 빠지면 PRISM은 값을 추정하지 않고 `PARTIAL`/`UNCOMPUTED`로 남깁니다. `EXECUTABLE`일 때만 엄격한 `Facility`로 승격되며 시설 위험 캠페인에 사용할 수 있습니다. 현재 센터 자료를 이 어댑터로 읽은 결과는 **PARTIAL**이며, P&ID 포트·좌표·실제 밸브 상태·시나리오 제어가 확인되기 전에는 센터 QRA로 승격하지 않습니다. 자세한 결과는 [설비 매니페스트 연결 기록](docs/PRISM_일반설비매니페스트_연결_개발기록_20261009.md)과 `scripts/validate_equipment_manifest.py`에 있습니다. **508개 portable 테스트**를 통과했습니다.

**외부 운전·고장 시나리오 근거 가져오기 (2026-10-09):** `scripts/import_scenario_evidence.py`는 검사센터를 포함한 외부 CSV에서 절차·예상고장·조치·감시 신호를 읽어 일반적인 옥외 LH2 사고 가족 후보로 정리합니다. 실제 가져오기는 CSV 3개, 52개 행이며 옥외 후보 41개와 시험동·건물·밀폐 맥락 11개를 구분했습니다. 이 결과는 `pipe_hole`, `valve_hole`, `vessel_hole`, `vent_hole`, `vaporizer_hole`, `inventory_over_600s`, `vertical_handoff` 후보와 압력·온도·유량·밸브·수소검지 등의 신호를 찾는 **screening evidence**입니다. 행별 원본 해시를 남기며, 빈도 적용·센서 빈도 학습·provider packet·시설 IR/F-N은 모두 `false`로 고정합니다. 후보 표만으로 빈도를 만들거나 정상 운전을 사고 방출로 바꾸지 않습니다. 상세 정책과 결과는 [외부 시나리오 근거 가져오기 기록](docs/PRISM_외부시나리오_근거_가져오기_개발기록_20261009.md)에 있습니다.

**검사센터 XLSX 상태 감사 (2026-10-18):** `scripts/audit_inspection_center_timeseries.py`는 17개 workbook·78개 sheet를 읽고 파일 해시, 헤더, 행 수, 태그 후보와 숫자 열의 집계 범위를 기록합니다. 실제 숫자값이 있는 522개 후보 열은 공학 단위가 확인되지 않아 `MISSING_OR_UNCONFIRMED`로 남겼으며, 상태 snapshot·빈도·sensor learning·provider packet·facility QRA는 모두 차단했습니다. 이 감사는 특정 센터의 태그를 일반 LH2 설비 기본값으로 고정하지 않는 준비도 검사입니다. 상세 규칙과 공개 요약은 [검사센터 시계열 상태 감사](docs/PRISM_검사센터_시계열상태감사_20261018.md)와 `examples/inspection_center_timeseries_audit.json`에 있습니다.

**표 형식 상태의 명시적 텔레메트리 변환 (2026-10-24):** `lh2_tno.inspection_timeseries.frame_from_row()`는 일반 설비 모델의 한 행을 `telemetry.Frame`으로 바꿀 때 원본 열→태그, 공학 단위, 품질, 시각, 스트림 ID를 모두 호출자가 명시하도록 검사합니다. 단위·품질·값을 추정하지 않으며, 공정 상태 프레임을 사고 방출·빈도·provider packet으로 승격하지 않습니다. 이 연결은 검사센터 전용이 아니고 임의의 옥외 LH2 설비에 사용할 수 있지만, 실제 사고 계산과 시설 QRA는 별도 설비 상태 adapter·사고 export·자격 증거가 있어야 열립니다. 자세한 예시는 [검사센터 시계열 상태 감사](docs/PRISM_검사센터_시계열상태감사_20261018.md)의 `명시적 행→텔레메트리 프레임 어댑터` 절에 있습니다.

`state_snapshot_from_row()`는 이 프레임을 기존 `TelemetryNormalizer`와 `EquipmentStateSnapshot` 계약에 연결합니다. 변환·압력 기준·센서 위치·최신성·순서 검사를 통과한 상태 snapshot만 만들며, 누출구경·방출시간·빈도·provider 방출은 만들지 않습니다. snapshot digest를 echo하는 별도 사고 export가 준비될 때만 설비 사고 계산으로 이어집니다.

실시간 디지털트윈 입력은 `RealtimeConsequenceMonitor.update_from_row()`로 같은 검사를 거쳐 처리할 수 있습니다. 이 메서드는 행→프레임→정규화→provider resolver(선택)→피해 계산의 처리시간과 deadline을 남기며, 명시적 바인딩 없이 값이나 빈도를 추정하지 않습니다.

여러 설비를 동시에 처리할 때는 `FacilityRealtimeConsequenceMonitor.update_from_rows()`가 설비별 행과 시각·스트림·열 바인딩을 받아 하나의 원자적 배치로 넘깁니다. 선언된 설비 집합과 행 집합이 다르면 즉시 거절하며, 부분 배치를 시설 위험 합계로 만들지 않습니다.
accepted 배치에는 `aggregate.facility_time_window`도 포함됩니다. 이 장부는 설비별 원본 시각과 도착 시각의 최소·최대·범위를 그대로 기록합니다. 서로 다른 시각을 임의로 맞추거나 보간하지 않으므로 `coherence_asserted=false`이며, 허용 시간창 판정은 상위 디지털트윈 운영 정책이 담당합니다.
상위 운영 정책을 PRISM 배치에서 직접 강제하려면 `FacilityRealtimeConsequenceMonitor(..., max_source_time_span_s=1.0)`처럼 양의 허용 원본 시각 범위를 명시합니다. 완전한 배치가 이 범위를 넘으면 계산된 설비 결과는 진단용으로 남기되 시설 상태는 `REJECTED`, `time_window_rejection.status="REJECTED_SOURCE_TIME_WINDOW"`가 되고 IR/F-N 합산은 닫힙니다. 기본값 `None`은 시간 범위를 측정만 하는 호환 모드입니다.

오류가 있는 행은 구조화된 `REJECTED` 장부로 반환되고, 누락·추가 컴포넌트와 원인 메시지가 남습니다. 시스템은 이 경우 이전 결과나 0 위험을 대신 사용하지 않습니다.

**검사센터 공학문서 감사 (2026-10-22):** `scripts/audit_engineering_document_evidence.py`는 P&ID·도면·운전절차서·비상절차서·시험절차서 PDF 18개를 해시와 페이지 수로 기록하고, P&ID 4개·도면 2개·운전절차 2개·비상절차 2개를 일반 설비 모델링 후보로 분류했습니다. 이 자료는 토폴로지·위치·조치 후보를 제공하지만 사고 방출 이력은 아니므로 `state_snapshot_binding_allowed=false`, `provider_packet_created=false`, `frequency_applied=false`, `facility_qra_claim=false`를 유지합니다. 상세 규칙은 [검사센터 공학문서 증거 감사](docs/PRISM_검사센터_공학문서_증거감사_20261022.md), 공개 요약은 `examples/inspection_center_engineering_document_audit.json`에 있습니다.

**외부 LH2 위험 스윕·처리시간 감사 (2026-10-22):** `scripts/audit_external_lh2_sweep.py`는 탱크·PSV 스윕 68건과 TNO 정책 계산 6건의 해시, 내부 질량·에너지 잔차, 실행시간, `ENGINEERING_JUDGEMENT` 위험 proxy를 기록했습니다. 탱크 최대 질량 잔차는 약 `1.04×10⁻¹¹ kg`, 최대 에너지 잔차는 약 `5.81×10⁻⁷ J`, TNO 정책 p95 실행시간은 약 `0.400 s`입니다. 실패한 탱크 사례는 그대로 보존하며, 이 자료는 내부 폐합·처리시간 screening evidence일 뿐 독립 물리검증·적격 provider packet·시설 IR/F-N·빈도 추정이 아닙니다. 상세 정책은 [외부 LH2 위험 스윕 처리시간 감사](docs/PRISM_외부LH2_위험스윕_처리시간_감사_20261022.md), 공개 요약은 `examples/center_lh2_external_sweep_audit.json`에 있습니다.

**범위 매트릭스·시설 원장 일관성 감사 (2026-10-22):** `scripts/audit_scope_ledger_consistency.py`는 범위 매트릭스와 실제 병합 시설 원장의 event ID, 사고군별 case 수, 조건부 실행/미계산 수를 직접 비교합니다. 이전 매트릭스는 여러 campaign 시점의 50개 event ID를 선언했지만 최신 원장은 41개를 보존했고, 조건부 미계산 수도 0건과 2건으로 달랐습니다. `scripts/build_ledger_scope_matrix.py`는 최신 원장에서 기존 사고군 표지를 보존하고, profile·release mode로 확인할 수 있는 기본 사고군과 정확히 지정된 provider-specific override만 반영해 범위표를 다시 만듭니다. 최신 결과는 41개 event·80개 case·조건부 실행 78건·미계산 2건이며 `CONSISTENT_SCOPE_LEDGER`입니다. 이 감사는 ID를 이름 변경하거나 빠진 사고를 0으로 채우지 않으며, [시설 원장 기반 범위표 재생성 기록](docs/PRISM_시설원장기반_범위표_재생성_20261022.md)과 `results/20261022/scope_ledger_consistency_family_repaired.json`에 결과를 보존합니다.

**시설 원장 빈도 불확실성 연결 (2026-10-22):** `scripts/compute_frequency_uncertainty.py`가 보정 원장의 312개 risk atom에 문헌 시나리오 5개를 적용합니다. 자산별 shared p05/중앙/p95와 event별 independent p05/p95를 비교하며 방출·확산·피해 물리는 다시 계산하지 않습니다. 최신 IJHE 감사에서 `diagnostic_frequency_uncertainty_evidence=PASS`가 되었지만, 미계산 case·합성 provider·부분 사고군 때문에 `facility_credible_interval=false`와 시설 전체 QRA 보류는 그대로입니다. [빈도 불확실성 연결 기록](docs/PRISM_시설원장_빈도불확실성_연결_20261022.md)에 재현 명령과 해석을 기록했습니다.

**사고 방출 packet 어댑터 (개발 소스):** `equipment_release_adapter.py`는 외부 설비 모델이 계산한 왼쪽 유지 시간 이력, 실제 종료 근거, 누적 질량·엔탈피와 액체·기체 분할을 `ResolvedGasRelease` 또는 `ResolvedLiquidRelease`로 엄격하게 변환합니다. 이 어댑터는 유량을 재계산하거나 요청시간까지 이력을 연장하지 않으며, 정상 운전 결과를 사고 packet으로 승격하지 않습니다. LayeredTank–SLABx-LH2 브리지도 같은 액체 어댑터를 사용해 중복 패킷 조립을 제거했습니다. 외부 `lh2dt`의 7개 설비 클래스는 이제 native 사고 export 경계를 제공하지만, qualified packet은 별도의 증거와 실제 시설 입력을 요구합니다. native export가 있어도 `provider_packet_promoted=false`인 연결 시험으로 남을 수 있습니다.

**외부 설비 사고 export 계약 (개발 소스):** `equipment_accident_export.py`는 정상 상태 메서드와 사고 이력 export를 분리합니다. provider는 `export_accident_history(request)`를 구현하고, 사고 포트·개구·관찰시계·provider 종료·질량/엔탈피 장부를 `prism.external_accident_history.v1`로 반환해야 합니다. `evaluate()`·`simulate()`·`advance()`만 있는 모델은 사고 packet을 만들 수 없으며 즉시 차단됩니다. `synthetic_diagnostic`과 `screening_only` 결과는 strict packet까지 검사하더라도 `DIAGNOSTIC_PACKET_NOT_PROMOTED`로 남습니다. `qualified_actual`은 요청 플래그만으로 승격되지 않고 `prism.provider_qualification_evidence.v1` 자격 기록과 source digest 일치까지 요구합니다. 또한 `input_origin=synthetic` 요청은 자격 sidecar가 있어도 요청 생성 단계에서 거부하여 합성 입력이 실제 적격 packet으로 표시되는 경로를 막습니다. 현재 외부 `lh2dt_models`의 7개 설비 클래스는 native 사고 export를 구현했으며, 실제 적격 packet은 0건입니다. 요청에는 선택적으로 `prism.equipment_state_snapshot.v1` 상태 snapshot을 넣을 수 있으며, canonical digest·설비 ID가 맞고 사고 전용 키가 없을 때만 provider로 전달됩니다. 요청 예시는 `examples/equipment_accident_export_request.json`, 상세 계약과 provider 구현 예시는 [외부 설비 사고방출 export 계약](docs/PRISM_외부설비_사고방출_export_계약_20261011.md)에 기록했습니다. 보완 기록은 [합성 입력의 적격 provider 승격 차단](docs/PRISM_합성입력_적격provider_차단_개발기록_20261009.md)입니다.

**설비 진단 adapter 공통 실행기 (2026-10-14):** `diagnostic_adapter_runner.py`가 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기 7개 adapter를 catalog에서 읽고, 각 클래스의 `export_accident_history(request)`를 해석합니다. host가 실제 provider 인스턴스를 명시적으로 등록하거나 `register_provider_from_config()`에 생성자 인자를 모두 넘겨야 실행되며, 정상상태 모델의 `evaluate()`·`simulate()`를 사고 packet으로 대신 사용하지 않습니다. `register_provider_instance()`와 `register_provider_instance_from_config()`로 같은 adapter 종류의 실제 탱크·배관·밸브를 서로 다른 `instance_id`에 분리 등록할 수 있고, 실행 결과에는 사용한 물리 설비 ID가 남습니다. `to_consequence_request()`는 strict 방출 이력을 명시적 기상·점화·공간영역·평가시계 context에 붙이고 빈도는 추가하지 않습니다. `make_resolver()`를 `RealtimeConsequenceMonitor`에 넘기면 상태 정규화→provider 방출→strict packet→피해 계산이 같은 callback 경계에서 이어지며, `state_snapshot_builder`를 추가하면 동일 상태의 canonical snapshot과 digest도 provider 요청에 전달됩니다. `scripts/audit_diagnostic_adapter_registry.py`의 live 감사는 7/7 클래스 해석, provider 인스턴스 0개, qualified packet 0개를 기록했습니다. 이는 설비별 호출 계약을 연결한 결과이며 빈도나 시설 QRA를 승격한 결과가 아닙니다. [공통 실행기 개발기록](docs/PRISM_설비진단_adapter_공통실행기_개발기록_20261014.md)

**외부 LayeredTank 실행기 smoke (2026-10-14):** `scripts/run_diagnostic_adapter_runner_smoke.py`는 외부 `lh2dt` LayeredTank를 명시적 생성자 설정으로 실제 1회 만들고 공통 runner를 통해 liquid accident export를 호출합니다. 합성 `1e-6 m²` 개구와 양수 재고 임계값 진단에서 strict packet의 질량 잔차는 `0 kg`, 엔탈피 잔차는 약 `-4.44×10⁻¹⁶ J`, 신규 실행 시간은 약 `1556 ms`였습니다. `provider_instance_count=1`을 확인했지만 `qualified_provider_packet_count=0`, `provider_packet_promoted=false`입니다. 따라서 이 smoke는 adapter 호출·strict 경계 검증이지 현장 빈도, 시설 IR/F-N, 독립 물리검증 또는 1 Hz 계산의 증거가 아닙니다. [결과 예시](examples/diagnostic_adapter_runner_layered_tank_smoke.json) / [실행기록](docs/PRISM_설비진단_adapter_공통실행기_개발기록_20261014.md)

**native LayeredTank와 문헌 빈도 연결 진단 (2026-10-18):** `scripts/run_lh2dt_native_frequency_case.py`는 기존 혼합 캠페인의 `LH2_VESSEL AREA_0.01%` 문헌 빈도를 그대로 적용하고, 해당 사건의 방출 시간 이력만 외부 `LayeredTank.export_accident_history()`에서 다시 받아 `ResolvedLiquidRelease`와 SLABx-LH2/피해 체인으로 전달합니다. 개구 `0.0127 m` exact-match, native 질량 잔차 `0 kg`, native export 약 `0.29 s`, 전체 캠페인 실행 약 `23.8 s`, 해당 사건 `EXECUTED_OPERATOR_LIMITED`를 기록했습니다. 이 결과는 **문헌 빈도 → native 방출 → 피해** 연결을 확인하는 진단이며, synthetic 초기상태·형상·대기경계·작은 선언형 풀 footprint와 부분 사고범위 때문에 `qualified_provider_packet_count=0`, `provider_packet_promoted=false`, 시설 총 IR/F-N은 계속 보류합니다. [실행기록](docs/PRISM_외부LH2모델_native_사고계약_감사_20261018.md) / [검증 요약](examples/native_lh2dt_frequency_case_verification.json)
저장탱크 worklist `AREA_0.01%`도 `provider_instance_id=storage-tank-01`로 실행해 event/component/port/opening exact-match와 strict release→consequence context→synthetic final chain 연결을 확인했습니다. chain은 약 11.22초에 끝났고 질량 잔차는 약 `-9.92×10⁻¹⁸ kg`였으며, 문헌 빈도는 자동 결합하지 않았습니다. [worklist 결과](examples/diagnostic_adapter_runner_worklist_storage_001.json)

**provider-resolved pool footprint 경계 (2026-10-18):** 액체 provider가 `prism.resolved_pool_footprint.v1`의 반경·충돌 위치·근거·결과 digest를 내보내면 PRISM이 그 반경을 thermal pool context에 exact-match로 전달합니다. 지면 액체가 없다는 provider 결과는 `prism.no_rainout_evidence.v1`로 명시할 수 있으며, 이 경우 요청 template의 declared-sensitivity pool을 자동으로 제거합니다. digest나 thermal context가 없으면 거부하며, 기존 packet처럼 footprint와 no-rainout 근거가 모두 없을 때는 `declared_sensitivity` 진단만 허용합니다. 현재 native LayeredTank·DynamicHEMPipe는 이 footprint/no-rainout 근거를 아직 내보내지 않으므로 해당 결과는 계속 `operator-limited`입니다. 계약 상세는 [native 사고계약 감사](docs/PRISM_외부LH2모델_native_사고계약_감사_20261018.md)에 기록했습니다.

**첫 실행형 외부 provider adapter:** `scripts/export_lh2dt_prism_accident_packet.py`는 외부 `HomogeneousTank`+`Valve`를 명시적인 failed-opening 시나리오로 실행하고, 시간 이력·provider 질량 장부·출구 상태를 `prism.resolved_release.v1`로 변환합니다. 2026-10-11 smoke는 0.2초 packet과 strict 질량 폐합을 확인했지만 입력이 합성 진단이므로 `provider_packet_promoted=false`입니다. `LayeredTank`, 배관, 밸브, 벤트, 펌프, 기화기, 재액화기의 실제 설비 사고 export와 현장 자료가 들어오기 전에는 일반 시설 QRA로 승격하지 않습니다.

**LayeredTank 재고 피드백용 strict packet (2026-10-12):** `scripts/export_lh2dt_layered_tank_prism_packet.py`는 외부 `LayeredTankNetworkSimulator+CommandedValve`의 탱크 상태·명령 밸브·양수 재고 threshold 시계를 `prism.external_accident_history.v1`로 감싼 뒤, 기존 `equipment_release_adapter.py`를 통해 `prism.resolved_release.v1` 액체 packet을 생성합니다. provider가 반환한 16개 구간을 왼쪽 유지 시간 이력으로 보존하고, 지면 액체 질량·누적 엔탈피·종료 basis를 다시 적분해 질량 잔차 `1.73e-18 kg`, 에너지 잔차 `0 J`를 확인했습니다. Hydrogen 물성 기준도 packet에 명시합니다.

다음 명령으로 재현합니다.

```powershell
.venv\Scripts\python.exe scripts/export_lh2dt_layered_tank_prism_packet.py `
  --lh2dt-root "C:\path\to\lh2dt_models" `
  --output-dir results/20261012/layered_tank_prism_packet5 `
  --time-step-s 0.5 --target-release-kg 0.01 `
  --full-open-area-m2 1e-6
.venv\Scripts\python.exe scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261012/layered_tank_prism_packet5/resolved_release.json `
  --output-dir results/20261012/layered_tank_prism_chain5
```

이 chain은 `DynamicLH2PoolX → SLABx-LH2/SLABx → cloud → 점화 → 화재·폭발 → TNO 피해`까지 실행되어 `END_TO_END_DIAGNOSTIC_EXECUTED`를 반환했습니다. 수영장 반경 `0.005 m`는 작은 합성 packet에서 wet-cell 조건을 확인하기 위한 **선언된 민감도 footprint**이며 시설 바닥 형상이나 실제 누출 면적을 추정하지 않습니다. 외부 provider는 액체 출구를 직접 계산하지만 flash·공기 중 액적·현장 개구·차단 신뢰도는 아직 제공하지 않으므로 이 결과는 `synthetic_diagnostic`, `operator-limited`, `provider_packet_promoted=false`입니다. 빈도, 시설 IR/F-N, 독립 물리검증을 자동으로 부여하지 않습니다.

**DynamicHEMPipe 사고 packet (2026-10-12):** `scripts/export_lh2dt_dynamic_pipe_prism_packet.py`는 외부 `DynamicHEMPipe`의 유한체적 상태와 full-bore 대기 출구를 같은 strict adapter로 변환합니다. 0.001 s를 10개 provider interval로 계산한 packet은 질량 잔차 `0 kg`, 에너지 잔차 약 `5.42e-20 J`를 보존했고, `synthetic_diagnostic_horizon` 종료 basis와 잔류 pipe inventory를 명시했습니다. 작은 packet의 pool footprint는 `radius_m=0.0001 m`인 선언된 sensitivity 값으로만 사용했습니다. 이 packet도 동일한 consequence chain을 끝까지 통과하지만, 짧은 고정 시계·합성 형상·flash/airborne-liquid closure·현장 검증은 미완료입니다.

**VentStack 사고 packet (2026-10-12):** `scripts/export_lh2dt_vent_stack_prism_packet.py`는 외부 `VentStack.evaluate()`의 steady two-port 결과를 명시적인 0.5초·10구간 synthetic diagnostic horizon으로 감싸고, `ResolvedGasRelease` strict packet으로 변환합니다. 기본 진단은 102 kPa upstream, 0.01 m stack bore를 사용해 저 Mach 대기 출구 조건을 만족시켰으며, 질량·정적 엔탈피 잔차는 각각 `0 kg`, `0 J`였습니다. 이 결과는 탱크 재고 소진·PSV setpoint·현장 벤트 빈도를 계산하지 않습니다. 같은 packet은 gas vector/SLABx·점화·화재/폭발·TNO 피해 chain까지 실행되며 `provider_packet_promoted=false`로 남습니다.

**DynamicVaporizer·DynamicReliquefier 사고 packet (2026-10-12):** `scripts/export_lh2dt_dynamic_vaporizer_prism_packet.py`는 외부 유한체적 기화기 또는 재액화기의 질량·내부에너지·벽 상태를 매 구간 다시 계산하고, 명시한 대기 밸브 면적·방출계수와 `StrokeLimitedCommandedValve`의 유한 stroke로 기체 출구를 만들었습니다. `--mode vaporizer`와 `--mode reliquefier`를 같은 strict gas adapter에서 지원합니다. 기본 각 packet은 0.5초·10구간, 질량 잔차 `0 kg`, 정적 엔탈피 잔차 약 `1.78e-15 J`이며 SLABx 확산·점화·화재/폭발·TNO 피해까지 끝까지 실행했습니다. 이 경계는 정상 `step()` 결과를 사고로 자동 승격하지 않고, 명시적인 사고 포트·대기 밸브·합성 진단시계만 사용합니다. 따라서 잔류 재고·열교환기 고장모드·차단 정책·현장 빈도·물리 검증은 여전히 미완료이며 두 packet 모두 `provider_packet_promoted=false`입니다.

**압축성 source-state adapter (2026-10-16):** 고속 packet을 대기 출구 속도만으로 underexpanded jet으로 취급하지 않습니다. 외부 `lh2dt` provider가 각 구간의 상류·throat 상태를 함께 export해야 하며, `src/lh2_tno/compressible_source_adapter.py`와 `scripts/build_compressible_plane_handoff.py`가 exact result digest와 질량·운동량·에너지 장부를 확인한 뒤 선택형 handoff를 만듭니다. source/throat 자료가 없는 기존 G1 packet은 `COMPRESSIBLE_PLANE_HANDOFF_SOURCE_STATE_BLOCKED`로 남습니다. 합성 1 MPa smoke는 handoff 최대 Mach `3.9982`, 에너지 잔차 `0 J/kg`를 보였지만 provider 승격·독립 물리검증·시설 IR/F-N·빈도 승격은 하지 않았습니다. 상세 계약은 [`docs/PRISM_압축성근접장_source_state_adapter_20261016.md`](docs/PRISM_압축성근접장_source_state_adapter_20261016.md)에 있습니다.

**MappedPump 사고 packet (2026-10-12):** `scripts/export_lh2dt_mapped_pump_prism_packet.py`는 외부 `MappedPump`의 H-Q-N map을 액체 공급 상태와 downstream 압력에 적용하고, 별도 대기 밸브가 계산한 방출 유량과 비교합니다. 두 유량의 상대오차가 2%를 넘으면 packet을 거절합니다. 기본 0.2초·10구간 liquid packet은 질량 잔차 `0 kg`, 에너지 잔차 약 `-1.39e-17 J`로 `DynamicLH2PoolX`·SLABx·점화·화재/폭발·TNO 피해까지 통과했습니다. 펌프 자체에는 재고가 없으므로 `available_mass_kg`는 명시된 feed-through 진단 reserve이며, 펌프 seal 고장·탱크 재고·차단·빈도·독립검증을 의미하지 않습니다. 이 결과도 `provider_packet_promoted=false`입니다.

**설비 adapter와 worklist 구조 대조 (2026-10-14):** 저장탱크 5개, `MappedPump` G1/G2, `DynamicVaporizer` G3, `DynamicReliquefier` G6, `DynamicHEMPipe` transfer-line 5개, `Valve` transfer-valve 5개를 facility manifest의 실제 component·accident port·개구값으로 명시적으로 바인딩했고, `VentStack` G1은 별도 emergency-relief 계약으로 연결했습니다. 여기에 `DynamicVaporizer`의 G1/G2 재고 방출과 `DynamicReliquefier`의 G4/G5 양단 파열 set을 추가했습니다. 세 release family를 분리한 coverage gate는 **24/24 `EXACT_MATCH`**, `UNMATCHED=0`, `extra=0`입니다. 이 수치는 event/component/port/경계/개구 계약이 맞는다는 구조 증거이며, 24 packet 모두 `synthetic_diagnostic`이라 실제 적격 provider packet·현장 빈도·시설 IR/F-N 승격은 계속 0 및 보류입니다. 결과는 `results/20261014/combined_provider_catalog_family_coverage_v5.json`입니다.

이번 단계의 상세한 재고 방출·양단 파열 계약과 실패 조건은 [재고·양단방출 통합 개발기록](docs/PRISM_재고·양단방출_통합_개발기록_20261014.md)에 정리했습니다.

**혼합 LH2 시설 캠페인 연결 (2026-10-14):** `scripts/build_lh2_mixed_provider_campaign.py`는 우발 누출·비상 릴리프·재고 방출·양단 파열 catalog를 이벤트 ID별로 하나의 `RiskCampaign`에 결합합니다. 같은 설비와 같은 개구를 공유하는 두 사건도 이벤트 ID를 먼저 선택해 잘못된 요청 복사를 막습니다. 일반 provider packet의 좌표를 시설 포트에 배치해야 할 때만 `--rebase-positions`를 사용하며, 이는 provider의 유량·열역학·재고 이력을 바꾸지 않고 매니페스트가 검토한 위치만 적용합니다. `scripts/run_lh2_mixed_provider_campaign.py`는 이 캠페인을 실제 SLABx-LH2/SLABx/TNO backend에 넣고 `EXECUTED`, `EXECUTED_OPERATOR_LIMITED`, `FAILED`, `UNCOMPUTED`를 모두 장부에 보존합니다. 보완 코드의 24건 전체 재실행은 5건 `EXECUTED`, 19건 `EXECUTED_OPERATOR_LIMITED`, 0건 `FAILED`, 0건 `UNCOMPUTED`로 기록됐습니다. bounded pool observation으로 transfer-valve deadline과 작은 pool 표적이 회복됐고, 양단 G4/G5는 풍하측 실제 전이행을 거쳐 endpoint 계산까지 도달했습니다. 세 transfer-line puff handoff는 먼저 provider 방출시간을 보존한 finite-clock native puff로 재시도하며, backend가 그 경계를 거부할 때만 순간화합니다. 현재 별도 replay에서는 3/3이 finite-clock 경로를 사용했지만 native puff 근사·provider 자격·물리검증이 없으므로 여전히 `EXECUTED_OPERATOR_LIMITED`입니다. transfer-valve deadline 초과는 bounded pool observation으로 해소됐습니다. 알려진 `worker-01` 기여 IR은 중앙 문헌 빈도에서 `1.749e-05/year`지만 시설 전체 IR/F-N은 계속 보류합니다. 공식 결과는 `results/20261014/generic_mixed_provider_campaign_refined_pool_result.json`과 `results/20261014/generic_lh2_mixed_facility_assessment_refined_pool.json`이며, 설명과 문헌 p05/중앙/p95 및 독립 이벤트 비교는 [혼합 LH2 시설 캠페인 연결 기록](docs/PRISM_혼합LH2_시설캠페인_연결_개발기록_20261014.md)과 `examples/generic_lh2_mixed_frequency_scenarios.json`에 있습니다.

**선택 packet 재결합 실행 (2026-10-15):** `scripts/rebind_campaign_to_worklist_packets.py`는 evidence 스캔에서 exact/strict로 선택된 packet만 읽어 strict `RiskCampaign`을 다시 만듭니다. provider의 유량·열역학·종료시계·source/result digest는 그대로 소비하고, 기존 캠페인이 선언한 facility port 배치는 명시적으로 보존합니다. 24개 packet의 digest 쌍은 24/24로 일치했습니다. 새 백엔드 실행은 4건 `EXECUTED`, 19건 `EXECUTED_OPERATOR_LIMITED`, 1건 `FAILED`로 기록됐습니다. 실패 사건은 `ambient-vaporizer/G1`이며 provider가 고속 출구(Mach 저마하 가정 초과)를 제공해 현재 확산 어댑터가 `compressible/underexpanded plane adapter required`로 중지했습니다. 이 실패를 시간 연장·유량 재계산·다른 packet 대체로 숨기지 않고 미계산으로 남겼습니다. 결과는 `results/20261015/generic_mixed_provider_campaign_worklist_rebound_result.json`, packet 결합 감사는 `results/20261015/generic_lh2_diagnostic_campaign_binding_worklist_rebound.json`입니다. 따라서 packet identity 소비는 진전됐지만, 23/24 risk-atom만 계산되며 qualified provider, 문헌 빈도, 시설 전체 IR/F-N, 독립 물리검증은 여전히 보류합니다.

**압축성 기체 plane handoff 계약 (2026-10-16):** `ResolvedGasRelease.compressible_plane_handoff`를 추가했습니다. 고속 또는 underexpanded 출구는 출구 속도만으로 PRISM이 팽창·혼합·회전시키지 않고, provider가 downstream plane의 위치·방향·속도·밀도·온도·수소 질량분율·단면을 시간별로 제공해야 합니다. 각 plane 상태의 `rho × velocity × 2·half_width × depth × H2 fraction`은 원 provider 수소 질량유량과 닫혀야 하며, 이 계약이 없으면 기존 저마하 guard가 계속 거절합니다. `scripts/validate_compressible_plane_handoff.py`로 packet을 별도 검증할 수 있습니다. 선택된 G1 packet은 `COMPRESSIBLE_PLANE_HANDOFF_BLOCKED`로 남았고, 이전 저마하 packet만 `DIRECT_LOW_MACH_GAS_EXIT_VALIDATED`를 반환했습니다. 합성 carrier plane으로 `ambient-vaporizer/G1`을 시험한 결과는 `END_TO_END_DIAGNOSTIC_EXECUTED`와 handoff 19개 소비를 확인했지만, provider packet에서 생성한 handoff가 아니므로 `operator_limited`, `physical_validation_claim=false`, `facility_qra_claim=false`입니다. 이 시험은 어댑터 연결을 검증한 것이며 실제 G1 결과를 승격하지 않습니다. 기록은 `results/20261016/compressible_plane_adapter_chain_smoke.json`입니다.

대표 1 m 배관 구간에 `location_weight=0.1`을 명시한 후속 계획(`examples/generic_lh2_mixed_frequency_plan.json`)에서는 24개 요청이 모두 물리 실행 단계까지 도달했습니다. bounded pool observation을 적용한 공식 재실행은 5건 실행·19건 연산자 제한·0건 backend 실패로 남았습니다. 배관 위치 미계산은 사라졌지만 실제 pool 형상과 세 transfer-line puff 시간분포 검증이 남아 시설 전체 IR/F-N은 여전히 보류합니다.

`--pool-radius-m 0.005`를 사용한 declared-sensitivity 진단은 실제 시설 바닥 형상을 추정하지 않습니다. bounded pool observation은 작은 방출에서 젖은 격자보다 먼저 기록된 증발 질량을 명시된 source footprint에 귀속하지만, provider가 계산한 실제 pool footprint 또는 `no_rainout` 판정을 대신하지 않습니다.

**DynamicHEMPipe transfer-line 및 VentStack relief 연결 (2026-10-12):** `scripts/export_lh2dt_dynamic_pipe_prism_packet.py`에 worklist의 `event_id`·`port_id`를 직접 바인딩하는 옵션을 추가하고, transfer-line 5개 개구를 외부 `DynamicHEMPipe`의 full-bore 대기 경계로 각각 실행했습니다. 다섯 packet은 구조적으로 exact-match되었지만, 모두 합성 diagnostic이고 잔류 배관 재고를 보존합니다. 가장 작은 0.01% case는 synthetic facility에서 방출→SLABx→피해 chain까지 실행했으며, 일부 더 작은 질량 case는 SLABx 계산의 `x must be non-decreasing` 오류로 `UNCOMPUTED`에 남아 있습니다. 이 오류를 우회해 빈 방출을 만들거나 시간을 늘리지 않습니다.

`VentStack`은 random hole이 아니라 `maximum_relief_discharge` 사건이므로 `EmergencyReliefExportRequest`와 `export_equipment_emergency_relief_history`를 별도로 사용합니다. `scripts/export_lh2dt_vent_stack_prism_packet.py`는 failure opening을 packet에 넣지 않고 `emergency_relief_discharge` 종료근거를 보존합니다. 기화기 adapter는 `instantaneous_inventory`에서 provider가 대기압 평형 재고 소진을 선언하고, `inventory_over_600s`에서는 정확히 600초의 이력을 반환합니다. 새 packet에는 임의의 failure opening을 붙이지 않으며, 기존 진단 packet에 면적 메타데이터가 남아 있어도 inventory 빈도 binding은 그 값을 문헌 hole 구경으로 사용하지 않습니다. 재액화기 adapter는 한 공유 finite-volume 상태에서 두 개의 명시적 rupture endpoint를 계산해 `prism.resolved_release_set.v1`로 저장합니다. G2는 실제 synthetic chain까지 실행됐고 G1은 고압·작은 진단 면적 조합에서 저마하 범위를 넘어 fail-closed로 남겼습니다. G4/G5 양단 set은 구조적으로 exact-match되지만 반대 방향 endpoint 중 상류 제트가 현재 SLABx handoff 방향 제한에 걸려 피해 chain은 미계산입니다. 이 결과를 실제 빈도나 시설 IR/F-N으로 승격하지 않습니다.

**Valve 및 펌프 G1 연결 (2026-10-13):** `scripts/export_lh2dt_valve_prism_packet.py`는 외부 `Valve`의 full-open LH2 출구와 대기 상태를 계산해 transfer-valve 5개 hole bin에 exact-match합니다. `MappedPump` adapter는 G1의 0.025 m 개구에도 H-Q-N map과 대기 밸브 유량 일치 gate를 적용했습니다. 두 경로 모두 질량·엔탈피 잔차를 확인하고 `DynamicLH2PoolX`·SLABx·점화·피해 chain을 대표 case에서 실행했지만, 설비 재고·seal/valve 고장확률·현장 빈도는 소유하지 않으므로 합성 packet으로만 남깁니다.

이 첫 액체 packet은 `scripts/validate_lh2dt_prism_packet_chain.py`로 DynamicLH2PoolX·SLABx-LH2·SLABx·점화·화재/폭발·TNO 피해까지 연결할 수 있습니다. 외부 packet의 `ParaHydrogen`과 native DynamicLH2PoolX의 `Hydrogen` 기준이 다르므로 `PoolBoundary`의 `fluid_translation="para_hydrogen_to_hydrogen"`와 provenance를 반드시 선언합니다. 선언이 없으면 계산을 거절하며, 선언이 있어도 교차 물성 검증 전까지 operator-limited로 기록합니다. 실행 결과는 `results/20261011/lh2dt_prism_chain_liquid8`에 남기고 시설 IR/F-N이나 빈도를 자동으로 부여하지 않습니다.

**외부 `lh2dt` 방출 이력과 SLABx 경계 진단:** `scripts/export_lh2dt_accident_history.py`는 외부 모델의 탱크 질량 장부와 엔탈피·엔트로피 상태를 보존한 채 SLABx 브리지 입력을 만듭니다. 포화 2상 상태를 압력·온도만으로 재해석하지 않도록 `slabx_provider_boundary.py`가 provider 상태의 등엔트로피 HEM 경계를 사용하고, `scripts/audit_lh2dt_slabsx_rate_boundary.py`가 총 유량을 5% gate로 비교합니다. 2026-10-09 합성 진단에서는 provider 질량 잔차가 약 `1.76e-15 kg`, 최대 상대 유량 오차가 `0.015324%`로 gate를 통과했고, `storage` 예제 설비에서 SLABx→PRISM 최종 피해 체인까지 실행했습니다. 이 결과는 합성 진단이며 실제 provider packet·빈도·독립 물리검증·시설 전체 IR/F-N으로 승격하지 않았습니다. [외부 lh2dt 사고방출 연결 진단](docs/PRISM_lh2dt_사고방출_연결진단_20261009.md)에 실행 명령과 남은 보완 항목을 기록했습니다.

추가로 `scripts/validate_layered_tank_inventory_slabsx.py`는 외부 `lh2dt.LayeredTankNetworkSimulator`의 액체 셀 상태를 구간마다 feedback하고, 문헌 `LH2_VESSEL AREA_0.01%`의 `0.0127 m` 개구와 exact-match한 packet을 만들 수 있습니다. 이 진단은 provider 질량 잔차 `2.71e-19 kg`, SLABx 유량 오차 `0.119%`, 최종 chain 잔차 `0 kg`을 확인했으며, 실제 설비 packet·현장 종료시간·빈도·시설 QRA로 승격하지 않습니다. 최종 피해를 예제 `storage/storage.out`에 실행할 때는 packet의 실제 식별자와 synthetic facility 식별자 rebinding을 별도로 기록합니다.

저장탱크 다섯 개구를 한 번에 반복 확인하려면 `scripts/build_layered_tank_worklist_packets.py`를 사용합니다. 2026-10-10 합성 진단은 문헌 작업목록 24건 중 `storage-tank-01`의 `AREA_0.01%`부터 `AREA_100%`까지 5건을 외부 `lh2dt.LayeredTankNetworkSimulator`와 SLABx-LH2에 exact-match했고, 최대 provider 질량잔차 `4.09e-18 kg`, 최대 유량 오차 `0.11915%`를 기록했습니다. 당시 결과는 구조 연결용이며 `provider_packet_promoted=false`, 실제 적격 provider packet 0건, 나머지 19건 `UNMATCHED_NO_PROVIDER_PACKET`인 2026-10-10 시점의 snapshot이다. 2026-10-15 최신 evidence-only 스캔에서는 외부 진단 packet이 24개 worklist 모두로 확장되었다. 상세 기준은 [lh2dt 사고방출 연결 진단](docs/PRISM_lh2dt_사고방출_연결진단_20261009.md), [provider coverage gate](docs/PRISM_provider_catalog_coverage_20261009.md), [worklist packet 증거 감사](docs/PRISM_worklist_패킷증거감사_20261015.md)에 기록합니다.

**저장탱크 차단 성공·실패 branch 진단 (2026-10-11):** `scripts/build_layered_tank_isolation_branches.py`는 각 저장탱크 hole event에 대해 provider가 소유하는 합성 LayeredTank 상태를 만들고, `CommandedValve`를 구간 경계에서 닫는 `isolation-success`와 닫히지 않는 `isolation-failure` 이력을 각각 생성합니다. 성공 branch는 `close_command_time_s=0.10 s` 뒤 `post_close_observation_delay_s=0.05 s` 동안 0 유량을 관찰한 경우에만 종료하고, 실패 branch는 0.50 s diagnostic horizon에서 열린 상태로 남깁니다. 5개 저장탱크 event, 10개 branch를 실행한 결과 7개 branch history가 생성되었고 4/24 event가 적어도 한 branch와 exact-match되었습니다. 큰 개구 3개 branch는 외부 solver의 `All cell masses must be finite and positive` 오류를 그대로 `UNCOMPUTED`로 보존했습니다. 성공확률 `0.99`와 실패확률 `0.01`은 요청 branch 구조를 시험하기 위한 합성값이며 현장 차단 신뢰도나 사고빈도가 아닙니다. 따라서 실제 적격 provider packet은 0건이고 시설 IR/F-N 승격도 차단되어 있습니다. 결과는 `results/20261011/layered_tank_isolation_branches_all/`에 저장합니다.

**provider 종료시계 연결 (2026-10-11):** strict `ResolvedGasRelease`/`ResolvedLiquidRelease` packet은 `termination_basis`를 보존합니다. request defaults가 `basis=provider_declared`, `time_s=provider_duration`을 명시한 경우에만 provider가 선언한 종료근거와 실제 packet 지속시간을 캠페인 요청에 복사하고 provider의 step breakpoint를 평가시계에 추가합니다. basis가 없는 예전 packet은 거절하며 시간이나 빈도를 추정하지 않습니다. 예시는 `examples/provider_request_defaults_liquid_provider_duration.json`입니다. 한 저장탱크 `AREA_0.01%`의 합성 성공·실패 두 branch는 방출→SLABx-LH2→pool/dispersion→cloud→fire/explosion 피해까지 실제 실행되었고 case 시간은 약 5.59–19.52 s였습니다. 이 실행은 operator-limited이고 24개 사건 중 두 branch만 계산했으므로 시설 전체 IR/F-N은 계속 보류합니다. 합성 진단 형상은 수평 대기 출구를 사용하며 수직 아래 출구는 provider가 수평 handoff를 명시하지 않으면 fail-closed로 거절합니다.

**수치 안정성 재시도:** 큰 개구 branch에서 외부 LayeredTank RK 중간단계가 양수 셀 질량을 위반하면, 진단 스크립트가 provider 소유 `tank.simulate(minimum_step_s=step/128)`로 한 번만 재시도합니다. 재시도는 10% 성공 branch를 통과시켰지만 10% 실패와 100% 성공·실패는 같은 양수 질량 오류를 반환했습니다. 두 시간간격(0.05 s, 0.005 s)과 adaptive retry 결과가 모두 7/10 branch 생성으로 일치하므로, 세 branch는 미계산으로 보존합니다.

**저장탱크 branch 전체 합성 실행 (2026-10-11):** 최신 compiled campaign을 24개 문헌 initiating event와 함께 실행한 결과, 생성된 저장탱크 branch 중 7건이 source→SLABx-LH2→pool/dispersion→cloud→fire/explosion 피해 단계를 통과했고 21건은 개구 불일치·branch 누락·provider packet 부재로 `UNCOMPUTED`에 남았습니다. 계산된 7건도 provider가 합성 상태·종료시계·차단을 소유하므로 `EXECUTED_OPERATOR_LIMITED`이며, 생성 빈도 `0.0138259/year`를 시설 전체 위험으로 해석하지 않습니다. 최신 결과는 `results/20261011/layered_tank_isolation_branches_all/campaign_result_full.json`과 `accident_scope_matrix_full.json`에 기록했습니다.

**일반 LH2 설비 범위 진단:** 탱크·이송배관만 있는 기본 예제와 별도로, [일반 LH2 설비 범위 진단 기록](docs/PRISM_일반LH2_설비범위_진단_20261009.md)의 합성 매니페스트에는 탱크·배관·밸브·벤트·펌프·기화기·재액화기·경계를 포함했습니다. 현재 검토된 문헌 프로파일과 명시적인 열교환기 측면 분류로 24개 initiating event를 만들고, 경계 컴포넌트는 사고 빈도에서 제외합니다. 이 진단은 빈도 범위 연결만 확인하며 provider 방출 장부나 시설 IR/F-N을 생성하지 않습니다. 실제 설비에서 열교환기 측면 분류가 확인되지 않으면 기화기·재액화기는 자동 대체하지 않고 다시 미계산으로 둡니다.

**빈도→방출 요청 작업목록:** [방출 요청 작업목록 기록](docs/PRISM_방출요청_작업목록_20261009.md)과 `scripts/build_provider_release_worklist.py`는 위 24개 사건을 설비별 provider packet 요청으로 펼칩니다. 실제 적격 provider packet은 여전히 0건이다. 다만 2026-10-15 저장된 외부 모델 진단 결과는 24건 모두 exact/strict packet 증거와 대조되었고, 15건은 consequence-chain 기록까지 있다. 이 진단 결과를 정상 유량·센서 시계열 또는 현장 사고 방출로 승격하지 않습니다. packet이 들어오면 개구·설비·포트·종료 basis를 exact-match한 뒤에만 피해영향 campaign으로 보냅니다.

합성 `lh2dt→SLABx-LH2` 진단은 이 작업목록의 저장탱크 `AREA_0.01%` 사건에 대해 `storage-tank-01/tank-accident-out/0.0127 m` 경계를 구조적으로 exact-match했고, 2026-10-15에는 저장탱크 5개 개구까지 같은 identity 계약으로 확장했다. 종료시계·기상·재고가 합성이므로 실제 provider packet·빈도·시설 QRA로 승격하지 않습니다. 전체 24개 worklist의 최신 packet 증거 결과는 `examples/generic_lh2_provider_worklist_packet_evidence.json`과 [worklist packet 증거 감사 기록](docs/PRISM_worklist_패킷증거감사_20261015.md)에 남습니다.

worklist identity를 보존한 LayeredTank packet을 직접 만들 때는 export 명령의 `--event-id`와 `--port-id`를 지정합니다. `--full-open-area-m2`는 worklist 개구에서 계산하고, 출력 폴더에는 `provider_response.json`, `resolved_release.json`, `verification.json`을 함께 둡니다.

```powershell
python scripts/export_lh2dt_layered_tank_prism_packet.py `
  --lh2dt-root "<lh2dt 모델 루트>" `
  --output-dir results/20261015/storage_tank_worklist_packets/AREA_0.01pct `
  --component-id storage-tank-01 `
  --port-id tank-accident-out `
  --event-id "generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%" `
  --full-open-area-m2 0.000126676869774374
```

이 export는 외부 모델의 synthetic geometry와 종료시계를 보존하는 진단 packet이다. 실행 뒤 `scripts/audit_provider_worklist_packet_evidence.py`를 사용해 전체 worklist와 대조하고, qualified packet·빈도·시설 위험으로 자동 승격하지 않는다.

provider packet이 들어오면 먼저 `scripts/audit_provider_catalog_coverage.py`로 작업목록과 대조합니다. 이 단계는 event/component/포트/개구/기체·액체 경계를 exact-match하고, 빠진 사건과 작업목록 밖 packet을 별도로 기록합니다. `FULLY_MATCHED`도 빈도 부여나 물리 검증 완료를 뜻하지 않으며, 이후 strict request context와 facility IR/F-N gate가 필요합니다. 자세한 사용법은 [provider packet coverage gate 기록](docs/PRISM_provider_catalog_coverage_20261009.md)을 참고합니다.

외부 [LH2 디지털 트윈 스크리닝 연결 감사](docs/PRISM_외부LH2DT_스크리닝_연결감사_20261009.md)는 12개 자산·8개 시나리오·21개 노드/27개 간선과 별도 공정 진단 후보 목록(고장 후보 444개·point 546개·센서 후보 62개·비상 시나리오 31개)을 근거로 보존하지만, live I/O·확정 센터 자산·전방비교 준비·사고 방출 packet이 없으므로 PRISM provider packet으로 승격하지 않습니다.

**설비 관측자료 물리검증 감사 (개발 소스):** `scripts/audit_equipment_validation_evidence.py`는 액화수소 저장탱크의 닫힌 운전 관측자료 4건(학습 후보 2건·holdout 후보 2건, 21행·34채널)과 독립 검증 gate 8건을 점검합니다. 현재 검증 방출 0건·simulator 호출 0건이며 topology도 `screening_only`이므로, 이 자료는 사고 방출 packet·빈도·SLABx-LH2 검증·시설 IR/F-N으로 승격되지 않습니다. 결과는 [설비 관측자료와 물리검증 근거](docs/PRISM_설비관측_물리검증_근거_20261009.md)와 `results/20261009/validation_evidence/equipment_validation_audit.json`에 해시와 함께 보존합니다.

**검증근거 통합장부 (2026-10-22):** `scripts/build_validation_evidence_matrix.py`는 DynamicLH2PoolX 제한 구성요소 재실행, 설비 정상 운전 관측자료, 외부 native 사고 export 계약, 조건부 시설 진단, IJHE 완료 감사, 외부 LH2 탱크·PSV·TNO 스윕의 폐합·처리시간 근거를 6개 영역으로 관리합니다. 각 근거의 허용 범위를 별도로 기록하며, 구성요소·인터페이스·조건부 진단·외부 스윕이 `physical_validation_claim` 또는 `facility_qra_claim`을 자동으로 열지 못하게 합니다. 최신 장부는 `results/20261022/validation_evidence_matrix_repaired_valve_transfer_line_replacement.json`이고 상태는 `RESTRICTED_EVIDENCE_MATRIX`, 판정은 `FACILITY_QRA_WITHHELD`입니다. [통합장부 설명](docs/PRISM_검증근거_통합장부_20261022.md)

IJHE 감사에 `--validation-evidence-matrix`를 주면 이 장부를 29번째 진단 검사로 기록합니다. 부분 coverage에 qualified packet 일부가 있어도 현재 상태 장부가 `0건` 또는 `false`이면 그 값을 덮어쓰지 않으며, `actual_provider_release_packet` 검사를 통과시키지 않습니다. 이 우선순위는 일부 packet을 시설 전체 적격 packet으로 오인하지 않기 위한 fail-closed 규칙입니다.

**설비 모델 결합 감사 (개발 소스):** `scripts/audit_equipment_model_binding.py`는 일반 매니페스트의 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기·경계를 외부 `lh2dt_models` 클래스와 설비별로 매핑합니다. 최신 native 바인딩 카탈로그 `examples/generic_lh2_native_model_binding.json`은 외부 설비 7개가 정상 공정상태와 사고 export 인터페이스를 모두 제공한다는 선언을 담고, PRISM 경계 컴포넌트는 사고 빈도 대상이 아닌 별도 인터페이스로 유지합니다. native interface가 있다고 해서 현장 종료·현장 빈도·자격 packet이 자동 생성되는 것은 아닙니다. 자세한 표와 다음 입력 계약은 [설비 모델 결합 계약](docs/PRISM_설비모델_결합계약_20261009.md)과 두 카탈로그 파일에 있습니다.

2026-10-14부터 같은 감사에서 PRISM-side 진단 adapter를 별도 표시합니다. 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기 7개는 native 사고 export를 PRISM strict release로 변환할 수 있고 진단 adapter도 별도로 기록됩니다. 최신 외부 native 사고 export는 기화기·재액화기·StrokeLimitedCommandedValve·VentStack·LayeredTank·DynamicHEMPipe·MappedPump 7건으로 모두 확인되었지만, qualified provider packet은 여전히 0건입니다. 이 adapter는 합성·스크리닝 결과의 구조 연결만 확인하고 빈도·독립 물리검증·시설 IR/F-N을 승격하지 않습니다.

**외부 모델 native 계약 감사:** `scripts/audit_lh2dt_native_contract.py`는 외부 `lh2dt` 소스의 클래스 정의를 실행하지 않고 정적으로 읽어, 정상 `simulate/step/evaluate`와 사고 전용 `export_accident_history(request)`를 구분합니다. 최신 감사에서 외부 7개 설비 클래스 전부(`DynamicVaporizer`, `DynamicReliquefier`, `StrokeLimitedCommandedValve`, `VentStack`, `LayeredTank`, `DynamicHEMPipe`, `MappedPump`)의 native 사고 export가 `7/7` 확인되었고 PRISM-side 진단 adapter 계약은 `7/7`입니다. `LayeredTank` native 경계는 탱크 상태를 전진시키고 출구 flash의 기체/지상 액체 분할과 질량 장부를 반환하며, `DynamicHEMPipe`는 명시적 파손 개구의 기체 재고수지와 차단시계 종료를, `MappedPump`는 H-Q-N 운전점과 상류 재고 장부를 분리해 반환합니다. 배관 액체/2상 경계는 native `DynamicHEMPipe`에서 지원되며, airborne liquid은 0으로 보수 제한됩니다. 단일 출구 export는 `two_sided_rupture`를 결합 release-set 없이 거부합니다. 모델들은 synthetic 진단 geometry와 operator-limited 조건을 사용할 수 있습니다. 이 결과는 누출 계산이 전체 시설에 완료되었다는 뜻이 아니라, 실제 외부 solver가 사고 포트·차단·재고 종료를 반환할 수 있는 코드 경계가 모두 존재한다는 증거입니다. 최신 결과는 `results/20261022/lh2dt_native_contract_audit_native_catalog.json`에 저장되며, native 메서드가 생겨도 packet 자격·빈도·물리 검증·시설 IR/F-N gate를 별도로 통과해야 합니다. 외부 `lh2dt_models` 전체 회귀시험은 375건 통과했습니다.
**native 바인딩 일관성 감사:** `scripts/audit_native_binding_reconciliation.py`는 위 소스 감사와 PRISM 모델 카탈로그를 한 행씩 대조합니다. 최신 결과 `results/20261022/native_binding_reconciliation.json`은 native 사고 export 7/7과 카탈로그의 `supported`·종료/질량 장부·PRISM resolved-release 변환 선언이 모두 일치하는 `RECONCILED_NATIVE_INTERFACES`입니다. 이 검사는 오래된 `missing` 카탈로그가 실제 소스와 조용히 어긋나는 문제를 막지만 packet을 만들거나 qualified 상태·빈도·시설 IR/F-N을 열지 않습니다.

**native 일반 LH2 전체범위 packet·campaign (2026-10-23):** `scripts/build_native_generic_scope_packet_catalog.py`가 일반 옥외 LH2 예제의 문헌 빈도 24개 사건을 탱크·배관·밸브·펌프·벤트·기화기·재액화기별 native 사고 exporter에 전달하고 event/component/port identity를 확인합니다. 최신 카탈로그는 **24/24 exact packet**(우발 21, 비상 릴리프 1, 양단 파열 2)이며, 5건은 개구면적을 바꾸지 않는 수치 안정화 재시도를 사용했습니다. `scripts/build_lh2_mixed_provider_campaign.py`와 `scripts/run_lh2_mixed_provider_campaign.py`의 최신 실행은 24개 요청 branch를 방출→SLABx-LH2/SLABx→점화·피해 chain으로 전달했고, `EXECUTED` 5건, `EXECUTED_OPERATOR_LIMITED` 19건, `FAILED` 0건입니다. 저장탱크 `AREA_1%`에서 발생했던 초기 질량 장부 실패는 후속 wet-area가 있는 실행에 대한 불필요한 미세시계 재정제를 생략하도록 고쳐 해결했으며, 질량 보정이나 허용오차 확대는 하지 않았습니다. 6개 case에는 액체·2상·재고 경계의 domain-incomplete 표지가 남아 있습니다. 600초 재고 이력은 내부 6,000구간을 96구간으로 줄이되 압력·엔탈피 평균에서 온도·밀도를 EOS로 다시 계산해 상태 일관성을 유지합니다. 이 전체 실행은 합성 진단이며 실제 provider·빈도·물리검증·시설 IR/F-N으로 승격하지 않습니다. 상세 명령과 제한사항은 [native 일반 LH2 전체범위 패킷·캠페인 기록](docs/PRISM_native_일반LH2_전체범위_패킷캠페인_20261023.md)에 있습니다.

**packet 자격 준비도 감사 (2026-10-24):** exact/strict packet이 있어도 qualification sidecar·독립 물리검증·실제 설비 경계가 없으면 자동 승격하지 않도록 `provider_worklist_evidence.py`가 사건별 `qualification_readiness`와 차단 사유를 기록합니다. 최신 24개 native generic 사건은 모두 `BLOCKED_REVIEW`이며 qualification sidecar 0건, 독립 물리검증 0건입니다. 이 결과는 빈도·센서 학습·시설 IR/F-N을 추가하지 않고, 다음 실제 provider 입력에서 교체해야 할 증거를 명확히 합니다. 감사기는 `provider_qualification.json`/`qualification.json` 및 물리검증 sidecar를 자동 발견하고 event/component/port와 source/result digest가 exact-match할 때만 존재로 집계하며, 불일치는 별도 차단 사유로 남깁니다. [packet 자격 준비도 감사 기록](docs/PRISM_패킷자격_준비도감사_20261024.md)

**native 저장탱크 strict smoke:** `scripts/run_lh2dt_native_layered_tank_smoke.py`가 외부 `LayeredTank.export_accident_history(request)`를 직접 호출해 PRISM strict `ResolvedLiquidRelease`로 변환하고, 같은 packet을 SLABx-LH2→확산→점화→피해 chain에 넣습니다. 2026-10-18 합성 실행은 0.05 s 이력, 질량 잔차 0 kg, 엔탈피 잔차 0 J, native export 약 1.64 s, 전체 chain 약 25.97 s를 기록했습니다. `END_TO_END_DIAGNOSTIC_EXECUTED`는 실제 native 응답 소비를 확인하는 결과이며, 합성 형상·초기상태·개구·기상과 airborne-liquid 미구현 때문에 qualified provider·빈도·시설 IR/F-N으로 승격하지 않습니다. 자세한 기록은 `results/20261018/native_layered_tank_smoke_chain/verification.json`과 [native 사고계약 감사 기록](docs/PRISM_외부LH2모델_native_사고계약_감사_20261018.md)에 있습니다.

**native 차단시간 handoff (2026-10-25):** `scripts/export_lh2dt_native_layered_tank_prism_packet.py`는 PRISM-side 탱크 재현기가 아니라 외부 `LayeredTank.export_accident_history(request)`를 직접 호출합니다. `--isolation-time-s`와 `--post-isolation-observation-s`를 주면 외부 탱크가 차단 시점 이후 유량 0을 확인하고 `reviewed_isolation_success` 종료 근거를 반환하며, PRISM은 그 시간 이력·재고·질량 잔차를 `ResolvedLiquidRelease`에 보존합니다. 최신 합성 실행 `results/20261025/native_layered_tank_isolation/verification.json`은 0.05 s 차단·0.01 s 관찰, 0.060000 s 전체 이력, 질량 잔차 약 `5.7×10⁻¹⁴ kg`, 상태 snapshot digest 일치를 기록했습니다. 이는 설비상태→native 방출→차단 종료→PRISM 피해 입력의 직접 연결을 검증하는 진단 증거이며, synthetic geometry·초기상태·개구이므로 provider 자격·현장 빈도·시설 IR/F-N을 열지 않습니다.
같은 packet을 `scripts/validate_lh2dt_prism_packet_chain.py`로 재생한 결과는 `results/20261025/native_layered_tank_isolation/chain/verification.json`의 `END_TO_END_DIAGNOSTIC_EXECUTED`입니다. 이 재생은 initiating frequency를 넣지 않으며, 시설 IR/F-N으로 합산하지 않습니다.

**native DynamicHEMPipe 차단·2상 handoff (2026-10-25):** `scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py`도 외부 `DynamicHEMPipe.export_accident_history(request)`를 직접 호출해 2상 flash, ground-liquid 분할, 재고 원장과 `reviewed_isolation_success`를 PRISM strict release로 넘깁니다. `results/20261025/native_dynamic_pipe_isolation/chain/verification.json`에서 동일한 packet의 SLABx-LH2/풀/점화/피해 연결을 `END_TO_END_DIAGNOSTIC_EXECUTED`로 확인했습니다. 배관 형상·초기 상태·방향은 합성 진단이며 airborne liquid은 native 계약에 따라 0으로 제한됩니다.

**native StrokeLimitedCommandedValve gas handoff (2026-10-26):** `scripts/export_lh2dt_native_valve_prism_packet.py`는 외부 `StrokeLimitedCommandedValve.export_accident_history(request)`를 직접 호출해 유한 stroke 개방과 gas 방출 이력을 PRISM strict gas release로 변환합니다. 외부 `ValveResult`가 계산한 throat 압력·질량플럭스와 provider 물성 entropy/상태를 packet에 보존해, native 7개 설비 중 기체 source/throat 상태 완결 항목을 2개에서 3개로 늘렸습니다. 밸브가 상류 재고·차단 신뢰도를 소유하지 않으므로 기본 종료는 `synthetic_diagnostic_horizon`이며, `available_mass_kg`는 호출자가 명시합니다. 500 kPa 기본 조건은 대기 출구 속도가 높아 현재 저마하 직접면 경계에서 자동 거절되고, near-ambient 101.5 kPa 구조진단은 `results/20261025/native_stroke_valve_low_mach/chain/verification.json`에서 `END_TO_END_DIAGNOSTIC_EXECUTED`를 확인했습니다. source/throat 상태 완결은 provider 근접장 팽창·혼합이나 독립 검증을 의미하지 않으며, high-speed 조건에는 provider-resolved downstream plane handoff가 별도로 필요합니다. 모두 synthetic diagnostic이며 빈도·물리검증·시설 IR/F-N은 열지 않습니다. 자세한 제한은 [native StrokeLimitedCommandedValve 방출 연결 기록](docs/PRISM_native_StrokeLimitedCommandedValve_방출연결_20261025.md)을 참고합니다.

고압 밸브 packet에도 선택형 압축성 handoff를 연결해 2개 native interval, 최대 Mach 약 `2.2855`, 에너지 잔차 `0 J/kg`, handoff 소비 및 최종 피해 chain을 확인했습니다. 이는 보존식 기반 notional-plane 진단이며 qualified provider·독립 근접장 검증·빈도·시설 IR/F-N을 열지 않습니다. 재현 명령과 결과는 [native StrokeLimitedCommandedValve 압축성 handoff 기록](docs/PRISM_native_StrokeLimitedCommandedValve_압축성handoff_20261026.md)과 `results/20261026/native_stroke_valve_high_pressure/`에 있습니다.

**native MappedPump liquid handoff (2026-10-25):** `scripts/export_lh2dt_native_mapped_pump_prism_packet.py`는 외부 `MappedPump.export_accident_history(request)`를 직접 호출해 H-Q-N 운전점, 액체 대기 개구, 상류 reserve, 지상 액체 분할을 PRISM strict liquid release로 넘깁니다. 합성 기본 실행은 `map_limited=false`, 0.2 s 진단시계, strict packet 질량 잔차 약 `6.8×10⁻²¹ kg`이며 `results/20261025/native_mapped_pump/chain/verification.json`에서 액체 풀→확산→점화·피해까지 `END_TO_END_DIAGNOSTIC_EXECUTED`를 기록했습니다. 펌프는 재고·seal 고장·차단 신뢰도를 소유하지 않으며 airborne liquid은 native 계약대로 0입니다. 이 결과는 pump 상태→native 방출→strict liquid packet→피해 chain 연결을 확인하는 synthetic diagnostic이고, 빈도·물리검증·시설 IR/F-N은 열지 않습니다. 자세한 사용법은 [native MappedPump 방출 연결 기록](docs/PRISM_native_MappedPump_방출연결_20261025.md)을 참고합니다.

**native 기화기·재액화기·벤트 직접 연결 (2026-10-25):** `scripts/export_lh2dt_native_dynamic_thermal_prism_packet.py`와 `scripts/export_lh2dt_native_vent_stack_prism_packet.py`가 각각 외부 `DynamicVaporizer`, `DynamicReliquefier`, `VentStack`의 사고 전용 export를 직접 호출합니다. 세 설비 모두 strict packet과 `END_TO_END_DIAGNOSTIC_EXECUTED` chain을 만들었고, 7개 native 설비 전체 결과는 `scripts/build_native_direct_adapter_coverage.py`와 [`native_direct_adapter_coverage_v1.json`](examples/native_direct_adapter_coverage_v1.json)으로 재검증합니다. 이 장부는 코드 경계 7/7과 진단 chain 7/7을 뜻하며, qualified packet·현장 빈도·독립 물리검증·시설 IR/F-N은 모두 0 또는 false로 유지합니다.

**native source/throat 상태 완결성 감사 (2026-10-26):** 7개 native 설비의 8개 명시적 상태 분기(`provider_response.json`)를 [`native_source_state_completeness_v1.json`](examples/native_source_state_completeness_v1.json)으로 필드 단위 대조합니다. 기체 분기 5개 중 StrokeLimitedCommandedValve·DynamicHEMPipe gas branch·DynamicVaporizer·DynamicReliquefier는 provider가 entropy와 throat 압력·온도·밀도·엔탈피를 제공해 **4/5 완결**했고, VentStack은 throat 해가 없는 Darcy 모델이라 **1/5 차단**입니다. DynamicHEMPipe의 액체·2상 분기는 같은 native class의 별도 상태 가족으로 계속 보존하며 기체로 재분류하지 않습니다. LayeredTank·DynamicHEMPipe liquid/two-phase·MappedPump는 별도 2상 근접장 계약 대상으로 분리합니다. 감사 명령은 `python scripts/audit_native_source_state_completeness.py --output examples/native_source_state_completeness_v1.json`이며, 누락 필드를 추정하거나 시설 IR/F-N·빈도를 열지 않습니다. 자세한 기준은 [native source/throat 상태 완결성 감사](docs/PRISM_native_source_state_완결성_감사_20261025.md)입니다.

**native DynamicHEMPipe 기체 handoff (2026-10-26):** 외부 `DynamicHEMPipe`의 명시적 gas branch가 upstream entropy와 hydraulic throat 상태를 export하도록 보완됐습니다. `results/20261026/native_dynamic_pipe_gas_isolation/`에서 `prism.compressible_plane_handoff.v1`을 exact provider digest에 붙여 **격리 성공 뒤 0 유량 종료 구간 1개를 보존**하고, 최대 Mach `3.8073`, 에너지 잔차 `0 J/kg`, handoff 소비 `true`, 최종 gas consequence chain `END_TO_END_DIAGNOSTIC_EXECUTED`를 확인했습니다. 엔트로피 잔차는 `127.47 J/kgK`로 남아 등엔트로피 물리검증을 주장하지 않으며, 합성 형상·빈도 없음·qualified provider·시설 IR/F-N 보류입니다. 기체 handoff와 액체·2상 격리 chain은 서로 다른 상태 가족으로 기록하며, 자세한 명령과 제한은 [DynamicHEMPipe 기체 source/throat handoff 기록](docs/PRISM_native_DynamicHEMPipe_gas_source_state_handoff_20261026.md)을 따릅니다.

**native DynamicHEMPipe 기체의 시설 빈도·IR/F-N 결합 (2026-10-26):** `scripts/run_native_dynamic_pipe_gas_facility_frequency_case.py`가 위 gas packet을 문헌 `LH2_PIPE AREA_0.01%` 사건과 `0.001 m` exact opening으로 매칭해 두 기상 조건의 시설 캠페인으로 실행합니다. 5개 opening event·10개 case 중 정확히 일치한 1개 event의 2개 case가 `EXECUTED_OPERATOR_LIMITED`로 피해 chain을 통과했고, 8개 risk atom과 문헌 central/p05/p95 조건부 IR/F-N 재가중이 시설 평가에 기록됐습니다. 나머지 opening bin은 `UNCOMPUTED`로 남겼으며, provider event ID와 frequency event ID의 매핑도 별도 장부에 보존했습니다. strict gas packet을 소비한 경우 사고 family는 `pipe_hole`로만 기록해 liquid/two-phase family를 자동 부여하지 않습니다. 결과는 `facility_total_risk_available=false`, `complete_facility_qra_claim=false`, `physical_validation_claim=false`로 유지합니다. 재현 명령과 제한은 [DynamicHEMPipe 기체 시설 빈도 결합 기록](docs/PRISM_native_DynamicHEMPipe_gas_facility_frequency_20261026.md)과 `results/20261026/native_dynamic_pipe_gas_facility_frequency/verification.json`에 있습니다.

**native 일반 LH2 전체 설비 빈도·IR/F-N 연결 (2026-10-26):** `scripts/run_native_full_scope_frequency_assessment.py`는 저장탱크·이송배관·밸브·벤트·펌프·기화기·재액화기의 24개 문헌 사건을 각각 native provider 방출 packet과 결합해 24개 case·96개 risk atom을 시설 원장에 넣습니다. 중앙·p05·p95 문헌 빈도 시나리오와 설비·사고군별 scope matrix, 방출 종료·재고 장부, 실제 case 처리시간을 함께 저장합니다. `provider_worklist.json`은 문헌 사건과 필요한 provider 방출 요청을 24/24 `ALIGNED`로 대조하며, 실제 qualified packet은 0개입니다. 이번 합성 near-receptor 진단에서는 24개 case가 수치상 실행됐지만 19개가 `EXECUTED_OPERATOR_LIMITED`라서 조건부 IR/F-N만 공개하고 시설 전체 QRA는 보류합니다. 수직 handoff all-bin과 기존 재고 소진 diagnostic branch를 별도 namespace로 명시적으로 병합한 union 결과는 34개 event·44개 case·176개 risk atom이며, `vertical_handoff`와 `inventory_depletion`은 strict `PARTIAL`/조건부 `EXECUTED`로 기록됩니다. union에서는 두 branch의 기상·인구 조건도 namespace와 receptor map으로 분리해 population mismatch 0건을 확인했습니다. union 후속 단계에서는 제한된 검증근거 6개 영역과 fresh physics/cache benchmark를 별도 장부로 묶었습니다. cache는 동일 요청 10/10 hit·p95 약 23.3 ms였고 fresh physics는 약 2.73초라서 1 Hz cache 진단만 기록합니다. 상세 명령과 결과는 [전체 설비 빈도·IR/F-N 연결 기록](docs/PRISM_native_일반LH2_전체설비_빈도IRFN_연결_20261026.md), [vertical handoff·inventory depletion union 기록](docs/PRISM_native_일반LH2_vertical_handoff_union_20261026.md), `results/20261026/native_full_scope_union_assessment/`에서 확인합니다. 최신 기본 캠페인 감사는 16개 검사 중 12개 통과·4개 차단, union 감사는 **21개 검사 중 17개 통과·4개 차단**인 `INCOMPLETE_EVIDENCE`이며, 상태 snapshot handoff는 별도 감사에서 2개 진단만 `BOUND_AND_ECHOED`, 24개 union campaign 사건은 `UNBOUND`로 남습니다. union도 synthetic/operator-limited 범위 때문에 시설 전체 QRA를 열지 않습니다.

**native 고압 DynamicVaporizer 압축성 handoff (2026-10-25):** source-state가 완성된 1 MPa 합성 기화기 packet을 별도 `prism.compressible_plane_handoff.v1`로 묶어 최대 Mach 약 `4.5694`를 검증하고, 같은 packet을 SLABx-LH2/SLABx·점화·피해 chain까지 재생했습니다. handoff 소비와 질량·에너지 장부는 닫혔지만, 이 plane은 notional diagnostic이며 qualified provider·독립 근접장 검증·빈도·시설 IR/F-N을 열지 않습니다. 결과는 [`native DynamicVaporizer 압축성 handoff 기록`](docs/PRISM_native_DynamicVaporizer_압축성handoff_20261025.md)과 `results/20261025/native_dynamic_vaporizer_high_pressure_completed/`에 있습니다.

현재 외부 소스 digest 기준 재실행도 `results/20261022/native_layered_tank_smoke_current_chain/verification.json`에 보존했습니다. native export 약 1.83 s, 전체 방출→SLABx-LH2/풀→점화→피해 chain 약 19.53 s, 질량 잔차 0 kg, 엔탈피 잔차 0 J, `END_TO_END_DIAGNOSTIC_EXECUTED`입니다. 이는 연결 회귀 증거이며 현장 packet·빈도·시설 전체 IR/F-N의 승격은 아닙니다.

같은 최신 소스의 `DynamicHEMPipe` full-bore도 `results/20261022/native_dynamic_pipe_full_bore_current/verification.json`에서 재실행했습니다. 0.01 m 개구의 2상 방출이 provider 자연 종료(`model_pressure_equalization`)까지 0.0314 s 진행되었고, 최종 압력은 101,325 Pa, 질량 잔차 0 kg, native export 약 0.69 s, 전체 chain 약 34.63 s로 `END_TO_END_DIAGNOSTIC_EXECUTED`를 반환했습니다. 합성 1 m 배관·대기경계·선언형 pool footprint·airborne liquid 0을 사용하므로 현장 packet·빈도·시설 전체 IR/F-N은 여전히 보류합니다.

**보완 pool 재실행:** 최신 `results/20261018/generic_mixed_provider_campaign_refined_pool_current.json`은 24개 case 모두 실행되어 `EXECUTED` 5건, `EXECUTED_OPERATOR_LIMITED` 19건, `FAILED` 0건, `UNCOMPUTED` case row 0건을 기록했습니다. campaign case에는 provider packet identity metadata가 24/24 기록되지만, 최신 저장 packet evidence와의 digest equality는 18/24만 확인되어 `packet_identity_consumed=false`로 유지합니다. release ledger 완전 행은 5건입니다. 19건의 제한 상태와 1건의 domain-incomplete 표시는 보존하며, 이 결과를 qualified provider나 시설 전체 IR/F-N으로 승격하지 않습니다. 최신 구조 연결 장부는 [방출 binding 갱신 기록](docs/PRISM_최신캠페인_방출binding_갱신_개발기록_20261018.md)입니다.

**시설 전체 packet coverage fail-closed 보완 (2026-10-24):** 최신 native packet catalog `results/20261023/native_generic_scope_packets_v10/verification.json`은 24/24 exact packet을 만들었고, 이를 다시 스캔한 evidence와 merged facility ledger를 비교했습니다. 24개 matched event의 source/result digest는 24/24 일치하지만, merged ledger의 수직 handoff 5개 event에는 packet evidence가 없습니다. 이제 `packet_subset_identity_consumed=true`와 `packet_identity_consumed=false`를 분리하고, `unbound_campaign_event_ids` 및 coverage ratio를 기록합니다. 따라서 24/29 연결은 확인되지만 시설 전체 packet 소비나 QRA 승격으로 해석되지 않습니다. [fail-closed 개발기록](docs/PRISM_시설전체_packet_coverage_fail_closed_개발기록_20261009.md)

**시설 case별 provider 요청 자동화 (2026-10-24):** `build_facility_evidence_request.py`는 이제 family/component 요약과 함께 `case_requests`를 생성합니다. 각 요청에는 사건·기상조건·방출 branch·component·port·source/result digest·현재 제한 사유가 들어갑니다. 최신 generic+vertical 원장에서는 34개 case 요청이 보존되고, 수직 handoff는 5개 event가 D-3/D-4 두 조건으로 확장된 10개 case로 표시됩니다. 현재 수직 packet은 synthetic 0.37 s handoff이므로 `qualification_required=true`이며, 이를 실제 provider packet으로 바꾸기 전에는 시설 IR/F-N을 열지 않습니다. [요청서 개발기록](docs/PRISM_시설별_공급자_packet_요청서_20261009.md) / [최신 요청 JSON](results/20261024/native_generic_scope_vertical_facility_evidence_request_v2.json)

중복 ledger 행이 같은 사건·기상·방출 branch를 나타낼 때는 실행 행과 미계산 행을 합치면서 한쪽에만 있던 provider identity와 scenario family를 보존합니다. 두 행의 identity가 충돌하면 요청을 열어 두고 충돌을 blocking reason으로 기록하므로, 목록 순서만으로 공급자 packet이 선택되지 않습니다.

**시설 case packet coverage 검증 (2026-10-24):** `audit_facility_case_packet_coverage.py`는 요청서의 34개 case와 `prism.provider_packet_evidence.v1`를 event/component/port/source digest/result digest까지 대조합니다. 같은 event의 여러 기상 case는 하나의 provider packet을 재사용할 수 있지만, case 수와 고유 event 수를 별도로 집계합니다. 현재 결과는 qualified evidence 0/34의 `NO_CASE_MATCH`이며, [coverage 개발기록](docs/PRISM_시설case_provider_packet_coverage_개발기록_20261009.md)과 [coverage JSON](results/20261024/native_generic_scope_vertical_case_packet_coverage_v1.json)에 남겼습니다.

같은 검토에서 외부 PreSLHy/DEGADI handoff replay 5건을 찾았지만, PRISM 사건·포트·방출 digest와 재고/종료 장부가 없어 `SCREENING_ONLY_UNBOUND`로만 인벤토리했습니다. [외부 handoff evidence inventory](results/20261024/native_generic_scope_vertical_external_handoff_evidence_inventory_v1.json)

**문헌 빈도 근거 추적 (2026-10-18):** `scripts/build_frequency_provenance_report.py`는 빈도 계획을 17개 검토 프로파일 카탈로그와 대조하고, 실제 선택된 7개 프로파일·24개 사건의 `source`, 원자료 SHA-256, 카탈로그 digest, 중앙값, p05/p95와 제한사항을 하나의 보고서로 기록합니다. 현재 일반 LH2 예제 보고서 `results/20261018/generic_lh2_frequency_provenance_current.json`은 `PASS_WITH_SCOPE_LIMITATIONS`이며, 현장 사고빈도 수집·센서 기반 빈도 학습·물리검증 주장은 모두 `false`로 고정합니다. 해시 불일치나 이벤트 누락은 `FAILED_PROVENANCE_INTEGRITY`로 중지합니다. 자세한 기준은 [문헌 빈도 근거 추적 개발 기록](docs/PRISM_문헌빈도_근거추적_개발기록_20261018.md)을 참고합니다.

**실시간 공정상태→사고 방출 경계:** `validate_equipment_process_state()`는 압력·온도·액면·유량 같은 정상 공정 상태만 외부 설비 resolver에 전달합니다. 누출 개구·방출 단계·지속시간·재고 소진·사건 빈도·`Resolved*Release` packet이 상태 snapshot에 섞이면 즉시 거절합니다. 설비 provider가 별도의 사고 방출 이력과 종료 근거를 반환한 경우에만 `request_from_equipment_resolver()`가 SLABx-LH2/SLABx 피해 계산으로 넘깁니다. 원본 상태는 깊은 복사로 보존하고, 빈도는 문헌 `FrequencyPlan`에서 별도로 결합합니다. 상세 계약은 [실시간 공정상태와 사고 방출 경계 계약](docs/PRISM_실시간_공정상태_방출경계_계약_20261009.md)을 참고합니다.

작업목록만 있는 기간에도 `scripts/build_equipment_campaign.py --provider-worklist-only`로 24개 사건과 24개 미계산 branch를 `RiskCampaign`에 넣을 수 있습니다. 이 모드는 물리 요청이나 위험 0을 만들지 않고, 시설 실행 회계에서 누락 사건을 보이게 합니다.

일반 LH2 전체 범위 예제는 이 작업목록 캠페인을 실제 실행 회계로도 보존합니다. `results/20261009/generic_full_scope_worklist/campaign_result.json`에는 24개 사건과 24개 `UNCOMPUTED` case가 있고, `accident_scope_matrix.json`에는 12개 사고 가족별 생성 여부를 기록합니다. 이는 provider packet이 없다는 사실을 명확히 보여주는 범위 감사이며 시설 IR/F-N 결과가 아닙니다.

**비상 릴리프 방출 경로:** `TNO_RELIEF_DEVICE`의 `maximum_relief_discharge`는 일반 벤트나 임의 누출로 대체하지 않고, `event_kind=emergency_relief`인 provider 기체 방출 이력과 `equipment_emergency_relief`·`emergency_relief_discharge` 근거가 모두 있을 때만 빈도와 결합합니다. 실제 provider 패킷이 없으면 해당 벤트 사고는 `NO_CASE_EXECUTED`/`UNCOMPUTED`로 남습니다.

실제 릴리프 packet catalog를 request template로 바꿀 때는 `build_provider_request_catalog.py`에 `--release-kind emergency_relief`를 지정합니다. 기본값 `accidental_leak`와 catalog를 섞지 않으며, 출력에 `provider_release_kind`를 남깁니다.

`inventory_over_600s`는 600초 전체 provider 이력과 전용 종료 근거가 모두 있을 때만 사건 빈도와 피해를 결합합니다. 짧은 진단 이력은 이 사고의 대체 계산으로 인정하지 않습니다.

주요 사고의 범위는 `scripts/build_accident_scope_matrix.py`로 별도 감사할 수 있습니다. 이 보고서는 저장탱크·배관·밸브·벤트·펌프·증발기·재액화기·액체/2상·재고소진·양단 파열·수직 handoff를 행으로 만들고, 각 행을 `EXECUTED`, `PARTIAL`, `UNCOMPUTED`, `NO_EVENT_GENERATED`로 표시합니다. 행별 문헌 빈도는 사고 가족 간에 중복될 수 있으므로 합산하지 않으며, 시설 전체 IR/F-N 승격 여부와 차단 이유도 함께 기록합니다. 자세한 기준은 [주요 사고 범위 매트릭스 기록](docs/PRISM_주요사고_범위매트릭스_20261009.md)을 참고합니다.

IJHE 제출 준비 상태는 `scripts/build_ijhe_completion_audit.py`로 자동 판정합니다. 최신 병합 감사 `results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v20.json`은 29개 PASS 검사·5개 BLOCKED 검사(상위 차단사유 4개)인 `INCOMPLETE_EVIDENCE`를 유지합니다. `--combined-chain-closure` 입력은 29개 사건의 방출→최종피해 연결을 확인하고, `--domain-recovery-audit` 입력은 6개 prior domain blocker의 회복과 22/24 outside-LFL proof를 event별로 기록합니다. 이 gate는 영역 밖 inventory를 숨기지 않으며 provider 자격·시설 IR/F-N을 승격하지 않습니다. 차단 사유는 합성 또는 screening provider packet만 사용됨, 주요 사고 범위의 partial/미계산 항목, 시설 IR/F-N 보류, 그리고 34개 facility case의 qualified provider packet coverage 0건이다. 이 진단 검사들은 `diagnostic_only=true`이며 qualified 사고 packet·빈도·시설 QRA·독립 전체 물리검증을 대신하지 않는다.
 IJHE용 파일을 갱신한 뒤에는 `scripts/audit_status_consistency.py`로 완료 감사·시설평가·증거요청·병합 원장·상태 장부가 같은 실행을 가리키는지 확인합니다. 현재 결과는 `results/20261024/ijhe_status_consistency_v11.json`의 `CONSISTENT`이며 20개 검사가 모두 통과한다. 완료 감사의 combined-chain, SLABx 및 realtime-cache 진단 검사를 직접 확인하며, 빈도 추정이나 시설 IR/F-N 승격을 수행하지 않습니다. 자세한 범위는 [SLABx-LH2 검증근거 통합 기록](docs/PRISM_SLABx_LH2_검증근거_통합_20261024.md), 상태 규칙은 [상태 장부 일관성 감사 기록](docs/PRISM_상태장부_일관성_감사_20261010.md)에 있습니다.

## 목차

1. [쉽게 이해하는 PRISM](#쉽게-이해하는-prism)
2. [시스템 구조와 개발 상태](#시스템-구조와-개발-상태)
3. [설치와 첫 실행](#설치와-첫-실행)
4. [입력 파일 작성](#입력-파일-작성)
5. [외부 모델 연결](#외부-모델-연결)
6. [기본 분석 모드](#기본-분석-모드)
7. [LH2 피해영향 계산](#lh2-피해영향-계산)
8. [빈도 산출과 적용](#빈도-산출과-적용)
9. [설비와 디지털트윈 연결](#설비와-디지털트윈-연결)
10. [출력 해석](#출력-해석)
11. [검증과 후속 개발](#검증과-후속-개발)
12. [문제 해결과 개발 기록](#문제-해결과-개발-기록)

## 쉽게 이해하는 PRISM

탱크에서 수소가 새는 상황을 생각하면 세 가지 질문이 생깁니다.

- **얼마나 자주 생길까?** 사고 빈도 모듈이 설비 종류·수량·배관 길이와 문헌 자료를 이용합니다.
- **발생하면 어떻게 퍼질까?** 공정/방출 모델과 SLABx-LH2·SLABx가 방출량, 극저온 전이와 확산을 계산합니다.
- **불이 붙으면 사람에게 어떤 피해가 생길까?** 점화 분기, 화재 방사열, 폭발 피해 구역과 인명 피해 변환을 연결합니다.

빈도와 피해는 다른 값입니다. 압력이 올라가면 누출량과 피해가 달라질 수 있지만,
현재 PRISM은 압력 센서만 보고 사고 빈도가 몇 배 증가했다고 추정하지 않습니다.
이미 누출이 관측됐다면 누출 발생확률을 다시 곱하지 않고 **그 누출의 조건부 피해**를 계산합니다.

PRISM은 각 모델을 연결하고 입력·질량·시간·출처가 맞는지 검사합니다.
모든 설비의 물리 모델을 자체 구현한 단일 공정 시뮬레이터는 아닙니다.

## 시스템 구조와 개발 상태

| 기능 | 현재 구현 | 범위/한계 |
|---|---|---|
| 모드 선택 | 기본 `standard`, 선택형 `lh2` | 내부 모델 분리 관리, 실패 시 자동 모드 전환 없음 |
| 시설 구성 | 부품·포트·연결·수용점 JSON과 검증 | 구성 등록이 모든 부품의 물리 해석 지원을 뜻하지 않음 |
| 누출→피해 | 방출, 지면 도달/풀, 극저온 전이, 확산, 점화, 화재/폭발, 인명 피해 | 제한된 옥외 진단 경로 |
| 사고 빈도 | 17개 설비 프로파일, 55개 LOC/누출구간 행 | 문헌 기본선, 현장 사고빈도 검증 없음 |
| 빈도→피해 | 문헌 LH2 배관 5개 area-bin과 LayeredTank 문헌 `LH2_VESSEL` 정확 개구 1개를 설비 방출·기상·점화 경로에 결합 | 실제 설비 수·위치·장벽 근거가 없어 일반 시설 전체 QRA는 미완료; 개구가 다른 bin은 자동 보간하지 않고 미계산 |
| 설비 출구 연결 | PH/network 출구, 5개 transient LH2 pipe area-bin, 양수 재고 threshold 종료, 양단 파열, provider-resolved vertical handoff, provider-resolved liquid/two-phase exit 수용 | 기체는 수평 또는 명시적 수평 handoff가 있는 대기압·Mach≤0.3 경계, 액체/2상은 provider flash·지면 분할이 완결된 경계만 수용; 유량 재계산 없음; airborne liquid·실제 설비의 LayeredTank 액체 재고 feedback은 미지원이며, 합성 대기 probe와 양수 임계값 feedback 진단만 별도 SLABx 브리지로 연결 |
| 일반 설비 매니페스트 | 부품·포트·연결·시나리오 제어를 시설 중립 JSON으로 검사하고 `EXECUTABLE/PARTIAL/EXCLUDED/UNCOMPUTED`를 명시 | 누락된 P&ID 태그·좌표·물성·제어를 추정하지 않음; `EXECUTABLE` 전에는 시설 위험 캠페인 승격 불가 |
| 센서 연결 | 단위·위치·품질·시간 검증, 알려진 누출의 P/T 갱신 | 누출 크기 역추정·경보 빈도 학습 없음 |
| 결과 캐시 | 동일 입력·시설·모델 버전의 결과 재사용 | 변경 상태는 신규 계산, 신규 계산 1 Hz 미검증 |
| 기존 엔진 QRA | 빈도 조회, 사건 생성, 점화·차단·기상, IR/F-N | 외부 엔진 기능, 새 LH2 전체 시설 결합은 미완료 |

```text
PRISM -> standard / LH2
LH2 -> source / resolved equipment exit -> pool/cryogenic transition
-> SLABx dispersion -> ignition/fire/blast -> human harm -> conditional risk
Literature frequency -> exact physical opening match -> initiating event -> risk contribution
```

| 모델 | 책임 | 이 저장소에 포함 |
|---|---|---|
| PRISM / `lh2_tno` | 모드 선택, 입력 계약, 실행 연결, 빈도, 센서 정규화, 출처 기록 | 예 |
| 기존 TNO 기반 엔진 | 기존 QRA, 열/폭발 인명 피해 변환, 근거 gate | 외부 경로 연결 |
| `lh2dt` | 설비 압력·엔탈피·상·유량·재고/사건 시계 | 외부 경로 연결 |
| SLABx-LH2 / SLABx | 상세 방출, 근거리 전이와 분산 | 외부 경로 연결 |
| DynamicLH2PoolX | 지면에 도달한 LH2 풀과 증발 | 외부 경로 연결 |

**제품 이름은 PRISM**입니다. TNO 표기는 방법·원자료·외부 엔진의 출처를 설명할 때 유지합니다.
HyRAM을 현재 LH2 전체 경로에 도입했다고 주장하지 않습니다. 필요성이 검토되면 별도 모델로 추가할 수 있습니다.

## 설치와 첫 실행

### 설치

GitHub 접근 권한이 있는 계정으로 새 비공개 저장소를 복제합니다. **Python 3.12 이상**이 필요합니다.
아래는 Windows PowerShell 기준이며 명령은 저장소 루트에서 실행합니다.

```powershell
git clone https://github.com/lyullee/prism.git
cd prism
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e "./lh2-tno[test]" setuptools wheel
```

배포 이름은 `prism-risk`, 실행 명령은 `prism`입니다. PyPI 설치 명령은 `python -m pip install prism-risk==0.6.2`입니다.

개발 환경에서 테스트를 실행할 때는 `python -m pip install -e ".[test]"`를 사용합니다. 이 extra에는 수소 물성 계산과 native LH2 packet 테스트에 필요한 `CoolProp`도 포함됩니다.
공개 배포 파일에는 외부 물리 모델이 포함되지 않습니다. GitHub는 비공개이며 접근 권한이 필요합니다.

### 설비 매니페스트 사전 점검

외부 디지털트윈은 먼저 설비 중립 매니페스트로 내보냅니다. 이 명령은 누락된 태그나 제어 신호를 자동으로 채우지 않고, 위험 계산에 넘겨도 되는지 판정합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_manifest.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --output manifest_audit.json
```

구조 점검이 `EXECUTABLE`이 된 뒤에도 빈도 범위는 별도로 확인합니다. 아래 감사기는 모든 설비에 검토된 문헌 profile을 배정하거나 명시적 제외 사유를 요구합니다. 설비 이름·압력·크기만으로 빈도를 추정하지 않으며, 방출 provider나 피해 계산을 자동으로 만들지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_frequency_scope.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --output frequency_scope_audit.json
```

예제의 `EXECUTABLE`은 구조와 빈도 범위가 갖추어졌다는 뜻입니다. 실제 시설 위험을 계산하려면 각 사건에 설비 provider 방출 이력과 명시적 `ConsequenceRequest`를 연결해야 하며, 빠진 사건은 `UNCOMPUTED`로 남겨야 합니다. 자세한 정책은 [일반 설비 빈도 범위 연결 기록](docs/PRISM_일반설비_빈도범위_연결_개발기록_20261009.md)을 참고합니다.

빈도 사건과 방출 요청 템플릿을 캠페인으로 묶을 때는 다음 컴파일러를 사용합니다. 개구나 설비가 맞지 않는 사건은 자동 대체하지 않고 미계산 경로로 남깁니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --request-template lh2-tno/examples/equipment_consequence_template.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "synthetic generic manifest campaign" `
  --output equipment_campaign.json
```

이 명령은 선언만 컴파일하며 물리 backend는 실행하지 않습니다. 실행 기록과 합성 예제의 1건 실행·9건 미계산 결과는 [일반 설비 방출경로 캠페인 기록](docs/PRISM_일반설비_방출경로_캠페인컴파일_개발기록_20261009.md)에 남깁니다.

설비가 여러 개의 실제 방출 경계를 제공하면 `--request-template` 대신 `--request-catalog`을 사용할 수 있습니다. JSON 배열 또는 `{"templates": [...]}` 객체에 설비별 `ConsequenceRequest`를 넣습니다. PRISM은 각 빈도 사건에 대해 설비 ID와 실제 개구가 모두 일치하는 요청만 선택하고, 여러 요청이 동시에 맞거나 일치하는 요청이 없으면 각각 오류 또는 `UNCOMPUTED`로 남깁니다. 다른 설비의 방출량·개구·지속시간을 복사하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --request-catalog equipment_request_catalog.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed equipment provider catalog" `
  --output equipment_campaign.json
```

차단 성공·실패처럼 하나의 initiating event에 여러 provider 방출 history가 있으면 `--request-branch-catalog`을 사용합니다. 각 행은 `id`, `probability_given_event`, `provenance`, `request`를 포함합니다. 같은 사건에 맞는 branch 확률의 합이 1보다 작으면 남은 확률을 `uncomputed-provider-branch-remainder`로 보존하고, 1보다 크면 컴파일을 거부합니다. 따라서 차단 실패 packet을 누락한 채 성공 branch만으로 시설 위험을 계산하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --request-branch-catalog equipment_request_branch_catalog.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed provider isolation branches" `
  --output equipment_branch_campaign.json
```

외부 설비 모델이 `prism.resolved_release.v1` packet을 직접 내보내면 중간 request catalog 파일을 만들지 않고도 선택형 경로로 연결할 수 있습니다. 이 경로는 packet을 strict 검증한 뒤 defaults의 종료근거·source operator를 붙이고, 같은 exact-match 규칙으로 설비와 문헌 빈도를 연결합니다. packet 하나라도 문맥과 맞지 않으면 캠페인을 만들지 않으며, 실제 packet이 없는 설비에는 아무 값도 추정하지 않습니다.

실제 provider가 저장한 방출 packet과 적격성 기록을 파일로 전달할 때는 `scripts/build_provider_packet_evidence.py`를 사용합니다. `--release`에는 `prism.resolved_release.v1` 또는 `prism.resolved_release_set.v1`, `--qualification`에는 별도 `prism.provider_qualification_evidence.v1` JSON을 넣습니다. 두 파일의 event/component/port 및 source/result SHA-256이 정확히 맞아야 `prism.provider_packet_evidence.v1`가 생성되며, `input_origin=synthetic`은 거부됩니다. 이 단계는 빈도를 추정하지 않고 기존 문헌 `FrequencyPlan`을 그대로 둡니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_provider_packet_evidence.py `
  --release actual_resolved_release.json `
  --qualification provider_qualification.json `
  --output provider_packet_evidence.json
```

생성된 evidence catalog를 campaign에 연결하려면 컴파일러에 `--provider-evidence-catalog provider_packet_evidence.json`을 추가합니다. 독립 물리검증 기록은 `--physical-validation-evidence validation.json`으로 별도 연결하며, `independent_validated`에는 evidence ID와 SHA-256이 모두 필요합니다. `scripts/audit_provider_catalog_coverage.py --provider-evidence-catalog provider_packet_evidence.json`을 사용하면 worklist의 구조 exact-match와 qualification exact-match를 별도로 확인할 수 있고, 합성 packet은 일치하는 sidecar가 있어도 qualified로 세지 않습니다. 필요하면 같은 coverage JSON을 `scripts/build_ijhe_completion_audit.py --provider-qualification-coverage coverage.json`에 넣어 완료 감사가 자격 검증된 packet 수와 전체 worklist 충족 여부를 읽도록 합니다. evidence에 없는 사건은 자동으로 다른 packet으로 대체하지 않고 `UNCOMPUTED`/미자격으로 남습니다. 현재 external evidence inventory에는 이 sidecar를 갖춘 실제 packet과 독립 검증 기록이 없어 qualified packet 수는 0건이며 시설 IR/F-N 승격은 계속 보류됩니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --provider-release-catalog provider_releases.json `
  --release-kind accidental_leak `
  --request-defaults request_defaults.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed provider release campaign" `
  --output equipment_campaign.json
```

같은 initiating event의 provider packet이 차단 성공·실패처럼 여러 개라면 `--provider-release-branch-catalog`을 사용합니다. 각 행은 `id`, `probability_given_event`, `provenance`, `release`를 가지며, 일반 누출 branch는 `prism.resolved_release.v1`, 양단 파열 branch는 `prism.resolved_release_set.v1` packet을 넣습니다. 양단 파열 branch는 `--release-kind two_sided_rupture`를 함께 지정해야 두 endpoint를 공유 사건으로 보존하는 전용 adapter가 선택됩니다. packet은 각각 실제 개구와 상태 이력을 보존하고, PRISM은 initiating frequency를 한 번만 부여합니다. branch 확률 합이 부족하면 `UNCOMPUTED` remainder를 남기고, 초과하면 거부합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --provider-release-branch-catalog provider_release_branches.json `
  --request-defaults request_defaults.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed provider barrier branches" `
  --output equipment_provider_branch_campaign.json
```

설비별 campaign을 따로 실행한 뒤 시설 장부로 합칠 때는 `merge_facility_campaigns.py`를 사용합니다. 이 단계는 물리 계산을 다시 하지 않고 각 campaign의 검증된 risk atom만 한 번씩 합칩니다. 전체 시설 component 목록을 `--expected-component-id`로 명시해야 하며, event ID·asset 소유권·수용점 집합이 겹치거나 기대한 설비·사고 가족이 빠지면 known contribution만 남기고 `total_facility_*`를 `null`로 유지합니다. 출력의 `component_contributions`에서는 event의 `model_component_id`별 IR/F-N 기여도를 확인할 수 있으며, 미계산 설비에 빈도 0을 배정하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/merge_facility_campaigns.py `
  --campaign-result tank_campaign_result.json `
  --campaign-result transfer_campaign_result.json `
  --expected-component-id storage-tank-01 `
  --expected-component-id liquid-transfer-line-01 `
  --output facility_risk_ledger.json
```

결합된 ledger에 문헌 빈도 구간을 재가중할 때는 `compute_frequency_uncertainty.py`에 명시적인 자산별 또는 사건별 시나리오 JSON을 전달합니다. 이 명령은 물리를 다시 실행하지 않고, 공개된 p05/published/p95 빈도만 risk atom에 적용합니다. `facility_credible_interval=false`는 통계적 신뢰구간을 주장하지 않는다는 뜻이며, 불완전한 scope는 그대로 보류됩니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/compute_frequency_uncertainty.py `
  --ledger facility_risk_ledger.json `
  --scenarios frequency_scenarios.json `
  --output facility_frequency_uncertainty.json
```

시설 ledger와 빈도 시나리오를 한 파일로 묶으려면 `build_facility_assessment.py`를 사용합니다. 이 실행기는 이미 계산된 campaign 결과를 한 번만 합치고, 선택한 문헌 빈도 시나리오를 저장된 risk atom에만 적용합니다. `--provider-qualification-coverage coverage.json`을 함께 주면 coverage 보고서의 전체 worklist 자격 상태와 merged ledger의 실제 qualified packet 수를 대조해 `provider_qualification_coverage.complete`에 기록합니다. 이 정보는 packet·물리검증·시설 QRA를 자동으로 만들어 주지 않으며, 개수나 digest가 맞지 않으면 명시적 차단 사유로 남습니다. `fresh_physics_executed=false`이며, 미완성 범위에서는 시설 total을 승격하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_facility_assessment.py `
  --campaign-result tank_campaign_result.json `
  --campaign-result transfer_campaign_result.json `
  --expected-component-id storage-tank-01 `
  --expected-component-id liquid-transfer-line-01 `
  --scope-matrix tank_scope_matrix.json `
  --scope-matrix transfer_scope_matrix.json `
  --required-accident-family pipe_hole `
  --scenarios frequency_scenarios.json `
  --provider-qualification-coverage provider_catalog_coverage.json `
  --output facility_assessment.json
```

비상 릴리프 packet은 `--release-kind emergency_relief`로 분리합니다. 이 옵션은 일반 누출이나 정상 벤트를 사고로 바꾸지 않으며, `equipment_emergency_relief`와 `emergency_relief_discharge` 근거가 없으면 연결되지 않습니다.

합성 저장탱크·이송배관 catalog를 현재 backend로 실행한 진단은 2개 요청 연결, 2개 물리 실행(1개 `EXECUTED`, 1개 `EXECUTED_OPERATOR_LIMITED`), 8개 미계산으로 기록되며 전체 시설 IR/F-N은 보류됩니다. 상세 수치와 해석 한계는 [일반 설비 방출경로 캠페인 기록](docs/PRISM_일반설비_방출경로_캠페인컴파일_개발기록_20261009.md)을 봅니다.

현재 액화수소검사지원센터 모델의 진단은 외부 자료를 변경하지 않고 다음처럼 실행할 수 있습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_manifest.py `
  --center-root "<디지털트윈 모델 루트>" `
  --manifest-output center_manifest.json `
  --output center_manifest_audit.json
```

`PARTIAL` 결과는 연결 검토용이며 시설 연간 위험의 숫자로 해석하지 않습니다. 모든 부품의 위치·물성 기준·포트·연결·필수 운전 제어가 실제 자료로 채워져 `EXECUTABLE`이 된 뒤에만 `Facility`와 피해 계산으로 승격합니다.

외부 물리모델 자체의 검증 결과와 실제 설비 연결 준비 상태는 별도로 감사해야 합니다. 다음 명령은 provider의 JSON 증거와 `검증결과.md`를 읽기만 하며, provider solver를 가져오거나 screening 값을 PRISM에 복사하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/audit_external_provider.py `
  --provider-root "<외부 LH2 디지털트윈 모델 루트>" `
  --output provider_evidence_audit.json
```

현재 검사센터 provider에는 자체 회귀검증 822건 통과 기록이 있지만, 센터 자산 바인딩과 전방 비교 허용이 모두 `false`이고 파라미터 89건·운전시퀀스 52행의 물리시간이 미확정이어서 결과는 `PARTIAL_PROVIDER_EVIDENCE`입니다. 이 숫자는 solver 검증 범위이며 센터 QRA 완료나 시설 IR/F-N을 뜻하지 않습니다. 상세한 원자료 해시·차단 사유·승격 규칙은 [외부 provider 검증 감사 기록](docs/PRISM_외부설비_provider_검증감사_20261009.md)에 보관합니다.

외부 모델 담당자가 실제 사고 packet을 만들 때 필요한 공통 필드·시계·질량/엔탈피 장부·소유권·exact opening 규칙은 [provider 방출 packet 요청 사양](docs/PRISM_provider_resolved_release_v1_요청사양_20261009.md)에 정리했습니다. `audit_external_provider.py`도 같은 사양을 `release_evidence.provider_export_request`로 출력합니다.

감사기는 이제 provider 루트의 JSON을 재귀적으로 인벤토리하여 사고 방출 계약도 확인합니다. `event_kind=accidental_leak`, 고장 개구, 시간별 `steps`, 지속시간, 누적 질량·엔탈피, 설비·포트·위치·방출 digest, 그리고 명시적인 `provider_export_schema`가 모두 있는 packet만 `QUALIFIED_ACCIDENT_RELEASE_EXPORT` 후보로 셉니다. 필드가 모두 있어도 `ResolvedGasRelease`/`ResolvedLiquidRelease` strict 검증을 다시 실행해 출구 연속성, 질량·엔탈피 장부, provider 시계, 수직 handoff와 유한값을 확인하며, 실패는 `strict_validation_failures`로 보존합니다. 일반 운전·스크리닝 JSON에 유량 열이 있어도 사고 계약이 없으면 `normal_or_screening_flow_file_count`로만 기록하며, 2026-10-10 재감사에서 센터 JSON **561개**를 확인했지만 사고 방출 후보 0건·적격 0건으로 시설 위험 계산 승격이 차단됩니다.

작업공간의 과거 `PRISM_IJHE_step1` 출력은 JSON 84개 중 방출 후보 42개가 있었지만 현재 `provider_export_schema`가 없어 0건 적격으로 남았습니다. 이는 합성 개발 출력의 존재를 확인한 것이며, schema를 사후 삽입해 실제 provider packet으로 만들지 않습니다. 자세한 검색 결과는 [provider artifact 검색 증거](examples/provider_artifact_search_evidence.json)에 있습니다.

이 legacy 출력 판정은 `scripts/audit_legacy_provider_artifacts.py`로 재현할 수 있습니다. 현재 계약이 없는 후보를 수정하지 않고, `LEGACY_OUTPUT_REQUIRES_EXPLICIT_SCHEMA_MIGRATION`으로 별도 표시합니다.

현재 provider와 legacy 폴더를 함께 확인할 때는 `scripts/audit_provider_artifact_roots.py`를 사용합니다. 두 결과를 합쳐 시설 위험으로 승격하지 않고, 현재 적격 packet 수와 legacy schema 누락 수를 분리해 보여 줍니다.

센터 폴더의 시나리오 CSV와 Excel도 별도로 감사합니다. 현재 CSV 3개 52행에서 `pipe_hole` 11, `valve_hole` 23, `vaporizer_hole` 4, `vent_hole` 4, `vessel_hole` 1, `inventory_over_600s` 1개의 사고 후보 family를 확인했고, Excel 17개에서 sequence 시트 21개와 time-series 시트 43개를 확인했습니다. time-series 43개 시트의 timestamp/일시와 PT·TT·DPT 센서 열, 관측 샘플 간격(중앙값 1초 7개, 60초 26개, 900초 10개)도 읽기 전용으로 기록했습니다. 이 파일들은 설비 운전상태·위험 후보 근거로 보존하지만 방출량·종료시각·위치·질량/엔탈피 장부가 없어 provider packet으로 승격하지 않습니다. 센서 기반 빈도도 학습하지 않습니다. 결과는 [센터 시나리오 증거 감사 기록](docs/PRISM_센터_시나리오_증거감사_20261009.md)과 `results/20261009/provider_evidence/center_scenario_evidence_audit.json`에 기록합니다. 실제 `액화수소검사지원센터 데이터` 폴더를 2026-10-09에 재감사해 동일 수치를 확인했으며, 재감사 산출물은 `results/20261014/center_scenario_evidence_live_audit.json`과 `center_provider_packet_request_catalog_live.json`에 남겼습니다. 후보 family 38행은 별도의 provider packet 요청 catalog로 정리했지만 `qualified_packet_count=0`, 빈도 미부여 상태를 유지합니다 (`scripts/build_provider_packet_request_catalog.py`, `center_provider_packet_request_catalog.json`).

provider가 `prism.resolved_release.v1` packet을 내보내면 다음 adapter로 명시된 피해 계산 문맥에 연결할 수 있습니다. adapter는 packet의 상·개구·시간·질량/엔탈피 장부를 strict contract로 검증하고, `weather`, `ignition`, `domain`, 평가시계, 종료근거를 담은 defaults와 결합합니다. 빈도는 이 단계에서 부여하지 않으며, 이후 `--request-catalog`와 `bind_event()`의 설비·개구 exact-match에서만 연결됩니다.

```powershell
python lh2-tno/scripts/build_provider_request_catalog.py `
  --provider-release-catalog provider_releases.json `
  --request-defaults lh2-tno/examples/provider_request_defaults.json `
  --output provider_request_catalog.json
```

저장소의 `examples/provider_release_catalog_synthetic.json`은 adapter 실행을 확인하기 위한 합성 packet이다. 실제 설비·실측·빈도 근거가 아니며, 외부 provider가 생성한 packet으로 교체해야 한다.

합성 액체 packet(`examples/provider_release_catalog_synthetic_liquid.json`)은 request adapter 뒤에 기존 설비 campaign과 backend를 이어 보는 진단도 제공합니다. `LH2_VESSEL AREA_0.01%` 개구와 정확히 맞는 1건을 source→SLABx-LH2/DynamicLH2PoolX→확산→점화·피해까지 실행했고, 9개 다른 개구 사건은 `UNCOMPUTED`로 남겼습니다. case 약 1.61초, campaign 약 1.81초였지만 packet·기상·종료근거가 합성이라 시설 전체 IR/F-N은 보류하고 `EXECUTED_OPERATOR_LIMITED`로 표시합니다. 결과는 `results/20261009/provider_release_full_chain_diagnostic/`에 기록합니다.

같은 결과에 `examples/provider_full_chain_frequency_uncertainty.json`을 적용하면 물리를 다시 실행하지 않고 문헌 p05/p95와 within-asset shared / independent-event 상관 가정을 비교합니다. 네 시나리오가 생성되며 known-contribution IR은 p05 `3.7383e-06`, p95 `1.1303e-03`/년으로 재가중됩니다. 이 값은 미계산 사건과 합성 물리를 포함한 시설 전체 credible interval이 아니므로 `facility_credible_interval=false`로 남습니다.

`request-defaults`의 `source_operator`와 `release_termination`은 설비별로 검토해 작성해야 합니다. provider duration과 종료시각이 일치하지 않거나, 두 양단 파열 set을 단일 packet으로 넣거나, source/frequency를 defaults에 넣으면 해당 packet은 `uncomputed`로 남습니다. 예제 defaults의 합성 확률·기상·종료근거는 실제 시설 값이 아닙니다.

공개 소스/예제/문서는 [Zenodo 소프트웨어 기록](https://doi.org/10.5281/zenodo.23241358)의 배포 파일을 사용합니다. 버전별 DOI는 릴리스 후 이 문서와 `CITATION.cff`에 기록합니다.
내부 폴더 `lh2-tno`, import `lh2_tno`, host 모듈 `tno_host`는 기존 연동 호환성을 위해 유지합니다.
과거 `lh2-tno` 배포본을 설치한 환경과 혼용하지 않도록 새 가상환경 사용을 권장합니다.

### 외부 물리 모델 없이 실행

```powershell
# 모드 확인
.venv\Scripts\python.exe prism.py --describe-modes

# 시설 구성만 검증: 물리 계산은 실행하지 않음
.venv\Scripts\python.exe prism.py --mode lh2 lh2-tno/examples/storage_terminal.json

# 문헌 기반 사고 사건/빈도 생성
.venv\Scripts\python.exe prism.py --mode lh2 lh2-tno/examples/lh2_frequency_facility.json --frequency-plan lh2-tno/examples/lh2_frequency_plan.json --output events.json

# 도움말
.venv\Scripts\python.exe prism.py --help
.venv\Scripts\python.exe prism.py --mode lh2 --help
```

빈도 예제는 **16개 사건**을 생성하며 `total_facility_annual_risk=null`입니다.
빈도를 계산했지만 모든 사건의 피해와 전체 시설 위험을 합산하지 않았다는 뜻입니다.
모든 예제는 합성 입력이며 실측 데이터나 검증된 시설 설계값이 아닙니다.

설치된 명령은 `.venv\Scripts\prism.exe --mode lh2 ...`로 실행합니다.
Linux/macOS에서는 `.venv/bin/python`, `.venv/bin/prism`을 사용합니다.
기존 `python tno.py`, `tno`, `lh2-tno`, `python -m lh2_tno.cli`도 호환용으로 유지합니다.
마지막 두 명령은 모드 선택 없이 LH2 경로를 직접 실행합니다.

### 모드 설정 파일

```json
{"mode": "lh2"}
```

```powershell
.venv\Scripts\python.exe prism.py --config lh2-tno/examples/prism_lh2_mode.json lh2-tno/examples/storage_terminal.json
```

설정은 `mode`, `backend`만 허용합니다. backend 상대경로는 **설정 파일 위치** 기준입니다.
CLI의 `--mode`·`--backend`가 설정값보다 우선합니다. 모드는 파일명으로 추정하지 않습니다.
CLI 시설·요청 상대경로는 작업 폴더 기준이며 backend 내부 모델 경로는 절대경로를 권장합니다.

## 입력 파일 작성

| 파일 | 내용 | 대응 예제 |
|---|---|---|
| `facility.json` | 환경, 부품, 포트, 연결, 수용점, 물성 기준 | [저장기지](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/storage_terminal.json), [충전시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/refuelling_station.json), [이송시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/transfer_station.json) |
| `frequency_plan.json` | 문헌 프로파일, 분류 근거, 수량/길이, 물리 범위, 제외 이유 | [계획](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/lh2_frequency_plan.json) + [시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/lh2_frequency_facility.json) |
| `consequence_request.json` | source 또는 설비 출구, 재고, 기상, 점화, 풀, 평가 시각/영역 | [요청](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/consequence_request.json) + [시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/consequence_facility.json) |

**다른 예제 파일을 임의로 섞지 않습니다.** 부품 ID, 탱크 체적, 물성 기준, 출구와 재고가 일치해야 합니다.
일반 저장기지 예제의 탱크와 짧은 0.2 m³ 계산 예제는 다른 입력입니다.

| 시설 필드 | 작성 기준 |
|---|---|
| `configuration_origin` | `synthetic`, `reviewed_design`, `field_confirmed`: 실제 출처대로 선택 |
| `environment` | 스키마에는 여러 환경이 있으나 현재 전체 LH2 물리 경로는 `outdoor` |
| `components` | 고유 ID, 종류, ENU 좌표, 물성 기준, SI 설비 치수 |
| `ports` / `edges` | 실제 연결과 유동 방향·상 정의 |
| `property_basis` | Hydrogen/ParaHydrogen, CoolProp-HEOS와 엔탈피 기준 |
| `receptors` | 사람/피해 평가 지점의 ID·ENU 좌표 |

ENU는 동쪽(E)·북쪽(N)·위쪽(U)입니다. 길이 m, 온도 K, 압력 Pa, 유량 kg/s, 비엔탈피 J/kg을 사용합니다.
중복 ID, 잘못된 포트·상·방향과 물성/엔탈피 혼용을 거절합니다. 구성 검증만으로 전체 설비 동역학을 풀지는 않습니다.
정확한 필드는 [시설 계약](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/contracts.py), [피해 요청](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/consequences.py), [빈도 계약](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/frequency.py) 또는 스키마로 확인합니다.

```powershell
.venv\Scripts\python.exe -c "import json; from lh2_tno.consequences import ConsequenceRequest; print(json.dumps(ConsequenceRequest.model_json_schema(), ensure_ascii=False, indent=2))"
```

## 외부 모델 연결

시설 검증과 빈도 생성은 이 저장소만으로 가능합니다. 실제 방출·분산·화재/폭발에는 **외부 모델 소스와 실행 환경**이 필요합니다.
일반 source→풀→피해 경로는 `tno`, `slabx_lh2`, `slabx`, 그리고 풀 발생 시 `dynamiclh2poolx`를 사용합니다.
설비 출구 생성 operation에는 `lh2dt`도 필요합니다. 기록된 기체 출구만 소비하면 실행하지 않는 provider/pool은 필요 없습니다.

아래 코드를 `configure_backend.py`로 저장하고 실제 경로와 interpreter를 수정한 뒤 실행합니다.
`tno`는 qra.py/fire.py/risk.py 등이 있는 코드 폴더, 나머지는 각 Python 패키지 디렉터리 자체입니다.

```python
import json
from pathlib import Path
from lh2_tno.backend import tree_digest

roots = {
    "tno": Path("D:/models/legacy-qra/code"),
    "slabx_lh2": Path("D:/models/slabx-lh2/slabx_lh2"),
    "slabx": Path("D:/models/slabx/slabx"),
    "dynamiclh2poolx": Path("D:/models/pool/src/dynamiclh2poolx"),
}
config = {
    "interpreter": "D:/models/runtime/Scripts/python.exe",
    "timeout_s": 180.0,
    "packages": [
        {"name": name, "root": str(root.resolve()), "sha256": tree_digest(root)}
        for name, root in roots.items()
    ],
    "required_versions": {},
}
Path("backend.json").write_text(
    json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
)
```

`required_versions`에는 재현 실험에서 확인한 CoolProp/NumPy/SciPy 등의 실제 버전 문자열을 추가합니다.
위 예제는 비어 있으며 외부 runtime의 의존성을 PRISM 최소 설치가 자동 설치해 주지는 않습니다.
모델 연결 뒤 실제 계산과 출처를 확인해야 합니다. 소스 pin만으로 물리 호환성/정확도가 보증되지 않습니다.
실행 전후 소스 SHA-256, 실제 import 위치, 지정 버전과 timeout을 검사합니다.
소스가 변경되면 검토·검증·기록 후 pin을 갱신하고 매 센서 갱신마다 자동으로 새 해시를 승인하지 않습니다.

## 기본 분석 모드

`standard`는 외부 엔진의 `qra.py` 명령을 그대로 전달합니다. 기존 CSV와 LH2 JSON 입력은 서로 다릅니다.
backend에는 `tno` pin과 기존 엔진을 실행할 interpreter가 필요합니다.

```powershell
# 외부 엔진 옵션 확인
.venv\Scripts\python.exe prism.py --mode standard --backend standard_backend.json --help

# CSV 템플릿 생성
.venv\Scripts\python.exe prism.py --mode standard --backend standard_backend.json template --directory standard_inputs

# 입력을 검토·수정한 뒤 실행
.venv\Scripts\python.exe prism.py --mode standard --backend standard_backend.json run --name my-facility --sections standard_inputs/sections.csv --components standard_inputs/components.csv --ignition purple --blocking none --samples 0 --extent 100 --cell 10 --out standard_result.json
```

엔진 버전의 `--help`와 생성된 파일명을 확인하고 실제 설비로 입력을 수정합니다.
점화·차단·격자 옵션은 명시 선택한 예시이며 모든 시설의 추천 기본값이 아닙니다.
기존 엔진에는 GH2/LH2 screening도 있으므로 standard를 “고압수소 전용”으로 해석하지 않습니다.
결과에 `execution_mode=standard`와 소스 해시를 더하고 기존 수치·근거 판정을 유지합니다.

## LH2 피해영향 계산

```powershell
.venv\Scripts\python.exe prism.py --mode lh2 lh2-tno/examples/consequence_facility.json --backend backend.json --consequences lh2-tno/examples/consequence_request.json --output consequence_result.json
```

예제는 0.2초 방출의 합성 진단 계산입니다. 입력 빈도·점화·복사율을 시설 기본값으로 복사하지 않습니다.
지면 도달량이 없으면 풀을 만들지 않습니다. LH2가 지면에 도달하면 footprint와 바닥 물성/수치 격자를 별도 지정해야 합니다.

요청 작성 시 다음을 검토합니다.

- `source_input` 또는 `resolved_release` 중 정확히 하나 선택.
- 탱크 상태, 누출 구경·방향·높이, 재고와 방출 종료 근거.
- source와 dispersion의 동일 기상. 현재 무풍·실내·provider handoff 없는 수직 전용 출구는 미지원.
- 시계에 방출 종료/지연점화 시각 포함, 지연 연소 종료까지 평가.
- 점화 분기, 복사율 범위, 장애물 에너지 분율과 출처.
- 공간 영역·격자. 영역 밖 질량은 기록하지만 그 영역 밖의 피해는 계산하지 않음.

현재 피해 시계는 120초/500노드 이하, 공간 250,000셀 이하, source 100구간 이하 등의 예산을 적용합니다.
한도만 늘려 큰 시설의 정확도/실행시간 문제가 해결되지는 않습니다.
폭발은 multi-energy의 **두 압력 기준 구역**을 사용하며 연속 압력/충격량 곡선, DDT·폭굉은 지원하지 않습니다.

### 설비 provider의 액체·2상 출구 연결

설비 모델이 액체 방출을 직접 계산했다면 `ResolvedLiquidRelease`를 사용합니다. 이 경계에는 provider가 소유한 총 유량, flash된 대기압 기체 유량, 지면 액체 유량, 액적 도착 위치·시간, 전체 질량·엔탈피 장부가 들어갑니다. PRISM은 이 값을 다시 nozzle/flash 계산으로 바꾸지 않고, 기체는 근거리 전이와 SLABx로, 지면 액체는 DynamicLH2PoolX로 전달합니다. airborne liquid이 남아 있으면 암묵적으로 기체로 바꾸지 않고 중단합니다.

```powershell
# 외부 provider pin과 runtime을 검토한 뒤 한 건의 연결 진단 실행
$env:PYTHONPATH = "lh2-tno/src"
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_liquid_release.py
```

진단 산출물은 `lh2-tno/results/20261009/equipment_liquid_release/`에 저장됩니다. `verification.json`의 `full_chain_executed=true`는 설비 경계부터 피해 계산까지 연결됐다는 뜻이고, `physical_validation_claim=false`, `operator_limited=true`는 SLABx-LH2의 일정 upstream·분무 에너지·ballistic rainout 가정과 합성 시설 입력이 남아 있음을 뜻합니다. 이 경로는 실제 LayeredTank의 액체/2상 재고 소진, airborne droplet adapter, 현장 빈도와 시설 전체 연간 IR을 대신하지 않습니다.

### Python API

```python
import json
from pathlib import Path
from lh2_tno.contracts import Facility
from lh2_tno.backend import BackendConfig, IsolatedBackend
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.pipeline import ResearchPipeline

facility = Facility.model_validate_json(Path("facility.json").read_text(encoding="utf-8"))
config = BackendConfig.model_validate_json(Path("backend.json").read_text(encoding="utf-8"))
request = ConsequenceRequest.model_validate_json(Path("consequence_request.json").read_text(encoding="utf-8"))
pipeline = ResearchPipeline(facility, IsolatedBackend(config))
result = pipeline.consequences(request)
Path("result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
)
```

API 호출에는 CLI가 덧붙이는 `execution_mode` 표기가 자동 추가되지 않습니다.

## 빈도 산출과 적용

[빈도 catalogue](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/data/frequency_catalogue.json)는 검토한 Purple Book LOC 표와 기존 LH2 문헌 표 snapshot을 사용합니다.
각 행에 출처·원자료 해시·통계 의미·단위·한계를 보관하며 기관 인증이나 현장 빈도 검증을 뜻하지 않습니다.
원자료 검토는 [빈도 개발 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md)을 참고합니다.

| 항목 | 계산 |
|---|---|
| 부품당 빈도 | 문헌의 부품당 연간 빈도 × 수량 |
| 배관 길이당 빈도 | m당 연간 빈도 × 적용 길이 × 수량 × 근거 있는 보정계수 |
| 요구시 실패 | 요구 빈도 × PFD, 별도 계약 제공 |
| LH2 불확실성 | 문헌 중앙값과 로그정규 분산 근거로 구간별 주변 p05/p95 및 명시적 표본화 |

Purple 배관에는 최소 적용 길이 10 m와 flange 포함 범위가 있습니다. 포함 flange를 다시 더하지 않습니다.
`physical_scope_ids`로 동일 실물의 중복을 거절합니다. 같은 탱크의 Purple LOC와 LH2 면적구간 빈도를 모두 더하지 않습니다.
구간별 p05/p95를 합쳐 시설 전체 p05/p95라고 표시하지 않습니다. 로그정규 mu/sigma 표본화는 known contribution에만 적용하며, 모든 물리·기상·방호·점화 항은 고정합니다.
대기압 근처 극저온 탱크에 압력용기 프로파일을 자동 적용하지 않습니다.
진공 상실·정상 벤트 요구·대기압 저장탱크 전용 기인 빈도는 보완 항목입니다.
미지원 프로파일은 GH2/OREDA로 암묵 대체하거나 0으로 만들지 않습니다.

### 사건별 피해와 결합

먼저 생성한 events에서 실제 ID·부품·구멍 크기·범위를 확인합니다. 다음 placeholder를 실제 사건 ID로 바꿉니다.

```powershell
.venv\Scripts\python.exe prism.py --mode lh2 facility.json --frequency-plan frequency_plan.json --event-id 검토한_사건_ID --backend backend.json --consequences matching_request.json --output matched_result.json
```

빈도 계획과 피해 요청을 함께 주면 `--event-id`가 필수입니다. 현재 기본 binding은 일치하는 **단일 부품 구멍 사건**이며,
누출 구경·부품·노출 범위·방출 종료·service를 대조합니다. source는 탱크/용기 구멍 사건,
설비 경계는 명시된 accidental leak이어야 합니다. GH2/cold-GH2에 LH2 빈도를 붙이지 않습니다.
순간 전량과 최대 relief는 사건을 생성해도 새 피해 경로에 자동 결합하지 않습니다. 양단 파단은 `ResolvedGasReleaseSet`에 두 provider 출구를 모두 선언하고
`equipment_two_sided_rupture`를 선택하면 두 출구를 각각 피해 계산한 뒤 한 사건의 Frechet 상한으로 결합합니다. 이제 각 수용점·점화분기마다 endpoint harm과 Frechet 교집합 가능 범위를 `prism.two_sided_interaction_diagnostic.v1`로 함께 기록하며, 공동 plume을 계산했다고 가정하지 않습니다. `TNO_PIPE` 길이/수량 빈도를 한 위치에 배정할 때는 `location_weight`와 근거를 함께 선언해야 합니다. 두 endpoint에는 하나의 initiating-event 빈도만 적용하고 빈도를 분할하거나 중복하지 않습니다. 교차 plume·압력·재고 상호작용은 아직 operator-limited로 기록됩니다. 600초 전량은 기체 provider의 `equipment_inventory_over_600s` 또는 액체·2상 provider의 `equipment_liquid_over_600s` operator와 `inventory_over_600s` 종료 근거를 선언하고 provider가 600초 전체 이력을
반환해야 binding할 수 있습니다. 현재 합성 campaign은 이 완전 이력을 제공하지 않아 G2를 미계산으로 유지합니다.
빈도만으로 임의의 짧은 누출 시간은 정당화되지 않습니다.

양단 파열 provider 입력은 `prism.resolved_release_set.v1` 최상위 packet으로 묶습니다. `releases`에 두 개의 `prism.resolved_release.v1` endpoint를 넣고 공유 재고·사건 ID를 한 번 선언하면, `scripts/build_provider_request_catalog.py`와 `scripts/build_equipment_campaign.py`의 `--release-kind two_sided_rupture`가 전용 adapter를 사용합니다. endpoint를 복사해 단일 누출로 바꾸거나 사건 빈도를 두 번 부여하지 않습니다. 적격 provider sidecar를 사용할 때는 두 endpoint의 source digest(및 제공된 result digest)가 모두 같은 순서로 일치해야 합니다.

### 문헌 빈도 불확실성과 상관 가정

현재 현장 사고 건수와 관찰 노출 자료는 없습니다. **문헌 기본선 + 불확실성·민감도를 사용하며
개발/첫 IJHE 논문에 현장 빈도 수집을 필수 조건으로 두지 않습니다.** `literature_frequency_uncertainty`
는 자산별로 같은 분위수를 모든 LOC에 적용하는 `within_asset_shared_quantile`과, 각 사건에
분위수를 따로 지정하는 `independent_event_bounds`를 명시적으로 비교할 수 있습니다. 이는 상관 가정
민감도 비교이며, 별도 distribution API는 catalogue에 공개된 로그정규 mu/sigma가 있는 사건만 표본화합니다. 현재 사례처럼 미계산·operator-limited 경로가 있으면 known-contribution 구간으로만 보고하고 시설 전체 credible interval로 부르지 않습니다.

분포 표본화는 다음처럼 실행합니다. 입력 파일은 `examples/frequency_distribution_diagnostic.json` 형식의 두 시나리오 배열입니다.

```powershell
python prism.py --mode lh2 facility.json --backend backend.json --risk-campaign campaign.json `
  --frequency-distribution examples/frequency_distribution_diagnostic.json `
  --frequency-distribution-draws 2000 --frequency-distribution-seed 20261009 `
  --output distribution_result.json
```

출력의 `literature_frequency_distribution.scenarios[*]`는 known contribution의 p05/p50/p95와 사건별 표본 빈도를 담습니다. `asset_rank_stability`에는 각 빈도 표본에서 계산된 기대 사망 기여도의 평균 순위와 1위 확률을 낮은/높은 복사율 끝점별로 기록합니다. 동률은 자산 ID로 결정해 재현성을 확보합니다. 표본화는 저장된 피해 원자를 다시 가중하므로 SLABx-LH2나 확산 물리를 반복 실행하지 않습니다. 이 순위는 계산된 known contribution 안에서만 유효하며, 미계산 사고를 포함한 시설 전체 우선순위를 뜻하지 않습니다.
캠페인 기본 결과의 `coverage.by_component`에는 시설의 각 탱크·배관·밸브·펌프 등에 대해 생성된 사건 수, 개시빈도, 실행/미계산 건수와 명시적 제외 사유가 들어갑니다. `PARTIAL` 또는 `EXCLUDED` 설비가 남아 있으면 합산값을 전체 시설 위험으로 표시하지 않습니다.
시설을 여러 campaign으로 합칠 때는 `prism.facility_risk_ledger.v1`의 `component_coverage`가 설비별 결합 원장 역할을 합니다. 각 행은 event ID, 고유 조건 case 수, 실제 consequence 결과 수, 엄격한 보류 행 수, operator-limited/domain-incomplete/failed 수와 risk atom 수를 보존합니다. provider packet의 `component_id`를 먼저 사용하고, 구형 행은 event의 `model_component_id`로 보완합니다. 조건부 case는 event·기상·방출 branch·점화 branch 조합으로 중복을 제거하지만, 엄격한 보류 행은 원자료 행 수를 그대로 남깁니다. 따라서 이 표는 설비별 연결 여부를 보여주지만 빈도를 새로 만들거나 미계산 설비의 위험을 0으로 만들지 않습니다. `scripts/build_facility_evidence_request.py`는 이 원장을 읽어 설비별 evidence request와 gate category도 함께 출력합니다.
실증 P/T/유량은 물리 검증에 쓰지만 사고 건수·관찰 설비수·기간을 대신하지 않습니다.
확인된 사고와 동일 범위의 관찰 노출이 생기면 선택형 Gamma-Poisson 업데이트 계약을 적용할 수 있습니다.
경보 건수를 누출 건수로 세거나 문헌 로그정규 분포를 근거 없이 Gamma로 바꾸지 않습니다.

## 설비와 디지털트윈 연결

### 설비별 결합

시설 부품/포트 ID를 설비 모델 출구에 대응시켜 **지원되는 방출 경계를 사건별로** 전달합니다.
이미 계산된 기화기·벤트 출구 유량을 받으면 탱크 누출식을 다시 풀지 않습니다.
등록한 모든 부품의 임의 누출을 즉시 지원하는 것은 아닙니다.

`ResolvedGasRelease`에는 PH·엔탈피 기준·단면적·밀도·속도·유량·시계·누적 질량/정적 엔탈피와 provider 해시가 필요합니다. 포트에 `position_enu_m`을 선언하면 provider 방출 좌표도 같은 위치여야 합니다. 양단 파열은 `ResolvedGasReleaseSet`이 동일 사건 ID·공유 재고·서로 다른 outward 포트·두 위치를 검증합니다.
현재 수평 또는 `VerticalGasHandoff`로 수평 단면을 선언한 수직 출구의 대기압·Mach≤0.3 기체와, provider가 flash·지면 액체·액적 도착을 완결한 `ResolvedLiquidRelease`를 허용합니다. 액체/2상 경계에는 `phase=liquid` 또는 `phase=two_phase`인 outward facility port가 필요합니다. airborne liquid, 실제 설비의 LayeredTank 액체/2상 재고 feedback, provider handoff 없는 수직 제트·고압 팽창 출구는 추가 adapter가 필요합니다. 합성 LayeredTank는 별도 양수 임계값 진단으로 재고 feedback 경로를 확인했습니다. 수직 handoff와 provider liquid 경로도 synthetic provider 경계와 downstream 교차상호작용 미해결 때문에 operator-limited입니다.
외부 `LayeredTankNetworkSimulator` 결과는 `scripts/audit_layered_tank_boundary.py`로 먼저 감사할 수 있습니다. 탱크 재고·포트·링크 유량이 있어도 대기압 출구, flash/지면/비산 액체 분할, 출구 형상, 종료 계약이 없으면 `ResolvedLiquidRelease`로 승격하지 않습니다. 액체 포트를 101,325 Pa 경계에 연결한 probe는 대기 경계까지 확인했지만 동일한 누락으로 승격이 보류되었습니다. 실제 provider 실행 결과와 판정은 [LayeredTank 경계 감사 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_LayeredTank_경계감사_개발기록_20261009.md)에 보존합니다.
`liquid_atmospheric_probe_export.json`은 `scripts/validate_layered_tank_slabsx_bridge.py`로 SLABx-LH2에 넘길 수 있습니다. 이 브리지는 LayeredTank의 전체 유량을 최종 질량 장부로 유지하고, SLABx의 flash·액적/지면 분할만 사용합니다. 첫 구간 유량 상대 오차는 2.4529%로 5% gate 안에 있었고, `ResolvedLiquidRelease` 검증과 풀·확산·점화·피해까지 전체 진단을 실행했습니다. 결과는 `results/20261009/equipment_layered_tank_slabsx/`에 저장되며, 책임 분리와 한계는 [LayeredTank–SLABx 브리지 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_LayeredTank_SLABx_브리지_개발기록_20261009.md)에 설명합니다. 이 결과는 합성 probe의 연결 검증이며 LayeredTank 전체 설비 모델·현장 보정·시설 전체 연간 위험 완성을 의미하지 않습니다.
`validate_layered_tank_inventory_slabsx.py`는 외부 `lh2dt.LayeredTankNetworkSimulator`를 0.5초씩 다시 실행하며 탱크 상태를 다음 구간에 feedback합니다. 누적 provider 질량 장부로 구간 평균 유량을 만들고 양수 재고 임계값에서 종료한 뒤 같은 SLABx·PRISM 체인을 실행합니다. 16개 구간/8초, provider 최대 질량 잔차 `5.65e-18 kg`, 최대 에너지 잔차 `1.34e-8 J`, PRISM 최종 잔차 `0 kg`을 확인했습니다. 결과는 `results/20261009/layered_tank_inventory_slabsx/`와 [재고 feedback 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_LayeredTank_SLABx_브리지_개발기록_20261009.md)에 보존합니다. 임계값·형상·밸브는 합성값이며 실제 설비의 완전 재고 소진이나 시설 전체 QRA를 뜻하지 않습니다.
`validate_layered_tank_frequency_campaign.py`는 provider 개구를 문헌 사건의 개구와 대조한 뒤 정확히 일치하는 한 개 사건만 `bind_event()`로 연결합니다. 이번 진단은 저장탱크·격리밸브·이송배관 15개 LOC를 생성하고, 0.001 m 개구와 저장탱크 `AREA_0.01%`만 연결했습니다. 나머지 14개 LOC는 두 기상 조건에서 미계산으로 기록했습니다. 문헌 p05/중앙/p95와 공개 로그정규 표본은 저장된 위험 원자를 재가중하며 물리를 다시 계산하지 않습니다. 결과는 `results/20261009/layered_tank_frequency_campaign/`와 [문헌빈도 연결 기록](docs/PRISM_LayeredTank_문헌빈도_시설연결_20261009.md)에 보존합니다.
정상 벤트에 사고누출 빈도를 붙이지 않습니다. emergency relief도 기인 사건/요구 의미를 별도 검토합니다.
상세: [경계 계약](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/equipment_boundary.py), [설비 연결 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md).

### 탱크·밸브 차단 과도 경로

개발 진단에서는 `scripts/validate_equipment_isolation.py`가 외부 `lh2dt`의 `LayeredTankNetworkSimulator`와 `CommandedValve`를 호출합니다. 합성 LH2 탱크를 초기화하고, 각 문헌 `LH2_PIPE` area-bin마다 밸브 면적을 독립적으로 계산합니다. 각 area-bin에서 하나의 provider 실행은 밸브를 0.25초까지 열어 둔 뒤 닫고, 다른 실행은 차단 실패로 0.5초 진단시계까지 열어 둡니다. provider가 반환한 각 시간구간의 유량·출구 PH·밀도·면적·속도를 `ResolvedGasRelease`로 변환하고, 5개 LOC의 두 분기를 시설 campaign에 연결합니다.

이 경로에서 확인한 것은 **5개 누출 크기 각각에서 명령된 차단 성공과 명시적 차단 실패가 서로 다른 방출 이력으로 피해계산에 전달되는지**입니다. 성공 분기는 0.25초 뒤 유량이 0이 되고, 실패 분기는 0.5초 진단시계 동안 유량이 남습니다. 질량·에너지 잔차도 각 분기에 기록됩니다. 5개 LOC × 2개 차단 분기 × 2개 기상으로 20건이 실행되며 `UNCOMPUTED` 사례는 0건입니다. 차단 성공확률 `0.99`는 합성 분기값이며, 실제 actuator 지연·고장확률·재고 소진을 추정하지 않습니다. 이 transient campaign 자체에는 액체·2상 경계가 없지만 별도 `validate_equipment_liquid_release.py`가 provider liquid/two-phase 출구 1건을 pool·피해까지 연결합니다. 결과는 `results/20261009/equipment_isolation_campaign/`와 `results/20261009/equipment_liquid_release/`에 저장하며, 합성 진단시계와 합성 장벽 때문에 시설 전체 연간 위험도는 `null`로 남깁니다.

개발 환경에서 이 진단을 다시 실행하려면 외부 provider 경로가 현재 스크립트와 같아야 합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_isolation.py
```

이 명령은 provider transient 성공·실패 이력을 각각 계산한 뒤 두 기상 조건의 시설 사례에 전달합니다. 실행시간은 PC·격자·시계에 따라 달라지며, 결과의 `verification.json`과 `campaign_result.json`을 함께 확인합니다.

600초 전량방출의 연결 진단은 다음 명령으로 재현합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_long_horizon_inventory.py --allow-pin-refresh
```

이 진단은 합성 10 m³ 탱크와 100000 W 벽면열을 사용해 600초 provider 이력을 만들고 전체 피해 체인을 실행합니다. 결과는 `EXECUTED_DIAGNOSTIC_ONLY`와 `facility_validation=WITHHELD`로 기록되며 실제 설비 QRA로 해석하지 않습니다.

### 양수 재고 기준으로 방출을 끝내는 경로

`scripts/validate_equipment_inventory.py`는 외부 `lh2dt`의 `HomogeneousTank`와 `DynamicNetworkSimulator`를 한 provider 구간씩 실행합니다. 탱크 질량이 선언한 양수 `threshold_mass_kg` 이하가 되면 그 구간의 실제 유량·엔탈피를 저장하고 종료합니다. 0 kg 상태를 강제로 만들거나 마지막 유량을 40초까지 늘리지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_inventory.py
```

현재 다섯 `LH2_PIPE` area-bin을 두 기상 조건에 연결하여 **10건 실행·0건 미계산**으로 기록했습니다. provider는 모두 `inventory_depletion`으로 종료했고, `AREA_100%`의 남은 질량은 `1.0793e-4 kg`, 다섯 사례의 최대 질량 잔차는 `1.34e-20 kg`, 최대 에너지 잔차는 `1.69e-13 J`였습니다. 이번 신규 물리 계산시간은 약 1.59–2.31초/건, 전체 약 20.85초였습니다. 결과는 `results/20261009/equipment_inventory_campaign/`에 저장합니다. declared-scope IR/F-N은 계산되지만 합성 시설 입력이므로 실제 시설 QRA로 보고하지 않습니다.

이 경로는 탱크 상태에서 피해까지 연결되는 종료 계약을 검증한 것입니다. 초기 상태·탱크 크기·밸브·기체 offset은 합성값이며, 액체/2상 flash, high-Mach jet, actuator 신뢰도, 실제 설비 calibration과 독립 물리검증은 포함하지 않습니다. 자세한 경계와 산출물은 [재고 소진 연결 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_재고소진_연결_개발기록_20261009.md)을 봅니다.

### 수직 벤트 handoff 진단

수직 포트 자체를 downstream 모델이 자동으로 수평으로 바꾸지 않습니다. 설비 provider가 수직 출구와 함께 수평 handoff 위치·방향·속도·밀도·온도·수소 질량분율·단면 크기를 `VerticalGasHandoff`로 제공할 때만 PRISM이 그 단면부터 SLABx-LH2/SLABx 경로를 시작합니다. handoff가 없는 수직 출구, 수직·수평이 섞인 방향, 음의 downwind 성분은 오류 또는 `UNCOMPUTED`로 남습니다.

현재 synthetic handoff 진단은 다음과 같이 실행합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_vertical_vent.py
```

`AREA_100%` 경로와 두 기상 조건의 2건을 실행하고, 나머지 네 area-bin은 provider handoff가 없다는 이유로 명시적 `UNCOMPUTED`로 남깁니다. 결과는 `results/20261009/vertical_vent/`의 `campaign_result.json`, `resolved_release.json`, `verification.json`에 저장합니다. 이 경로는 variable-state synthetic adapter이므로 실제 수직 제트 부력·장애물·교차 plume와 현장 handoff를 검증한 것이 아닙니다.

새 프로세스로 처리시간을 반복 측정하려면 다음을 실행합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/benchmark_vertical_vent_timing.py --repeats 3
```

이번 3회 탐색 측정에서 campaign 내부 신규 물리시간은 p50 `7.170 s`, p95 `7.352 s`, p99 `7.368 s`였고, 프로세스 시작·외부 provider 로딩을 포함한 wall time은 p50 `12.005 s`, p95 `12.245 s`, p99 `12.266 s`였습니다. 이는 1 Hz 실시간 처리나 운영 SLA를 입증하지 않으며 `results/20261009/vertical_vent_timing/benchmark.json`에 저장합니다.

### 센서 갱신

```text
센서 → 단위/위치/품질/시간 검증 → 알려진 누출의 탱크 P/T 갱신
→ 동일 조건이면 캐시, 변경이면 새 계산 → 결과와 자료 나이 표시
```

`TelemetryNormalizer`는 절대압/게이지압·대기압·위치·단위·품질·시간순서·나이를 검사합니다.
현재 서비스가 source 갱신에 사용하는 것은 지정한 탱크 P/T입니다. 수위/농도 정규화가 자동 역추정을 뜻하지 않습니다.
설비 resolved 출구를 원시 P/T로 덮어쓸 수 없고 provider가 새 경계를 생성해야 합니다.
위 API의 `pipeline`, `request`에 이어서 사용할 수 있습니다.

외부 설비 디지털 트윈을 실제 갱신 경계로 사용할 때는 `release_resolver`를
명시적으로 넘깁니다. resolver는 정규화된 센서 상태를 받아 이미 검증된
`ConsequenceRequest`를 반환해야 하며, 그 안에는 `ResolvedGasRelease`,
`ResolvedGasReleaseSet` 또는 `ResolvedLiquidRelease` 중 정확히 하나와 종료근거가
있어야 합니다. PRISM은 이 경계에서 누출 크기·지속시간·빈도·방출 프로파일을
추정하지 않습니다.

```python
from lh2_tno.service import ConsequenceService

def equipment_release_resolver(template, normalized):
    # 외부 lh2dt/공정 모델이 normalized를 사용해 계산하고,
    # provider_release adapter로 만든 ConsequenceRequest를 반환한다.
    return provider_request_from_equipment_model(template, normalized)

result = service.update_from_telemetry(
    request, normalized, pressure_tag="P", temperature_tag="T",
    release_resolver=equipment_release_resolver,
)
```

이 경로의 결과에는 `telemetry_boundary.equipment_release_resolved=true`가
남습니다. resolver가 일반 source 입력을 반환하거나, provider 경계를 넣지 않거나,
빈도를 함께 넣으면 즉시 거절됩니다. 따라서 센서 기반 빈도 학습과 알려지지 않은
누출 크기 역추정은 여전히 수행되지 않습니다.

```python
from lh2_tno.service import ConsequenceService
from lh2_tno.telemetry import Frame, TagMapping, TelemetryNormalizer

mappings = (
    TagMapping(tag="P", component_id="storage", quantity="pressure", source_unit="Pa",
               pressure_basis="absolute", sensor_location="tank"),
    TagMapping(tag="T", component_id="storage", quantity="temperature", source_unit="K",
               sensor_location="tank"),
)
normalizer = TelemetryNormalizer(mappings, maximum_age_s=2.0)
frame = Frame.model_validate_json('''{
  "stream_id":"demo", "sequence":1, "source_time_s":100.0, "arrival_time_s":100.1,
  "origin":"synthetic",
  "values":{"P":{"value":600000.0,"unit":"Pa","quality":"valid"},
            "T":{"value":20.893,"unit":"K","quality":"valid"}}
}''')
normalized = normalizer.normalize(frame, now_s=100.2)
service = ConsequenceService(pipeline, capacity=16)
result = service.update_from_telemetry(request, normalized, pressure_tag="P", temperature_tag="T")
```

frame 단위 deadline 장부가 필요하면 같은 서비스를 monitor로 감쌉니다.

```python
from lh2_tno.service import RealtimeConsequenceMonitor

monitor = RealtimeConsequenceMonitor(service, period_s=1.0, deadline_s=1.0)
result = monitor.update_from_frame(
    request, normalizer, frame, now_s=100.2,
    pressure_tag="P", temperature_tag="T",
)
print(result["realtime"]["deadline_status"])  # MET 또는 MISSED
```

시간은 동일 시계 기준이며 synthetic을 실측으로 표시하지 않습니다. 현재는 동기 API입니다.
`RealtimeConsequenceMonitor`를 사용하면 정규화된 frame마다 처리시간·입력자료 age·정확한 cache hit/fresh physics 여부·deadline 초과를 한 장부에 기록할 수 있습니다. deadline을 넘긴 결과는 오래된 결과로 조용히 대체하지 않고 `realtime.deadline_status=\"MISSED\"`로 남깁니다. 이 monitor는 빈도 학습·누출 크기 역추정·스케줄러를 제공하지 않으며, OPC-UA/MQTT 수집기·HTTP 서버·운영 화면과 비동기 스케줄러는 별도 개발해야 합니다.
이전 짧은 로컬 사례는 신규 기체 약 3초, 풀 약 7–10초, 동일 요청 캐시 약 20–40 ms였습니다.
모든 시설/PC의 성능을 보장하지 않으며 **캐시 응답속도가 신규 물리 계산 1 Hz를 뜻하지 않습니다.**

현재 native LH2 packet을 사용한 재현 benchmark [`native_lh2_realtime_cache_benchmark_v1.json`](examples/native_lh2_realtime_cache_benchmark_v1.json)은 fresh physics 약 `2685.50 ms`, exact-cache 20/20 hit, cache median `31.47 ms`, p95 `33.23 ms`를 기록했습니다. 따라서 이 실행에서는 동일한 정규화 요청의 cache 조회가 1 Hz deadline을 만족했지만, 상태가 바뀌어 fresh physics가 필요한 갱신은 1 Hz로 주장하지 않습니다. 재현 명령은 `scripts/benchmark_realtime_cache.py`이며, 결과에는 `realtime_fresh_physics_claim=false`가 고정됩니다.

여러 설비를 같은 시각에 확인해야 할 때는 `FacilityRealtimeConsequenceMonitor`를
사용합니다. 설비마다 `RealtimeConsequenceMonitor`, 센서 정규화기, 방출 resolver와
사고 템플릿을 하나씩 명시합니다. 입력은 `component_id`별 frame 묶음이어야 하며,
설비가 하나라도 빠지거나 잘못되거나 같은 `stream_id`를 공유하면 전체 묶음은
`status="REJECTED"`가 됩니다. 이때 정상적으로 계산된 설비 결과는 진단용으로
남지만 실패한 설비에 이전 결과나 0을 대신 넣지 않습니다.

```python
from lh2_tno.service import (
    FacilityRealtimeBinding,
    FacilityRealtimeConsequenceMonitor,
)

facility_monitor = FacilityRealtimeConsequenceMonitor({
    "storage-tank-01": FacilityRealtimeBinding(
        component_id="storage-tank-01", template=tank_template,
        monitor=tank_monitor, normalizer=tank_normalizer,
        pressure_tag="P_TANK", temperature_tag="T_TANK",
        release_resolver=tank_release_resolver,
    ),
    "transfer-pump-01": FacilityRealtimeBinding(
        component_id="transfer-pump-01", template=pump_template,
        monitor=pump_monitor, normalizer=pump_normalizer,
        pressure_tag="P_PUMP", temperature_tag="T_PUMP",
        release_resolver=pump_release_resolver,
    ),
})

snapshot = facility_monitor.update_from_frames({
    "storage-tank-01": tank_frame,
    "transfer-pump-01": pump_frame,
}, now_s=100.2)
print(snapshot["status"])                         # ACCEPTED 또는 REJECTED
print(snapshot["aggregate"]["deadline_status"])  # MET, MISSED 또는 REJECTED
```

문헌 빈도를 실시간 피해와 연결하려면 설비 binding에 별도로 붙입니다. 이 값은 센서에서 배우지 않고 검토된 문헌 사건에서 가져옵니다.

```python
from lh2_tno.service import RealtimeFrequencyBinding

frequency = RealtimeFrequencyBinding(
    event_id="storage-tank-hole-01",
    asset_id="storage-tank-01",
    initiating_frequency_per_year=1.0e-3,
    annual_condition_probability=0.5,
    release_branch_probability=0.8,
    occupancy_probability=0.25,
    provenance="published LH2 vessel frequency median",
    source_digest="a" * 64,
)
# FacilityRealtimeBinding(..., frequency_binding=frequency)
```

설비 빈도를 카탈로그에서 직접 만들었다면 수치를 다시 복사하지 않고
`from_frequency_event()`로 실시간 binding을 만들 수 있습니다. 이 함수는
패키지에 들어 있는 Purple/LH2 `FrequencyEvent`의 사건 ID·연간 빈도·문헌
SHA-256·p05/p95를 그대로 전달합니다. 가동조건·방출분기·재실 확률은
센서에서 추정하지 않으므로 호출자가 반드시 명시해야 합니다.

```python
from lh2_tno.frequency import generate_events

catalogue_event = generate_events(facility_manifest.to_facility(), frequency_plan)[0]
frequency = RealtimeFrequencyBinding.from_frequency_event(
    catalogue_event,
    annual_condition_probability=0.5,
    release_branch_probability=0.8,
    occupancy_probability=0.25,
)
# FacilityRealtimeBinding(..., frequency_binding=frequency)
```

따라서 실시간 경로는 내장 문헌 카탈로그 → 설비별 사건 binding → provider
방출·피해 결과로 이어지며, telemetry 값으로 개시빈도를 학습하지 않습니다.
카탈로그 사건이 실제 설비 개구·방출 branch와 정확히 맞지 않으면 binding하지
않고 해당 risk atom을 보류합니다.

provider 결과에 수용점 피해가 있으면 `snapshot["aggregate"]["current_weather_annual_ir_low_high"]`가 생성됩니다. 이는 현재 기상 조건의 진단값이며, `facility_annual_risk_available`와 전체 시설 F/N은 계속 `false`입니다.

수용점별 인구 장부까지 명시하려면 `FacilityRealtimeConsequenceMonitor`에 `RealtimePopulationBinding`을 전달합니다.

```python
from lh2_tno.service import RealtimePopulationBinding

population = RealtimePopulationBinding(
    persons_by_receptor={"worker-01": 10.0},
    provenance="declared outdoor worker population snapshot",
    source_digest="b" * 64,
)
facility_monitor = FacilityRealtimeConsequenceMonitor(
    bindings, population_binding=population
)
```

모든 설비가 같은 수용점 집합의 피해와 문헌 빈도를 갖는 경우에만
`snapshot["aggregate"]["conditional_current_weather_expected_death_fn_low_high"]`가 생성됩니다. 이 값은 명시된 인구와 현재 기상에 대한 조건부 expected-death F/N 기여이며, `facility_fn_available`과 `facility_annual_risk_available`은 여전히 `false`입니다. 인구 장부가 없거나 수용점 ID가 맞지 않으면 `WITHHELD`로 남습니다.

`snapshot["aggregate"]["component_risk_ranking"]`에는 같은 batch에서 현재 기상 IR이 계산된 설비의 진단용 우선순위가 기록됩니다. 높은 불확실성 끝점의 수용점 IR을 기준으로 정렬하며, 빈도 binding·frame·피해가 빠진 설비는 `rank=null`과 `[null, null]`로 보류합니다. 누락을 0으로 만들지 않고 빈도를 재분배하지 않으므로, 자세한 출력 계약과 예시는 [실시간 설비별 위험순위 개발기록](docs/PRISM_실시간_설비별_위험순위_개발기록_20261010.md)을 참고합니다.

같은 순위 장부에는 문헌 빈도 `p05`·`published`·`p95`를 적용한 설비별 peak IR과 순위도 선택적으로 기록됩니다. `frequency_sensitivity_rank_stable=true`이면 세 빈도 가정에서 순위가 유지된다는 뜻이고, 물리 피해를 다시 계산하거나 빈도를 학습했다는 뜻이 아닙니다. 범위가 없는 설비는 `null`로 보류됩니다.

각 accepted component에는 `equipment_release_path`도 기록됩니다. provider resolver가 반환한 사고 경계의 지속시간, 종료 basis, available/cumulative/remaining mass와 provider digest를 보존하며, 양단 방출은 shared inventory로 표시합니다. resolver가 없으면 `WITHHELD_PROVIDER_RELEASE_NOT_RESOLVED`로 남고 누출량 0으로 대체하지 않습니다. 자세한 계약은 [실시간 방출 경로 장부 개발기록](docs/PRISM_실시간_방출경로_장부_개발기록_20261010.md)을 참고합니다.

시설 `aggregate.equipment_release_path_accounting`은 accepted 설비별 종료
basis, 차단 상태, 재고 상태, 잔여 질량과 상태별 개수를 함께 보여줍니다.
설비 질량을 시설 총량으로 더하지 않으므로 양단 방출의 shared inventory가
중복 계산되지 않습니다. 방출 경로가 없는 설비나 실패한 설비는 `WITHHELD`로
남고, 누락된 방출을 0 kg 또는 정상 차단으로 바꾸지 않습니다.

실시간 snapshot을 기존 시설 위험 장부로 넘길 때는
`build_realtime_facility_risk_handoff(snapshot)`을 사용합니다. 이 함수는 원본
snapshot의 digest, 설비별 frame·provider 방출경로·현재 기상 IR·빈도 민감도·처리시간을
그대로 보존한 `prism.realtime_facility_risk_handoff.v1` 패킷을 만듭니다. 동시에
실시간 결과를 시설 연간 IR/F-N으로 승격하지 않도록 `mergeable=false`를 고정합니다.
실시간 risk atom에는 연간 기상 ID, 방출 branch ID, 점화 branch별 피해, 기대 사망수
폐합이 없기 때문입니다. 이 경계에서 PRISM은 ID를 임의로 만들거나 전체 피해를
점화 branch에 나누지 않습니다. 이후 별도 검토 캠페인이 branch별 consequence와
적격 provider·독립 물리검증 증거를 채운 경우에만 일반 시설 ledger를 새로 만들 수
있습니다.

```python
from lh2_tno.service import build_realtime_facility_risk_handoff

snapshot = facility_monitor.update_from_frames(frames, now_s=100.2)
handoff = build_realtime_facility_risk_handoff(snapshot)
assert handoff["facility_ledger_merge"]["mergeable"] is False
print(handoff["source_snapshot_digest"])
```

따라서 이 패킷은 디지털트윈 운영 화면과 후속 시설 캠페인의 입력 증거를 연결하는
표준화된 중간 결과이며, 빠진 사고·기상·점화 branch를 0으로 간주한 시설 위험도는
아닙니다.

실시간 snapshot을 **조건부 시설 ledger의 risk atom으로 연결**해야 할 때는 별도
어댑터를 사용합니다. `build_realtime_facility_campaign_result()`는 handoff가
보류한 네 가지 축(연간 기상 조건, 방출 branch, 점화 branch, branch별 피해)을
호출자가 명시한 경우에만 채웁니다. 센서 frame에서 이 값을 추정하지 않으며,
branch별 피해의 확률 가중합이 snapshot의 관측 누출 피해와 일치하지 않으면
즉시 `RealtimeCampaignBindingError`를 냅니다.

```python
from lh2_tno.realtime_campaign import build_realtime_facility_campaign_result
from lh2_tno.facility_ledger import merge_facility_campaign_results

campaign = build_realtime_facility_campaign_result(
    snapshot,
    annual_conditions=[{
        "id": "weather-D-west", "annual_probability": 1.0,
        "weather": {"wind_speed_m_s": 3.0, "stability_class": "D"},
        "population": [{
            "receptor_id": "worker-01", "persons": 10.0,
            "presence_probability": 1.0,
            "provenance": "reviewed outdoor population register",
        }],
        "provenance": "reviewed annual weather table",
    }],
    scenario_bindings=[{
        "component_id": "storage-tank-01",
        "event_id": "storage-tank-hole-01",
        "asset_id": "storage-tank-01",
        "annual_condition_id": "weather-D-west",
        "release_branch_id": "reviewed-isolation",
        "release_branch_probability": 1.0,
        "ignition_branch_probabilities": {
            "direct_fire": 0.25, "delayed_flash_fire": 0.35,
            "delayed_explosion": 0.10, "no_ignition": 0.30,
        },
        "branch_harm_low_high": {
            "worker-01": {
                "direct_fire": [0.20, 0.40],
                "delayed_flash_fire": [0.20, 0.40],
                "delayed_explosion": [0.20, 0.40],
                "no_ignition": [0.0, 0.0],
            }
        },
        "scenario_families": ["vessel_hole"],
    }],
    expected_component_ids=("storage-tank-01",),
)
ledger = merge_facility_campaign_results(
    [campaign], expected_component_ids=("storage-tank-01",)
)
```

이 결과는 `prism.realtime_facility_campaign_result.v1`이며 네 점화 branch마다
하나의 atom을 만듭니다. `conditional_diagnostic_facility_risk_available`는
`true`가 될 수 있지만 현재 snapshot은 `EXECUTED_OPERATOR_LIMITED`로 남고,
`facility_total_risk_available`, `qualified_facility_qra_available`,
`complete_facility_qra_claim`은 `false`입니다. 아직 계산하지 않은 설비나
방출경로가 있으면 전체를 0으로 채우지 않고 `UNCOMPUTED`/`MISSING_COVERAGE`로
보류합니다. 인구가 1명보다 크거나 재실확률이 있으면 adapter가
`expected_deaths_basis="population_weighted"`를 표시하고 시설 ledger가 그
조건의 인구 장부로 기대 사망수 폐합을 다시 확인합니다.

따라서 이 어댑터는 “실시간 결과를 시설 장부가 읽을 수 있는 조건부 기여로
전달하는 연결부”입니다. 연간 사고범위 전체, 적격 provider evidence,
독립 물리검증이 채워지기 전에는 IJHE용 완전 시설 QRA 결과로 해석하지 않습니다.

한 설비에 여러 연간 기상조건을 연결할 수도 있습니다. 이때 같은 사건 ID는
시설 ledger에서 하나의 event로 보존되고, 조건별 case와 risk atom만 늘어납니다.
현재 snapshot을 사용하는 조건은 `consequence_basis="realtime_snapshot"`으로
두며 설비마다 하나만 허용합니다. 다른 연간조건은
`consequence_basis="reviewed_annual_condition"`,
`observed_harm_low_high`, `consequence_provenance`를 함께 제공해야 합니다.
이 조건의 branch 피해는 현재 기상 피해를 복사하지 않고 별도 검토 결과로
폐합합니다. 여러 조건을 선언하면서 이 basis를 생략하면 어댑터가 중단됩니다.

표 형식 입력에서 provider resolver까지 연결하는 최소 경로는 `update_from_rows()` → `frame_from_row()` → `TelemetryNormalizer` → 설비 상태 → provider 방출 경계 → consequence 결과 → 시설 장부입니다. 이 경로는 `tests/test_consequence_service.py`의 `test_facility_realtime_monitor_row_batch_connects_state_to_provider_release_and_consequence`에서 상태 압력, provider 사고 ID, 방출시간, 종료 상태, 잔여 재고를 함께 검증합니다. 예시 provider가 합성이라면 이 테스트가 통과해도 qualified 실제 설비 packet이나 시설 연간 IR/F/N이 열리지는 않습니다.

행 배치에 각 설비의 `RealtimeFrequencyBinding`과 시설의 `RealtimePopulationBinding`을 함께 선언하면 같은 경로에서 설비별 현재 기상 IR을 합산하고, 수용점 인구를 곱한 조건부 expected-death F/N 기여와 p05/발표값/p95 빈도 재가중을 계산합니다. 이 값은 현재 배치의 조건부 진단 결과이며 `facility_annual_risk_available=false`, `facility_fn_available=false`를 유지합니다. 센서로 빈도를 학습하거나 누락 설비를 0으로 처리하지 않습니다.

provider consequence 결과에 네 가지 옥외 점화 branch(`direct_fire`, `delayed_flash_fire`, `delayed_explosion`, `no_ignition`)가 모두 있으면 `snapshot["aggregate"]["current_weather_ignition_accounting"]`에 설비별 branch 확률과 명시 문헌 빈도로 가중한 현재 조건 branch 발생률을 기록합니다. branch가 빠지거나 빈도 binding이 없으면 해당 행 또는 branch rate를 보류하며, 이를 시설 연간 IR/F-N으로 승격하지 않습니다.

`components`에는 설비별 frame/mapping digest, fresh physics 또는 exact cache,
처리시간, deadline, provider 방출 경계 여부가 보존되고 `aggregate`에는 설비 수,
실패 수와 deadline 요약이 기록됩니다. `FacilityRealtimeBinding`에
`RealtimeFrequencyBinding`을 넣으면 검토된 문헌 개시빈도·현재 기상확률·방출분기확률·재실확률을
센서와 분리된 입력으로 사용해, consequence 결과의 수용점 피해가 있는 경우
`current_weather_annual_ir_low_high`를 계산합니다. 빈도 binding에는 사건 ID·자산 ID·출처 문구·SHA-256이
필수이며 센서값으로 바뀌지 않습니다. 수용점 피해가 없거나 한 설비라도 빈도 binding이 없으면
현재 기상 IR은 `WITHHELD`로 남깁니다. 이 조정기는 센서 기반 빈도 학습이나 누출 크기 역추정을
수행하지 않고, F/N과 시설 전체 연간 IR은 여전히 `facility_annual_risk_available=false`로 보류합니다.
문헌 p05/p95가 있으면 같은 피해 결과를 재실행하지 않고 `current_weather_frequency_sensitivity_ir_low_high`에 세 빈도 경계의 재가중 결과를 함께 기록하며, published 값이 p05와 p95 사이에 있지 않으면 입력을 거절합니다.
시설 IR/F-N은 별도의 문헌 빈도·사고범위·물리검증·시설 장부 gate를 통과한 campaign에서만 계산됩니다. 인구 장부를 추가해도 센서 기반 빈도 학습, 누출 크기 역추정, 전체 시설 위험 승격은 수행하지 않습니다.

`aggregate.processing_time`에는 accepted 설비의 `service_elapsed_ms`와
`physics_run_elapsed_ms`를 설비별로 남기고, 배치 합계·평균·최대값을 기록합니다.
이는 한 번의 동기 배치 처리시간을 보여주는 운영 장부이며, 지속 처리량이나
새로운 물리계산의 1 Hz 달성 증거로 해석하지 않습니다. 설비가 거절되거나 시간
측정값이 없으면 해당 행은 `WITHHELD` 또는 `PARTIAL`로 남습니다.

## 출력 해석

`--output` 파일에 전체 결과를 저장합니다. 콘솔의 짧은 status만으로 피해를 판정하지 않습니다.

| 필드 | 뜻 |
|---|---|
| `data.status=END_TO_END_DIAGNOSTIC_EXECUTED` | 지원 가정에서 전체 경로 실행 완료 |
| `physical_validation_claim=false`, `facility_validation=WITHHELD` | 물리/시설 검증 완료 주장 보류 |
| `data.mass_ledger` | 방출·기체·풀·잔류·영역 이탈 질량 장부 |
| `data.explosion.domain_truncated` | 영역 밖 질량으로 폭발 평가가 잘렸는지 |
| `data.receptors` | 지점별 농도, 열유속/용량, 압력 구역과 피해 |
| `harm_given_observed_release_low_high` | 이미 누출이 발생한 조건의 점화 반영 피해 |
| `annual_current_weather_contribution_low_high` | 단일 사건 현재 기상 연간 기여, 빈도 결측은 null |
| `first_initiation_harm_probability_low_high` | 아직 미발생 사건의 시간 내 첫 발생·피해, initiation 결측은 null |
| `elapsed_ms`, `stage_elapsed_ms` | 전체 backend와 단계 실행시간 |
| `service.exact_cache_hit` / `fresh_physics_this_update` | 서비스 캐시와 새 계산 구별 |
| digest / `environment` | 입력·모델 소스·설정·의존성 출처 |

지점별 필드는 `data.receptors` 안에 있습니다. low/high는 주로 지정한 복사율 범위 결과이며 통합 95% 신뢰구간이 아닙니다.
질량 폐합은 전체 에너지 폐합 증명과 다릅니다.
단일 사건 현재 기상 연간 기여는 개념적으로 `빈도 × 사건조건부 피해 × 재실확률`입니다.
전체 연간 IR에는 모든 기인 사건·점화/차단·연간 기상 분포가 필요합니다.
[risk.py](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/risk.py)의 합산 산술은 기상 합·중복·결측을 검사하지만 전체 시나리오 자동 계산기는 아닙니다.
F-N에는 인구 분포와 같은 사건의 피해자수 정의도 필요합니다. LH2 한 요청 결과를 시설 IR/F-N으로 표시하지 않습니다.

## 검증과 후속 개발

```powershell
.venv\Scripts\python.exe -m pytest -q lh2-tno/tests -c lh2-tno/pyproject.toml
.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation ./lh2-tno -w wheelhouse
```

### 물리 검증 근거의 범위

외부 DynamicLH2PoolX Stage-C 자료는 지면에 도달한 유입의 축대칭 풀 증발·확산 구성요소를 hold-out 자료로 제한 검증합니다. 물 Trial 4 반경 RMSE는 `0.1374 m`, 알루미늄 Trial 6은 `0.1016 m`, 두 영상 구간 포함률은 `1.0`, HSE Test 6 질량 잔차는 `8.24e-13 kg`입니다. PRISM은 이 자료의 원자료 목록과 모델·manifest 해시를 [물리 검증 근거 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_물리검증_근거_20261009.md)으로 보관합니다.

현재 외부 snapshot의 `dynamic_validation_protocol.json` 선언 해시가 evidence JSON과 달라 상태를 `DECLARED_EVIDENCE_WITH_SOURCE_HASH_DRIFT`로 기록했습니다. 엄격 검증은 중단하고, 감사 모드만 지표와 불일치 파일을 보존합니다. 이 구성요소 증거는 설비 방출·대기 확산·점화·IR/F-N 전체 체인의 물리 검증이나 현장 절대위험 검증을 의미하지 않습니다.

공개 v0.6.0은 단위·계약·보존·모드 검사 154개로 고정되어 있고, 현재 0.6.2 개발 소스는 LayeredTank 경계 감사·유량 gate·endpoint enthalpy·액체 빈도 binding·일반 설비 매니페스트 계약·CLI 승격·빈도 범위 감사·외부 provider evidence audit·센터 시나리오 증거 감사·주요 사고 범위 매트릭스·양단 provider release-set adapter·설비 모델 결합 감사 검사를 포함해 **384개**를 통과합니다. 별도 실행 진단은 steady 설비 경계와 5개 transient LH2 pipe LOC의 성공·실패 분기 20건, 다섯 area-bin 양수 재고 종료 경로의 두 기상 조건 10건, LayeredTank의 문헌 `LH2_VESSEL` 정확 개구 1개와 두 기상 조건의 시설 campaign을 통과시켰습니다. 어느 숫자도 독립 실험 검증을 대신하지 않습니다.
GitHub Actions에서 portable 검사와 wheel catalogue/명령 포함을 확인합니다.
새 안내의 도움말·시설·빈도 예제도 깨끗한 소스 export에서 확인합니다.
`validate_*.py`는 개발 PC 경로와 이전 결과를 참조할 수 있어 클론 직후의 일반 사용 명령이 아닙니다.
v0.5 모드 검증의 설비 경계는 v0.4 기록 재생이며 최신 live provider를 재실행한 결과가 아닙니다.

우선 개발 항목:

1. 전체 시설 LH2 사건/source/종료·위치 배분, 점화·차단·기상과 IR/F-N 결합.
2. LayeredTank PH nozzle/flash와 액체·2상 재고 feedback, airborne droplet adapter, provider handoff 없는 수직·팽창/high-Mach 출구 확장과 handoff 물리검증.
3. 양수 재고 종료 경계를 실제 탱크·배관·밸브·펌프 조건과 액체/2상 flash, actuator 지연·실패 분기로 확장하고 전량 방출·양단 교차상호작용·실제 수직 jet을 별도 사건으로 검증.
4. 방출·풀·확산·화재/폭발 독립 검증과 관측 연산자.
5. 프로파일 적용 민감도·상관을 반영한 전체 위험 불확실성.
6. 신규 계산 가속, 검증된 surrogate/사전 계산, 비동기 요청·유효시간 정책.

IJHE 연구는 설비 경계·질량/시간 일관성·문헌 빈도·조건부 피해의 연결과 검증 범위를 명시합니다.
현장 빈도 학습/1 Hz 완료를 선행 주장하지 않습니다. [IJHE 프로토콜](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/IJHE_연구프로토콜.md).

## 문제 해결과 개발 기록

| 문제 | 확인 사항 |
|---|---|
| 명령 못 찾음 | 설치한 가상환경 실행 파일 또는 그 Python의 prism.py 사용 |
| backend 요구 | 기존 엔진/외부 모델 경로·해시·interpreter 설정 |
| source revision mismatch | 실제 소스 변경 검토·검증 후 pin 갱신 |
| import/version mismatch | 패키지 디렉터리·runtime·버전 확인 |
| event-id 오류 | 계획+피해 요청에는 실제 일치 사건 ID 필수 |
| 물리 범위 중복 | 같은 실물의 대체 빈도를 중복 합산하지 않음 |
| PH/유량/시계/질량 오류 | 단위·엔탈피·경계·명령/종료 시간·누적 장부 대조 |
| stale/duplicate/unknown tag | 시계·나이·품질·매핑 확인 |
| deadline exceeded | 원인/격자/환경 검토, 오래된 결과로 자동 대체하지 않음 |
| null/WITHHELD | 결측·미검증 표시이며 0/안전 판정이 아님 |

- [현재 상태 JSON](https://github.com/lyullee/prism/blob/main/lh2-tno/CURRENT_STATUS.json)
- [구조와 저장소 관리](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/모듈구조와_GitHub_관리.md)
- [PRISM v0.6.0 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_v060_명칭과사용안내_20261008.md)
- [기존 기능 66개 목록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_위험성평가_구축기능_상세목록_20261008.md)
- [전체 연결](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/방출부터_최종피해_연결완료_20261008.md)
- [빈도 v0.3](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md)
- [설비 경계 v0.4](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md)
- [모드 v0.5](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md)

이전 문서의 TNO-LH2 명칭·로컬 경로는 당시 기록입니다. 제품과 새 저장소 이름은 PRISM이고 이전 Git 이력은 보존합니다.
외부 소스·책·원계측 자료·로컬 원고는 이 저장소에 포함하지 않습니다.

## 배포와 인용

- [PRISM 0.6.2 PyPI·DOI 배포 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_v062_PyPI_DOI_배포기록_20261009.md) / [이전 0.6.0 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_v060_PyPI_DOI_배포완료_20261008.md)
- Python 배포명: **prism-risk**, 버전 **0.6.2**, 라이선스 **MIT**.
- [PyPI 프로젝트](https://pypi.org/project/prism-risk/0.6.2/) / [Zenodo v0.6.2 DOI](https://doi.org/10.5281/zenodo.23246944).
- 버전 고정 인용은 **10.5281/zenodo.23246944**, 전체 버전 인용은 [10.5281/zenodo.23241358](https://doi.org/10.5281/zenodo.23241358)입니다.
- [CITATION.cff](https://github.com/lyullee/prism/blob/main/CITATION.cff)에 소프트웨어 인용 정보를 보관합니다.
- DOI는 소프트웨어 버전 기록이며 IJHE 논문 DOI나 물리 검증 인증이 아닙니다.
- v0.6.2의 PyPI 공개 배포와 DOI 발행·연결 확인을 완료했습니다. 등록 상태와 commit/workflow 영수증은 `CURRENT_STATUS.json`과 [배포 기록](docs/PRISM_v062_PyPI_DOI_배포기록_20261009.md)에 보관합니다.

```powershell
python -m pip install prism-risk==0.6.2
prism --describe-modes
```

외부 모델 없이 시설 검증과 문헌 빈도 생성이 가능합니다. source/확산/피해 물리 계산은 별도 검토된 provider가 필요합니다.
MIT는 PRISM 자체 배포 파일에 적용하며 외부 모델과 원자료의 라이선스·재배포 권한을 변경하지 않습니다.

## 시설 IR/F-N 연결 결과 읽기

공식 혼합 LH2 재실행부터 시설 원장은 두 층의 결과를 저장합니다. `conditional_diagnostic_facility_annual_ir_low_high`와 `conditional_diagnostic_facility_expected_death_fn_low_high`는 실제로 만들어진 risk atom을 시설 수준에서 합한 **조건부 진단용 IR/F-N**입니다. 이 값으로 방출→확산→점화→화재·폭발→수용점 피해가 시설 원장까지 연결됐는지 확인하고, 문헌 빈도 p05/중앙/p95 시나리오를 다시 적용할 수 있습니다.

F/N 배열이 비어 있어도 계산 누락으로 해석하지 않습니다. `conditional_diagnostic_facility_expected_death_fn_diagnostics.status`가 `ZERO_EXPECTED_DEATH_AT_DECLARED_RECEPTORS`이면 risk atom과 IR은 계산됐지만 현재 수용점에서 기대 사망자 수가 0이고, `SUB_ONE_EXPECTED_DEATH_LEVEL_ONLY`이면 0보다 크지만 N=1 기준에 도달하지 않은 상태입니다. `CURVE_AVAILABLE`일 때만 N≥1 곡선의 점이 들어갑니다. 이 구분으로 20 m 수용점의 0 피해와 near-receptor 연결 검증을 같은 시설 원장 안에서 혼동하지 않습니다.

near-receptor F/N 연결 검증은 `scripts/build_near_receptor_facility_assessment_summary.py`로 재현할 수 있습니다. 저장된 한 사건을 원장에 다시 합치는 작업이며 물리 계산을 재실행하지 않습니다. 출력 예시는 [`native_lh2_near_receptor_facility_assessment_summary.json`](examples/native_lh2_near_receptor_facility_assessment_summary.json)에서 확인합니다.

시설 원장은 이제 risk atom과 함께 annual condition의 기상·인구 행도 보존하고 `population_accounting`으로 수용점 집합, 인구 행 수, provenance를 검사합니다. 설비 campaign을 시설 namespace로 합칠 때 수용점을 여러 개에서 하나로 접는 경우에는 population도 자동으로 적격화하지 않고 `RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC`으로 남깁니다. 최신 generic+vertical 진단은 [`native_generic_scope_vertical_population_binding_summary.json`](examples/native_generic_scope_vertical_population_binding_summary.json)에서 확인할 수 있습니다.

추가로 시설 원장은 이제 `scenario_branch_accounting`을 보존합니다. `annual_conditions`의 기상·연간 확률, `release_branches`의 방출·차단·종료 근거, `ignition_branches`의 점화 결과와 실제 risk atom 수를 같은 원자 집합에서 확인할 수 있습니다. 각 분기에는 저장된 `개시빈도 × 조건부 가중치` 합도 있어 기상·차단·점화 확률이 실제 계산에 적용됐는지 확인할 수 있습니다. `cross_product_count`는 실제로 계산된 조건×방출×점화 조합 수이며, 이 장부는 빈도를 추정하거나 branch를 재배분하지 않습니다. 이전 저장 ledger에도 진단 장부를 재구성할 수 있으며, 자세한 규칙은 [시설 분기·기상·종료·점화 장부 개발 기록](docs/PRISM_시설분기_기상_종료_점화_장부_개발기록_20261024.md)에 있습니다.

최신 29-event·34-case·136-risk-atom 병합 결과의 compact 추적성 증거는 [`native_generic_scope_vertical_branch_release_accounting_summary.json`](examples/native_generic_scope_vertical_branch_release_accounting_summary.json)입니다. 이 파일은 기상조건 3개, 분기 조합 12개, provider 종료근거와 질량 장부 요약을 보존하며, `facility_total_risk_available=false`와 `DIAGNOSTIC_ONLY`를 함께 기록합니다.

같은 원장에 문헌 빈도 민감도 5개를 다시 적용한 branch 장부는 [`native_generic_scope_vertical_frequency_branch_accounting_summary.json`](examples/native_generic_scope_vertical_frequency_branch_accounting_summary.json)입니다. 다섯 시나리오 모두 같은 12개 조건×방출×점화 조합을 유지하고 branch별 가중 빈도만 바꾸며, `facility_credible_interval=false`를 유지합니다.

시설 원장의 `timing.stage_elapsed_ms`에는 case에 실제로 기록된 단계별 경과시간의 건수·합계·중앙값·최댓값·p95·p99가 들어갑니다. 이는 provider 방출과 SLABx/피해 단계의 처리시간을 분리해 보는 근거이며, 반복 실행 처리량이나 신규 물리 1 Hz 성능을 의미하지 않습니다.

`facility_total_risk_available`와 `total_facility_annual_ir_low_high`는 검증용 결과입니다. 예상 설비·사고가 모두 실행되고 미계산 사건, 합성 종료시계, 연산자 제한, 실제 형상 미확정, 물리검증 부족이 해소될 때만 채워집니다. 현재 공식 결과는 진단용 IR/F-N은 계산되지만 검증용 시설 총위험도는 `null`입니다. 이는 계산을 버린 것이 아니라, 부분 계산을 전체 시설 위험도로 잘못 표시하지 않도록 한 승격 경계입니다. 사건 수, risk atom 수, 연산자 제한 수, 차단 이유는 `conditional_diagnostic_facility_coverage`에서 확인할 수 있습니다.

사고 가족별 범위도 같은 평가에 연결됩니다. `results/20261014/generic_mixed_accident_scope_matrix_refined_pool.json`은 현재 혼합 캠페인의 12개 주요 사고 가족을 `EXECUTED` 4개, `PARTIAL` 7개, `NO_EVENT_GENERATED` 1개로 기록합니다. 이 표는 사고 빈도를 합산하는 표가 아니라, 어떤 사고가 계산됐고 어떤 사고가 빠졌는지를 시설 총위험도 승격 전에 확인하는 장부입니다.

사고 family의 설비 적용범위와 필요한 provider 방출·종료 계약은 [LH2 사고 시나리오 카탈로그](docs/PRISM_LH2_사고시나리오_카탈로그_20261017.md)와 `src/lh2_tno/accident_scenario_catalog.py`에 고정되어 있습니다. `scripts/export_accident_scenario_catalog.py`는 12개 야외 주요사고 family를 manifest의 설비 ID와 함께 JSON으로 내보냅니다. 이 카탈로그는 누출 packet이나 빈도를 만들어 내지 않으며, packet이 없거나 종료 장부가 부족하면 해당 family를 `UNCOMPUTED` 또는 `NO_EVENT_GENERATED`로 남깁니다. 최신 개발 소스는 **445개 portable 검사**를 통과했지만, 현재 외부 provider 적격 사고 packet은 0건이고 시설 전체 IR/F-N은 계속 보류됩니다.

provider worklist의 각 event에는 `scenario_families`가 함께 기록됩니다. 따라서 저장탱크 구멍이 `vessel_hole`과 `liquid_two_phase`에 걸리는 것처럼 설비 family와 상변화·재고 사고를 명시적으로 추적할 수 있습니다. 이 필드는 빈도를 재배분하지 않고, 필요한 provider packet이 없을 때 미계산 상태를 유지하기 위한 연결표입니다.

`build_accident_scope_matrix.py --provider-worklist`를 사용하면 이 worklist와 campaign의 event ID·주 사고 family가 같은지 검사합니다. 구조가 `ALIGNED`여도 provider packet이 없으면 계산을 시작하지 않으며, 최신 generic 24-event 진단도 이 원칙에 따라 packet 0건·시설 QRA 보류로 기록됩니다.

범위표는 매니페스트에 해당 설비 종류가 실제로 없을 때 그 사고 family를
`NOT_APPLICABLE`로 기록합니다. 예를 들어 펌프가 없는 저장·이송 시설에서는
`pump_hole`을 누락 사고로 세지 않습니다. 설비가 존재하는데 사건이 생성되지
않았거나 계산되지 않은 경우에는 계속 `NO_EVENT_GENERATED`, `PARTIAL`,
`UNCOMPUTED`로 남아 시설 완결성을 막습니다. `manifest_scenario_component_ids`와
각 행의 `applicability`로 이 구분을 확인할 수 있습니다.

여러 campaign의 범위표를 `scope_matrix_merge`로 합칠 때도 모든 입력 행이
`NOT_APPLICABLE`이면 그 상태를 유지하고, 다른 campaign에서 실제 사건이 실행되면
그 실행 상태를 우선합니다. 비적용 설비를 누락으로 세지 않으면서 실제 설비의
미계산 사고는 계속 시설 blocker로 남습니다.

실행된 risk atom에는 사고 family가 함께 남고, facility ledger의 `scenario_family_contributions`에서 탱크·배관 사고와 액체 2상·재고 사고의 기여를 따로 조회할 수 있습니다. 이 표는 같은 atom을 family별로 분류한 결과이므로 family별 수치를 서로 더하지 않습니다.

campaign 결과의 `release_termination_inventory_ledger`에는 사건×차단 분기×연간 조건별로 provider packet digest, 방출 지속시간, 종료근거, provider 재고·누적 방출량·잔여량, 차단 선언을 한 행에 기록합니다. `UNCOMPUTED`와 `EXECUTED_OPERATOR_LIMITED`는 각각 누락·제한 상태로 남으며, 질량이 0이 되었다는 이유만으로 재고소진이나 차단 성공을 추론하지 않습니다. 최신 결과는 `results/20261018/generic_mixed_provider_campaign_release_ledger.json`이고, 24행 중 5행은 operator-limited, 14행은 실패, 5행은 미계산이며 시설 전체 IR/F-N은 계속 보류됩니다.

문헌 빈도 민감도 결과에도 family별 known expected-fatality 기여와 순위 안정성이 기록됩니다. 최신 5개 빈도 시나리오 결과는 `results/20261017/frequency_uncertainty_family_atoms.json`에 있으며, 물리 재계산 없이 빈도만 재가중한 조건부 진단 결과입니다.
# 압축성 기체 근접장 handoff (2026-10-16)

고속 기체 출구는 출구 압력·속도만으로 PRISM이 팽창과 충격파를 다시 만들지 않습니다. 외부 provider가 `prism.compressible_plane_handoff.v1`로 downstream plane의 위치, 혼합상태, 단면, 시간별 상태를 내보내고 원 packet의 source/result digest를 지정해야 합니다. `scripts/attach_compressible_plane_handoff.py`가 이 handoff를 `ResolvedGasRelease`에 붙이면서 각 interval의 `rho × u × A × H2 fraction` 질량 장부와 식별자를 다시 검사합니다. `src/lh2_tno/chain_worker.py`는 공급자가 선언한 plane에서만 SLABx를 시작합니다.

현재 선택된 `ambient-vaporizer/G1`은 고속인데 provider handoff가 없어 `COMPRESSIBLE_PLANE_HANDOFF_BLOCKED`로 남아 있습니다. 저마하 참고 packet을 고속 사건에 대체하지 않으며, 합성 handoff smoke도 실제 provider·물리검증·시설 QRA 증거로 승격하지 않습니다. 계약과 필요한 입력은 [압축성 근접장 handoff 기록](docs/PRISM_압축성근접장_handoff_계약_20261016.md)에 정리했습니다.

2026-10-17에는 같은 G1 사건을 외부 `lh2dt.DynamicVaporizer` source/throat state가 포함된 별도 packet으로 재실행했습니다. 1 MPa source, 11개 provider interval, `max Mach=3.9982`의 `prism.compressible_plane_handoff.v1`을 exact digest로 붙여 `SLABx-LH2/SLABx → 점화·화재/폭발 → 수용점 피해`까지 소비했고, G1은 `EXECUTED_OPERATOR_LIMITED`가 되었습니다. 이 결과는 이전 공식 결과를 대체하지 않는 `source_state_rebound` 진단이며 provider 자격·고속 근접장 독립검증·시설 IR/F-N 승격은 보류합니다. 24개 사건 전체 재실행은 `4 EXECUTED + 20 EXECUTED_OPERATOR_LIMITED + 0 FAILED`였고, 빈도 coverage는 `0.8040`이지만 전체 시설 위험도는 `null`입니다. 자세한 digest·시간·제한은 [G1 source-state 시설 캠페인 기록](docs/PRISM_source_state_G1_시설캠페인_개발기록_20261017.md)에 있습니다.

혼합 설비 빈도 캠페인에서 공개 p05/p95 근거가 없는 펌프·기화기·PSV·재액화기 사건은 임의 분포를 만들지 않고 `fixed`로 선언된 catalogue 빈도를 유지합니다. 문헌 경계가 있는 저장탱크·배관·밸브만 p05/published/p95를 재가중하고 shared-asset와 independent-event 시나리오를 비교합니다. `fixed` 선택지를 벗어난 빈도 추정이나 센서 기반 빈도 학습은 하지 않습니다.

로그정규 `mu/sigma` 표본화도 같은 원칙을 적용합니다. 기본은 분포가 없는 사건을 거부하고, 혼합 시설 캠페인에서는 `fixed_event_policy=hold_published`를 명시해야 해당 사건의 catalogue 빈도를 고정한 채 shared-asset/independent-event 표본을 계산합니다. 결과는 빈도 모델 기반 known-contribution 구간이며 전체 시설 credible interval이 아닙니다.

재현 명령은 `scripts/compute_frequency_distribution_uncertainty.py`이며, `--draws`와 `--seed`를 장부에 남깁니다. 이 명령도 물리 재실행이나 센서 기반 빈도 학습을 하지 않습니다.

### 배관 native 2상 연결 예제

`scripts/run_lh2dt_native_dynamic_pipe_frequency_case.py`는 외부 `DynamicHEMPipe`의 액체·2상 초기 품질, 대기 flash, 기체·지상 액체 질량, 종료시계와 잔차를 반환받고 `LH2_PIPE AREA_0.01%` 문헌 빈도를 적용해 consequence chain을 실행한다. 실행 요약은 `examples/native_lh2dt_dynamic_pipe_frequency_case_verification.json`에 있다. 결과는 `PARTIAL_DECLARED_SCOPE`이며 다른 opening bin·설비는 명시적으로 미계산/제외되고, airborne liquid·시설 총 IR/F-N·qualified packet은 보류된다.

### 네이티브 LH2DT 패킷 장부

설비별 외부 모델 출력의 방출시간·종료근거·질량잔차·피해체인 연결 여부는 [`examples/native_lh2dt_packet_coverage_ledger.json`](examples/native_lh2dt_packet_coverage_ledger.json)에 모아져 있다. 다음 명령으로 현재 결과를 다시 만들 수 있다.

```powershell
$py = (Get-Item '../output/prism-export-v060-1febujhk/venv/Scripts/python.exe').FullName
& $py scripts/build_native_lh2dt_packet_coverage_ledger.py `
  --provider-worklist results/20261017/provider_worklist_with_scenario_families.json `
  --output examples/native_lh2dt_packet_coverage_ledger.json
```

현재 장부는 네이티브 패킷 25건, 작업목록 exact-match 24건, consequence-chain 연결 18건을 기록한다. 장부는 `diagnostic_only`이며 provider 승격·빈도 추론·시설 IR/F-N·물리검증을 열지 않는다. 읽는 법과 사고군별 표는 [네이티브 LH2DT 사고 패킷 장부](docs/PRISM_네이티브_LH2DT_사고패킷_장부_20261018.md)를 참조한다.

저장된 네이티브 packet을 실제 시설 campaign 요청에 다시 넣은 결과도 별도 감사한다. `examples/native_lh2dt_packet_campaign_execution_ledger.json`은 24개 event와 24개 case에서 packet identity·source/result digest를 모두 보존했고, 23개 case가 체인까지 실행됐음을 기록한다. 19개는 `EXECUTED_OPERATOR_LIMITED`, `ambient-vaporizer/G1`은 압축성 plane handoff 부재로 명시적 `FAILED`다. 이 실패를 다른 방출모델로 대체하지 않으며 시설 전체 IR/F-N은 계속 보류한다. 자세한 실행·재현 명령은 [네이티브 packet 시설 campaign 감사](docs/PRISM_네이티브패킷_시설캠페인_감사_20261019.md)에 있다.

방출값이 실제 시설 case 장부에 소비됐는지는 별도 값 감사로 확인한다. `scripts/audit_diagnostic_campaign_binding.py`는 저장 packet의 `duration_s`, 종료 basis/provenance, available mass, cumulative release mass를 case의 `termination`·`mass_ledger`와 endpoint digest 순서로 대조한다. 2026-10-24 generic 전체범위에서는 24/24 packet event가 값 일치(`packet_subset_value_consumed=true`)였고, 시간 단계 전체를 독립 재생했다는 주장은 하지 않는다. 수직 handoff 5개 event는 packet subset 밖에 있으므로 전체 campaign packet 소비로 확대하지 않는다. 결과는 [`방출 집계값 소비 감사 기록`](docs/PRISM_방출집계값_시설ledger_소비감사_20261024.md)과 [`binding v5`](results/20261024/native_generic_scope_vertical_diagnostic_campaign_binding_v5.json)에서 확인하며, 적격 provider·물리검증·시설 IR/F-N gate는 계속 별도 보류한다.

방출부터 최종 피해까지의 마지막 연결은 `scripts/audit_facility_chain_closure.py`로 별도 재계산한다. 2026-10-24 기록은 24개 packet event가 종료·재고 case, 피해 원자, 조건부 시설 IR/F-N 합계까지 폐쇄되었음을 확인하고, packet 밖 수직 handoff 5개는 `HANDOFF_OR_PACKET_MISSING`으로 보존한다. 이는 진단 chain closure 증거이며 qualified provider, 독립 전체 체인 물리검증 또는 시설 QRA 승격을 의미하지 않는다. 상세 결과는 [`방출→최종피해 체인 폐쇄 감사`](docs/PRISM_방출_최종피해_체인폐쇄감사_20261024.md)와 [`chain closure v1`](results/20261024/native_generic_scope_vertical_chain_closure_v1.json)에서 확인한다.

G1 고속 출구는 이후 `scripts/rebind_campaign_to_compressible_handoff.py`로 별도 source/throat 기반 handoff를 명시적으로 재결합했다. event/component/port/source digest가 맞을 때만 같은 campaign 요청에 붙였고, provider result digest 변경과 `not independently validated` provenance를 별도 기록했다. 최종 네이티브 packet campaign은 **24/24 chain 실행, 20건 `EXECUTED_OPERATOR_LIMITED`, 0건 실패, 96 risk atom**으로 끝났지만 시설 전체 IR/F-N은 계속 `null`이다. 최신 장부는 [`examples/native_lh2dt_packet_campaign_execution_ledger_g1_handoff.json`](examples/native_lh2dt_packet_campaign_execution_ledger_g1_handoff.json), 최신 IJHE 감사는 `results/20261019/ijhe_completion_audit_with_native_packet_campaign_g1_handoff.json`이다. 이 handoff는 계산 경계를 연결한 진단 증거이며 provider 적격성·고속 근접장 물리검증·시설 QRA를 의미하지 않는다.

최종 campaign 결과는 시설 ledger로도 재집계했다. 24개 사건과 96개 risk atom에 문헌 빈도 5개 시나리오를 적용한 조건부 진단 결과를 [`examples/native_lh2dt_packet_campaign_facility_assessment_summary.json`](examples/native_lh2dt_packet_campaign_facility_assessment_summary.json)에 보관했다. 20개 운전자 제한과 1개 domain-incomplete 상태가 남아 `facility_total_risk_available=false`이며, 조건부 합산을 자격 있는 시설 IR/F-N으로 표현하지 않는다.

### 별도 vertical handoff 결과의 시설 결합

수직 벤트 모델이 별도 campaign으로 생성한 결과도 `src/lh2_tno/vertical_handoff_campaign.py`를 통해 공통 시설 namespace로 결합할 수 있습니다. 이 과정은 시설 ID, event/provider packet ID, 설비·component ID를 함께 재작성하고, 서로 다른 수용점은 사용자가 지정한 매핑으로만 결합합니다. 현재 예시는 네 수용점을 `worker-01`로 매핑하고 여러 값이 겹치면 endpoint maximum을 취합니다. 이는 진단용 비교 규칙이며 실제 시설 좌표·인구를 대체하지 않습니다.

결합 시설 장부는 generic v12와 vertical all-bin 진단을 합쳐 29개 event, 34개 case, 136개 risk atom을 기록하고, vertical handoff를 `PARTIAL`로 추적합니다. 모든 case가 조건부 consequence chain에는 도달했지만 strict 승격용 operator-limited·domain-incomplete 표지가 남으므로 시설 전체 위험도는 계속 `null`입니다. 병합 장부는 [`native_generic_scope_vertical_merged_facility_ledger_repaired_v1.json`](results/20261023/native_generic_scope_vertical_merged_facility_ledger_repaired_v1.json), 범위표는 [`native_generic_scope_vertical_merged_scope_matrix_v1.json`](results/20261023/native_generic_scope_vertical_merged_scope_matrix_v1.json), 결합 요약은 [`native_generic_scope_vertical_merged_ledger_consistency_v1.json`](results/20261023/native_generic_scope_vertical_merged_ledger_consistency_v1.json)입니다. synthetic handoff·operator-limited physics·부분 사고군·물리검증 부족은 그대로 표시되며 provider 승격이나 빈도 추론은 하지 않습니다.

### Two-sided rupture와 시설 사고범위 통합

별도 두 종단 rupture campaign도 `scripts/rebind_campaign_namespace.py`로 공통 시설 ID 아래에 결합했습니다. event·asset·component·receptor 매핑은 provenance에 남고, `near_worker` 등은 `worker-01`로 명시적으로 축약됩니다. 이 결과는 2개 event와 16개 risk atom을 추가하며, 비영 near-worker harm 때문에 조건부 진단 IR/F-N이 표시됩니다. 최신 시설 평가는 31개 event, 40개 case, 120개 risk atom이고, 요약은 [`native_lh2dt_packet_campaign_vertical_handoff_two_sided_facility_assessment_summary.json`](examples/native_lh2dt_packet_campaign_vertical_handoff_two_sided_facility_assessment_summary.json)입니다.

`scope_matrix_merge.py`는 generic·vertical·two-sided matrix를 family별로 합쳐 `results/20261019/generic_vertical_two_sided_merged_scope_matrix.json`에 보관합니다. 부분 또는 미계산 family를 `EXECUTED`로 바꾸지 않으므로 `vertical_handoff`와 `two_sided_rupture`의 `PARTIAL` 상태가 시설 감사에 그대로 보입니다. two-sided 결과에는 endpoint별 harm과 Frechet 교집합 범위를 기록하는 `two_sided_interaction_diagnostic`이 추가됐지만 공동 plume·압력 feedback을 계산한 것은 아닙니다. 합성 geometry·인구·provider handoff 검증은 남은 제한이며, 시설 전체 IR/F-N은 계속 `null`입니다.

### Inventory depletion을 포함한 공통 시설 평가

독립적으로 실행한 재고 소진 진단도 공통 시설 평가에 결합할 수 있습니다. `scripts/rebind_campaign_namespace.py`로 `inventory-depletion-pipe-01`을 별도 namespace에 넣고, 기존 transfer-line 사건과 중복 합산하지 않습니다. provider가 선언한 positive-mass depletion threshold와 종료시간은 case별로 보존됩니다.

최신 네 campaign 결합 결과는 [`native_lh2dt_packet_campaign_vertical_handoff_two_sided_inventory_facility_assessment_summary.json`](examples/native_lh2dt_packet_campaign_vertical_handoff_two_sided_inventory_facility_assessment_summary.json)에 있습니다. 36개 event, 50개 case, 160개 risk atom, 10개 component를 기록하며, inventory depletion 부분만 5개 event·10개 실행 case·0개 미계산 case·40개 atom입니다. `conditional_diagnostic_facility_annual_ir_low_high`와 F/N은 계산되지만, `facility_total_risk_available`은 `false`입니다.

네 개 범위표의 병합 결과는 `results/20261019/generic_vertical_two_sided_merged_scope_matrix.json`입니다. family별 상태가 `PARTIAL`이면 시설 전체 위험도를 올리지 않으며, 12개 사고 family 중 빠진 provider history·operator-limited physics·synthetic release는 감사 결과에 남습니다. 독립 진단 결과에 component coverage가 없을 때는 namespace rebind 단계가 event/case 회계에서 한 행을 만들어 설비별 연결 상태를 보존합니다. 이 기능은 회계 보완이며 빈도 추론·물리검증·QRA 승격이 아닙니다.

수직 벤트의 면적 구간을 하나의 대표 누출로 줄이지 않기 위해 `scripts/validate_vertical_vent.py --all-area-bins` 경로를 추가했습니다. `AREA_0.01%`부터 `AREA_100%`까지 다섯 개를 각각 provider 계산하고, 두 기상 조건의 10개 case를 같은 vertical handoff→SLABx 피해 chain으로 실행합니다. 최신 결과는 `results/20261020/vertical_vent_all_bins/`와 [모든 개구면적 연결 기록](docs/PRISM_수직벤트_모든개구면적_연결_개발기록_20261020.md)에 있습니다. 이 실행은 5개 event·10개 case·질량잔차 0 kg을 확인했지만, provider handoff가 합성·operator-limited이고 독립검증이 없어 시설 전체 IR/F-N을 열지 않습니다. 새 병합 원장은 설비 campaign별 `fresh_physics_cases`와 case p95/p99 처리시간도 보존합니다.

통합 원장을 시설 평가기에 다시 넣을 때도 원장을 하나의 campaign으로 재분해하지 않습니다. `prism.facility_risk_ledger.v1`의 설비별 상태·coverage·처리시간·미계산 회계를 그대로 보존하므로, 현재 11개 component의 상태(`EXECUTED` 3, `PARTIAL` 8, `EXCLUDED` 1)가 평가 결과와 evidence request에 일치합니다. 이 회계 보정은 위험도를 높이거나 사고를 대체하지 않습니다.

### 차단 성공·실패와 방출 지속시간 결합

`equipment_isolation_campaign`도 공통 시설 장부에 별도 component로 연결했습니다. `isolation-diagnostic-pipe-01`은 5개 opening bin, 20개 실행 branch/weather case, 80개 risk atom을 보유합니다. 성공 10개는 0.25초 차단 후 유량 0인 `reviewed_isolation_success`, 실패 10개는 0.5초 diagnostic horizon인 `synthetic_diagnostic_horizon`으로 각각 기록됩니다.

최신 다중 campaign 요약은 [`isolation 포함 시설 평가`](examples/native_lh2dt_packet_campaign_vertical_handoff_two_sided_inventory_isolation_facility_assessment_summary.json)입니다. 전체는 41개 event, 70개 case, 240개 atom, 11개 component이며, 이 결과도 조건부 진단 IR/F-N만 제공하고 시설 전체 위험도는 `false`로 유지합니다. 성공 branch를 실패 branch의 대체값으로 사용하지 않으며, synthetic 종료시계와 실제 차단 신뢰도 부족은 IJHE 감사 blocker로 남습니다.

### 다음 실증자료를 위한 evidence request

현재 시설 평가와 사고범위 matrix에서 남은 증거 요구사항은 `src/lh2_tno/facility_evidence_request.py`가 자동으로 정리합니다. 다음처럼 최신 평가와 병합 matrix를 넣으면 설비별·사고군별 provider 자료 목록이 생성됩니다.

```powershell
$py = (Get-Item '../output/prism-export-v060-1febujhk/venv/Scripts/python.exe').FullName
& $py scripts/build_facility_evidence_request.py `
  --assessment results/20261019/native_campaign_with_vertical_handoff_two_sided_inventory_isolation_facility_assessment.json `
  --scope-matrix results/20261019/generic_vertical_two_sided_merged_scope_matrix.json `
  --output results/20261019/facility_evidence_request.json
```

출력은 `prism.external_accident_history.v1` provider packet, 정확한 component·port·개구·위치·방향, provider 소유 시간 이력과 종료근거, 재고·질량·에너지 폐합, 독립 물리검증을 요구한다. 현재 12개 사고군과 11개 component를 `OPEN_EVIDENCE_REQUEST`로 표시하며, 문헌 빈도를 센서나 provider 결과에서 추정하지 않는다. 실제 provider packet과 검증자료가 들어오기 전에는 이 요청서가 시설 IR/F-N 승격을 열지 않는다.

각 사고군에는 `strict_gate_categories`도 기록한다. `MISSING_PROVIDER_CASES`, `OPERATOR_LIMITED_INPUT`, `DOMAIN_INCOMPLETE`, `FAILED_PROVIDER_CASE`, `FAMILY_SCOPE_PARTIAL` 중 실제 장부가 뒷받침하는 항목만 표시하고, 항목별로 다음 provider 자료를 연결한다. 이는 자료 수집 순서를 정리하는 분류표이며 누출빈도나 시설 QRA를 자동으로 추정하는 기능이 아니다. 최신 2026-10-22 요청에는 `FAMILY_SCOPE_PARTIAL`, `MISSING_PROVIDER_CASES`, `OPERATOR_LIMITED_INPUT`이 남아 있다.

### qualified provider packet과 물리검증의 승격 게이트

실제 설비 모델이 사고 이력을 제공하면 `RiskCampaign.provider_packet_evidence`에 그 근거를 명시한다. `prism.provider_packet_evidence.v1` 레코드는 event·component·port와 provider source/result SHA-256 digest를 모두 적어야 하며, 실행된 `provider_packet_identity`와 정확히 일치할 때만 해당 case를 `qualified_provider_packet_case_count`로 센다. packet을 읽었다는 사실만으로 qualified 상태가 되지 않는다.

`physical_validation_evidence.status=independent_validated`와 검증 근거 ID/digest도 별도로 필요하다. 따라서 캠페인 결과의 `provider_packet_promoted`, `physical_validation_claim`, `complete_facility_qra_claim`은 각각 독립적으로 기록되며, 기존 문헌 빈도는 그대로 유지된다. provider 방출 이력은 빈도를 만들거나 바꾸지 않는다. 현재 실행 결과는 qualified packet 0건이고, 이 게이트가 시설 전체 IR/F-N을 자동으로 열지는 않는다. 이 계약과 검사는 483개 portable 테스트로 확인했다.

문헌 빈도 p05·published·p95 및 분포 샘플링 결과에도 같은 승격 상태를 전달한다. 따라서 빈도 민감도 표가 계산되어도 `provider_packet_promoted`와 `complete_facility_qra_claim`을 별도로 확인할 수 있고, 빈도 불확실성 결과가 물리검증이나 시설 완결성을 대신하지 않는다.

새 gate를 반영해 기존 5개 campaign 결과를 물리 재실행 없이 다시 집계했다. [`provider-gate assessment summary`](examples/provider_gate_facility_assessment_summary.json)는 41개 event, 70개 case, 37개 미계산 case, 240개 risk atom, provider packet case 0건, qualified facility QRA `false`를 기록한다. 원본 ledger·assessment·evidence request는 `results/20261019/`에 생성했다.

같은 결과를 IJHE 완료 감사기에 다시 넣은 요약은 [`ijhe_completion_audit_provider_gate_summary.json`](examples/ijhe_completion_audit_provider_gate_summary.json)이다. 15개 검사 중 chain·빈도 불확실성·방출 지속시간/차단/재고 장부·처리시간은 통과했고, 실제 provider packet·주요 사고범위 완결·시설 IR/F-N 때문에 4개 blocker가 남아 `INCOMPLETE_EVIDENCE`이다.

### 설비 배관 개구면적을 기존 시설 장부에 결합하는 방법

`validate_equipment_campaign.py --all-area-bins`는 설비 provider가 계산한 `AREA_0.01%`~`AREA_100%` 방출을 각각 실행한다. 기존 시설 campaign과 결합할 때는 시설 ID·수용점 ID·component ID를 명시하고, 이미 사용한 asset ID와 겹치지 않게 지정한다.

```powershell
python scripts/validate_equipment_campaign.py `
  --all-area-bins `
  --facility-id generic-lh2-full-scope-example `
  --common-receptor-id worker-01 `
  --component-id liquid-transfer-line-01 `
  --asset-id equipment-transfer-line_asset `
  --output-dir results/20261020/equipment_campaign_all_bins_transfer_line_replacement
```

이 결과는 설비 campaign 자체의 계산을 완료해도 시설 전체 QRA를 자동으로 열지 않는다. 기존 event를 중복 합산하지 않도록 교체용 facility ledger를 만들고, 문헌 빈도 시나리오·사고범위 matrix·provider 자격·물리검증 gate를 함께 확인해야 한다. 실제 실행 결과와 재현 파일은 [설비 상태·배관 개구면적 시설 결합 기록](docs/PRISM_설비상태_배관개구면적_시설결합_개발기록_20261020.md)에 정리했다.

### 밸브 방출 패킷을 시설 원장에 결합한 최신 단계

`scripts/validate_valve_campaign.py`는 기존 `transfer-valve-01`의 다섯 문헌 면적 사건을 저장된 `lh2dt.Valve` 액체/2상 방출 패킷과 연결한다. 각 패킷은 PRISM의 `valve-accident-out` 포트로 들어가 SLABx-LH2/SLABx 피해 계산과 native IR/F-N 원자로 전달된다. 결과는 [밸브 campaign](results/20261021/valve_provider_all_bins_campaign/campaign_result.json)에 있다.

최신 7개 campaign 시설 원장은 [여기](results/20261021/native_campaign_with_valve_transfer_line_replacement_vertical_all_bins_two_sided_inventory_isolation_facility_ledger.json)에 있다. 고유 사건 41개, 사례 80개, 보류·미계산 복사본 37개, 위험 원자 304개를 기록한다. 밸브는 8개 `EXECUTED_OPERATOR_LIMITED` 사례와 2개 백엔드 시간 제한 실패를 갖는다. 실패를 0 위험으로 처리하지 않고 미계산으로 남긴다.

이 통합은 밸브 모델을 별도 애드온으로 분리하지 않고 같은 PRISM 시설 원장에 선택형 외부 방출 경계로 연결한 것이다. 그러나 현재 패킷은 합성·스크리닝 자료이고 provider 자격·독립 물리검증·완전한 사고군이 없으므로 시설 전체 IR/F-N은 계속 차단된다. 자세한 내용은 [밸브 방출 패킷 시설 결합 기록](docs/PRISM_밸브_방출패킷_시설결합_개발기록_20261021.md)과 [IJHE 완료 감사](results/20261021/ijhe_completion_audit_valve_transfer_line_replacement.json)를 참조한다.

`validate_valve_campaign.py --area-bin AREA_0.01% --timeout-s 360`처럼 제한시간 초과 사례만 선택 재실행할 수 있다. 이 재시도 후 밸브 10개 사례가 모두 계산됐지만 모두 `EXECUTED_OPERATOR_LIMITED`이며, 시설 원장은 [`repaired ledger`](results/20261022/native_campaign_with_repaired_valve_transfer_line_replacement_vertical_all_bins_two_sided_inventory_isolation_facility_ledger.json)에서 312개 위험 원자로 갱신됐다. 제한시간 개선은 계산 누락을 줄인 것이고 provider 자격·물리검증·시설 전체 QRA 승격을 의미하지 않는다.

사고범위 표의 `conditional_status`/`conditional_chain_complete`는 수치 계산 완료 여부를 별도로 보여준다. 운전자 제한 사례는 조건부 숫자 계산으로 세지만 엄격한 `status`/`matrix_complete`는 계속 `PARTIAL`로 유지한다. 이전 범위표 형식의 `executed_case_count`를 보정해 현재 조건부 범위는 12개 선언 family 모두 미계산 0건으로 기록한다.


**2026-10-22 case 회계 보정:** 시설 원장의 서로 다른 기상·방출 branch를 event ID만으로 합치지 않도록 case 식별자를 보정했다. 최신 80개 case 중 78개는 조건부 숫자 chain을 실행했고 2개는 `UNCOMPUTED`로 남았다. 엄격 승격용 보류 복사본 37개와 구분한 자세한 정의는 [조건부 case 회계 보정 기록](docs/PRISM_조건부case_회계보정_20261022.md)에 있다.




**2026-10-24 설비 모델 결합 감사 보정:** 최신 native catalog와 worklist를 다시 실행해 8개 manifest component 중 7개 설비의 사고 방출 인터페이스와 7개 진단 adapter를 확인했다. [`native_equipment_model_binding_audit_v1.json`](results/20261024/native_equipment_model_binding_audit_v1.json)은 `accident_release_interface_component_count=7`, `diagnostic_release_adapter_component_count=7`, `qualified_accident_release_component_count=0`을 분리 기록한다. 경계 component가 state-only이므로 전체 catalog 상태는 `STATE_ONLY_BOUND`이지만, 이는 7개 native 사고 인터페이스가 없다는 뜻이 아니다. [`native_generic_scope_worklist_with_native_binding_v1.json`](results/20261024/native_generic_scope_worklist_with_native_binding_v1.json)은 24개 사건 요청을 모두 구조적으로 준비했지만 실제 provider packet·독립 물리검증·시설 IR/F-N은 승격하지 않는다.

**2026-10-24 수직 handoff 체인 감사:** 다섯 수직 vent 사건은 별도 native `resolved_release_catalog`에 저장된 합성·운영자 제한 방출 패킷을 provider result digest로 다시 연결했다. [`audit_vertical_handoff_chain.py`](scripts/audit_vertical_handoff_chain.py)는 5개 event, 10개 weather case, 40개 final-harm atom을 방출량·종료시간·재고 장부·vertical state history까지 대조한다. 결과는 [`native_generic_scope_vertical_handoff_chain_v1.json`](results/20261024/native_generic_scope_vertical_handoff_chain_v1.json)과 [감사 기록](docs/PRISM_수직핸드오프_체인감사_20261024.md)에 있다. 이 기록은 기존 24개 packet subset과 합쳐 29개 선언 사건의 진단 연결을 확인하지만, 합성 입력·운영자 제한·독립 검증 부재 때문에 qualified provider packet, 현장 빈도, 시설 QRA를 열지 않는다.

두 결과를 [`audit_combined_chain_closure.py`](scripts/audit_combined_chain_closure.py)로 합치면 [`native_generic_scope_combined_chain_closure_v1.json`](results/20261024/native_generic_scope_combined_chain_closure_v1.json)의 `FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED` 상태가 된다. 이는 24개 packet-subset 사건과 5개 vertical operator-limited 사건이 모두 최종 피해 원자에 도달했다는 뜻이며, qualified provider 0건과 시설 QRA `false`를 동시에 보존한다. 자세한 정의는 [전체 진단 체인 통합 감사](docs/PRISM_전체진단체인_통합감사_20261024.md)에 있다.

\n
**상태 스냅샷→방출 경계 감사 (2026-10-27):** 일부 오래된 `DynamicHEMPipe` 내보내기가 상태 digest만 넣고 실제 상태 원문을 요청에 넣지 않던 경로를 정식 `EquipmentStateSnapshot` 전달로 보완했습니다. `LayeredTank`와 native DynamicHEMPipe full-bore를 재실행해 압력·온도·상·위치·품질을 포함한 `prism.equipment_state_snapshot.v1` 원문, canonical digest, provider echo를 모두 기록하고 방출→SLABx-LH2/SLABx→피해 chain까지 확인했습니다. 새 `scripts/audit_state_snapshot_binding.py`는 원문 없는 digest를 `DECLARED_DIGEST_ONLY` 또는 `UNBOUND`로 분리합니다. 최신 union 감사는 26개 기록 중 2개 `BOUND_AND_ECHOED`, 24개 campaign 사건 `UNBOUND`, digest 불일치 0건이며, `diagnostic_equipment_state_snapshot_binding`은 diagnostic-only PASS입니다. 따라서 상태 handoff 증거는 강화됐지만 union 전체 시설의 상태 연결·provider 자격·빈도·물리검증·시설 IR/F-N은 승격하지 않습니다. [상태 스냅샷→방출 경계 감사](docs/PRISM_상태스냅샷_방출경계_감사_20261027.md)
