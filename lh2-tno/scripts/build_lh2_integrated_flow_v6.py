"""Build the balanced LH2 HAZOP/QRA integration figure.

The figure is intentionally model-neutral: PRISM is shown as one calculation
function inside the shared risk-integration layer, alongside the process,
release, frequency, dispersion, ignition and exposure models.
"""

from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
SOURCE = FIG / "lh2_hazop_multiequipment_integrated_flow_20261014.svg"
OUT_SVG = FIG / "lh2_hazop_multiequipment_integrated_flow_v6.svg"
OUT_PNG = FIG / "lh2_hazop_multiequipment_integrated_flow_v6.png"


def build() -> None:
    svg = SOURCE.read_text(encoding="utf-8")

    # Make every arrow marker explicit.  The earlier draft referenced two
    # markers that were not declared in its <defs> block.
    svg = svg.replace(
        '<marker id="arrow-6F8EA4"',
        '<marker id="arrow-35C6D6" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 1 L 11 6 L 1 11 z" fill="#35C6D6"/></marker><marker id="arrow-F2A45B" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 1 L 11 6 L 1 11 z" fill="#F2A45B"/></marker><marker id="arrow-6F8EA4"',
    )

    svg = svg.replace(
        "현장 상태와 운전 모드 → HAZOP 정성판단 → 공통 위험모델 → 현재·예측 상태 평가",
        "현장 상태·운전 모드 → HAZOP 시나리오 판단 → 여러 위험모델 결합 → 현재·예측 상태 평가",
    )
    svg = svg.replace(
        "입력의 운전 모드가 판단 조건과 시나리오 선택에 함께 사용됨",
        "현장 입력의 운전 모드가 HAZOP 판단 조건과 시나리오 선택에 함께 사용됨",
    )
    svg = svg.replace("통합 정량 위험분석 계층", "공통 정량 위험분석 계층")
    svg = svg.replace("PRISM 연산 커널 포함", "PRISM 위험도 계산 기능 포함")
    svg = svg.replace(
        "설비·공정 모델</tspan><tspan x=\"1068\" dy=\"17.3\">현재 방출 상태",
        "설비·공정 모델</tspan><tspan x=\"1068\" dy=\"17.3\">방출·차단·재고 상태",
    )
    svg = svg.replace(
        "설비·공정 모델</tspan><tspan x=\"1068\" dy=\"17.3\">예측 방출 상태",
        "설비·공정 모델</tspan><tspan x=\"1068\" dy=\"17.3\">예측 방출·재고 상태",
    )
    svg = svg.replace(
        "사고 빈도 모델</tspan><tspan x=\"1288\" dy=\"17.3\">문헌·설비 근거",
        "빈도·시나리오 모델</tspan><tspan x=\"1288\" dy=\"17.3\">문헌·설비 근거",
    )
    svg = svg.replace(
        "사고 빈도 모델</tspan><tspan x=\"1288\" dy=\"17.3\">시나리오별 근거",
        "빈도·시나리오 모델</tspan><tspan x=\"1288\" dy=\"17.3\">시나리오별 근거",
    )
    svg = svg.replace(
        "점화·노출 모델</tspan><tspan x=\"1068\" dy=\"17.3\">기상·인구·노출",
        "점화·노출 모델</tspan><tspan x=\"1068\" dy=\"17.3\">기상·인구·IR/F-N",
    )
    svg = svg.replace(
        "정량평가는 설비·빈도·확산·노출 모델을 묶어 수행하며, PRISM은 그중 위험도 통합 계산 기능으로 함께 동작합니다.",
        "정량평가는 여러 모델을 같은 시나리오에 적용하며, PRISM은 그중 위험도 통합 계산 기능으로 함께 동작합니다.",
    )
    svg = svg.replace(
        "두 경로 모두 동일한 사고 시나리오·모델 조합을 사용",
        "두 경로 모두 동일한 시나리오와 모델 조합을 사용",
    )

    OUT_SVG.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(OUT_PNG), output_width=2400, output_height=1350)
    print(OUT_SVG)
    print(OUT_PNG)


if __name__ == "__main__":
    build()
