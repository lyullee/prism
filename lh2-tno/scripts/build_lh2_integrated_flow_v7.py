"""Build the model-balanced LH2 HAZOP/QRA integration figure.

This revision makes the operating mode an explicit part of the field input
packet and keeps the quantitative layer visually model-neutral.  PRISM is
named only as a connected calculation function; the process, frequency,
dispersion, ignition/exposure and QRA integration functions are peers.
"""

from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
SOURCE = FIG / "lh2_hazop_multiequipment_integrated_flow_v6.svg"
OUT_SVG = FIG / "lh2_hazop_multiequipment_integrated_flow_v7.svg"
OUT_PNG = FIG / "lh2_hazop_multiequipment_integrated_flow_v7.png"


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
            # Make the first hand-off explicit: mode travels with the field
            # values into the HAZOP lookup.
            "현장 입력 패킷": "현장 입력 + 운전 모드",
            "센서·설비 상태</tspan><tspan x=\"118\" dy=\"32.5\">압력 · 온도 · 재고 · 밸브/펌프 상태</tspan>":
                "센서·설비 상태 + 운전 모드</tspan><tspan x=\"118\" dy=\"32.5\">압력 · 온도 · 재고 · 밸브/펌프</tspan>",
            "운전 모드: 인수 · 공급 · 스탠바이": "모드 값: 인수 · 공급 · 스탠바이",
            "모드별 이탈 기준 · 원인 · 결과 · 기존 방호":
                "운전 모드별 이탈 기준 · 원인 · 결과 · 방호",
            "HAZOP 기반 정성판단": "HAZOP 규칙 적용",
            "현장값 + 운전 모드 + HAZOP 기준</tspan><tspan x=\"850\" dy=\"35.0\">이탈 여부와 원인·결과·방호를 자동 조회</tspan><tspan x=\"850\" dy=\"35.0\">→ 적용할 위험 시나리오를 생성</tspan>":
                "현장값 + 운전 모드 + HAZOP 기준</tspan><tspan x=\"850\" dy=\"35.0\">이탈 여부·원인·결과·방호를 함께 조회</tspan><tspan x=\"850\" dy=\"35.0\">→ 운전 모드에 맞는 위험 시나리오 생성</tspan>",
            "현장 입력의 운전 모드가 HAZOP 판단 조건과 시나리오 선택에 함께 사용됨":
                "운전 모드는 HAZOP 판단 조건과 시나리오 선택에 직접 반영됨",
            "위험도 통합</tspan><tspan x=\"1288\" dy=\"17.3\">PRISM 위험도 계산 기능 포함</tspan>":
                "QRA 통합 계산</tspan><tspan x=\"1288\" dy=\"17.3\">여러 모델 결과 통합</tspan>",
            "정량평가는 여러 모델을 같은 시나리오에 적용하며, PRISM은 그중 위험도 통합 계산 기능으로 함께 동작합니다.":
                "정량평가는 동일한 시나리오에 여러 모델을 함께 적용하며, PRISM 계산 기능은 이 통합 계층에 연결되어 결과를 산출합니다.",
        },
    )
    # The longer mode label needs a wider pill while preserving the existing
    # box geometry and the clean alignment with the HAZOP table below it.
    svg = svg.replace(
        '<rect x="118" y="270" width="182" height="38" rx="19" fill="#DDF7F9"',
        '<rect x="118" y="270" width="258" height="38" rx="19" fill="#DDF7F9"',
    )
    svg = svg.replace(
        'font-size="20" font-weight="700" fill="#167785" text-anchor="middle"><tspan x="209" dy="0">현장 입력 + 운전 모드</tspan>',
        'font-size="20" font-weight="700" fill="#167785" text-anchor="middle"><tspan x="247" dy="0">현장 입력 + 운전 모드</tspan>',
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
