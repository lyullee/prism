"""Build the neutral, peer-model LH2 risk-assessment flow figure (v4).

This version makes the field value and operating mode a single HAZOP input
package and keeps the quantitative models visually equal.  The orchestrator
is intentionally described as a common integration layer rather than as the
subject of the figure.
"""
from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "figures" / "lh2_hazop_multiequipment_integrated_flow_v11.svg"
OUT_SVG = ROOT / "docs" / "PRISM_lh2_integrated_flow_v4.svg"
OUT_PNG = ROOT / "docs" / "PRISM_lh2_integrated_flow_v4.png"


def build() -> None:
    svg = SOURCE.read_text(encoding="utf-8")
    replacements = {
        "액화수소 인수기지 위험분석 통합 흐름": "액화수소 인수기지 통합 위험분석 흐름",
        "현장 입력(설비 상태·운전 모드) → HAZOP 판단 → 공통 계산 계층 → 현재·예측 위험도":
            "현장값 + 운전 모드 → HAZOP 판단 → 다중 모델 통합 계산 → 현재·예측 위험도",
        "01  현장 입력과 HAZOP 기반 시나리오 결정": "01  현장 입력과 HAZOP 기반 시나리오 결정",
        "현장 입력 + 운전 모드": "현장 입력 패킷",
        "센서·설비 상태 + 운전 모드": "센서·설비 상태 + 운전 모드",
        "공통 정량분석 계층": "다중 모델 통합 정량분석",
        "도식 읽는 법": "도식 읽는 법",
        "HAZOP가 고른 동일 시나리오에 설비·빈도·누출확산·점화·노출 모델을 함께 적용합니다.":
            "HAZOP가 고른 동일 시나리오에 설비·빈도·누출확산·점화·노출 모델을 함께 적용합니다.",
    }
    for old, new in replacements.items():
        if old not in svg:
            raise ValueError(f"Expected source text was not found: {old}")
        svg = svg.replace(old, new)

    # Keep the model boxes peer-level: no dark highlight and no product name
    # in the central calculation layer.  The footer explains the integration
    # role without making one component the visual protagonist.
    svg = svg.replace(
        "PRISM은 통합 실행·결합 계층으로 배치",
        "모든 모델은 동일한 시나리오 ID로 연결",
    )
    svg = svg.replace(
        "PRISM은 별도 주인공이 아니라, 사고빈도·방출·SLABx-LH2·점화·피해영향 모델을 동일한 시나리오로 실행하고 결과를 결합하는 공통 계층이다.",
        "통합 실행 계층은 사고빈도·방출·SLABx-LH2·점화·피해영향 모델을 동일한 시나리오 ID와 시간 기준으로 연결하고 결과를 결합한다.",
    )
    OUT_SVG.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(OUT_PNG), output_width=2400, output_height=1350)
    print(OUT_SVG)
    print(OUT_PNG)


if __name__ == "__main__":
    build()
