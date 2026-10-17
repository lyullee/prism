# SLABx-LH2 검증 상태

2026-11-15 현재 SLABx-LH2는 PRISM의 남은 개발 과업에서 제외된 **고정·검증 완료 외부 구성요소**로 취급한다. 원자료와 논문화용 재현성 자료를 다시 읽어 검사를 실행했으며, 이전 기록과 비교해 결과 변화가 없었다.

재검사 결과:

- 상태: `RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE`
- 모델: SLABx-LH2 0.1.2, SLABx 1.0.6
- 검사: 5/5 통과, 차단 사유 0건
- FFI 사례: 6건
- FLACS 비교 행: 6건
- pool-radius 중앙 비율: 1.0305006
- 최대 시나리오 질량잔차: 1.77e-12 kg
- 반복 실행 재고 차이: 0 kg
- 재검사 기록: [`slabx_lh2_validation_audit_current_recheck.json`](../results/20261115/slabx_lh2_validation_audit_current_recheck.json)

`RESTRICTED_*` 표기는 SLABx가 실패했다는 뜻이 아니다. 이 기록은 SLABx가 담당하는 극저온 pool·옥외 확산·질량수지·재현성 범위를 닫고, 점화·폭발·IR/F-N·시설 QRA를 SLABx의 검증 범위로 잘못 확장하지 않기 위한 경계표시다. 따라서 이 문서의 검사는 SLABx 추가 개발을 요구하지 않는다. PRISM에서 유지할 항목은
SLABx 결과를 변경하지 않는 입력·단위·시간축·실패처리 handoff 계약뿐이다.

남은 시설 과업은 SLABx 자체가 아니라 다음 연결이다.

1. 실제 설비 provider가 방출량·지속시간·차단·재고 소진을 제공한다.
2. 그 방출 경계가 SLABx 입력과 정확히 연결된다.
3. 시설별 수용점·기상·인구·점화·IR/F-N 계산이 모든 선언 사례에 대해 qualified 자료로 닫힌다.

PRESLHY Trial 10의 현장 모델 비교 결과는 별도 외부 설비/좌표축 진단이다. 그 결과를 SLABx 검증 실패로 해석하거나 SLABx 검증 완료를 시설 전체 QRA 완료로 확대하지 않는다.
