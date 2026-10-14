"""Build the model-neutral LH2 HAZOP/QRA integration figure.

The field packet carries the operating mode into the HAZOP lookup.  The
quantitative layer is shown as a peer integration layer for the equipment and
process, frequency, SLABx-LH2, ignition/exposure, and QRA functions; PRISM is
not visually promoted as a standalone model.
"""

from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
SOURCE = FIG / "lh2_hazop_multiequipment_integrated_flow_v8.svg"
OUT_SVG = FIG / "lh2_hazop_multiequipment_integrated_flow_v9.svg"
OUT_PNG = FIG / "lh2_hazop_multiequipment_integrated_flow_v9.png"


def replace_all(svg: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        if old not in svg:
            raise ValueError(f"Expected source text was not found: {old}")
        svg = svg.replace(old, new)
    return svg


def build() -> None:
    svg = SOURCE.read_text(encoding="utf-8")
    svg = replace_all(
        svg,
        {
            "현장 상태·운전 모드 → HAZOP 시나리오 판단 → 여러 위험모델 결합 → 현재·예측 상태 평가":
                "현장 상태·운전 모드 → HAZOP 시나리오 결정 → 공통 위험모델 계층 결합 → 현재·예측 상태 평가",
            "모델 결과 통합 · PRISM 연계": "공통 실행 계층 · 모델 결과 통합",
            "정량평가는 동일한 시나리오에 여러 모델을 함께 적용하며, 통합 계산 계층에서 결과를 산출합니다.":
                "정량평가는 동일한 시나리오에 여러 모델을 함께 적용하고, 공통 실행 계층에서 결과를 산출합니다.",
        },
    )
    OUT_SVG.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(OUT_PNG),
        output_width=2400,
        output_height=1350,
    )
    print(OUT_SVG)
    print(OUT_PNG)


if __name__ == "__main__":
    build()
