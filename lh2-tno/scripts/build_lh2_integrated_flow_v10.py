"""Build the neutral, multi-model LH2 risk-assessment flow figure.

The field packet contains both measured equipment/process state and the
operating mode.  HAZOP uses both values to select the scenario.  The lower
layer deliberately presents the equipment, frequency, dispersion, ignition /
exposure and risk-integration models as peers; no single package is shown as
the centre of the system.
"""

from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
SOURCE = FIG / "lh2_hazop_multiequipment_integrated_flow_v9.svg"
OUT_SVG = FIG / "lh2_hazop_multiequipment_integrated_flow_v10.svg"
OUT_PNG = FIG / "lh2_hazop_multiequipment_integrated_flow_v10.png"


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
            "액화수소 인수기지 통합 위험분석 흐름": "액화수소 인수기지 통합 위험평가 흐름",
            "현장 상태·운전 모드 → HAZOP 시나리오 결정 → 공통 위험모델 계층 결합 → 현재·예측 상태 평가":
                "현장 상태 + 운전 모드 → HAZOP 판정 → 다중 위험모델 결합 → 현재·예측 상태 평가",
            "결정된 위험 시나리오를 공통 위험모델에 전달":
                "결정된 위험 시나리오를 공통 정량평가 계층에 전달",
            "두 경로 모두 동일한 시나리오와 모델 조합을 사용":
                "현재·예측 경로가 같은 시나리오 ID와 모델 조합을 사용",
            "공통 정량 위험분석 계층": "정량 위험평가 모델 결합 계층",
            "빈도·시나리오 모델": "사고빈도·시나리오",
            "QRA 통합 계산": "위험도 통합 계산",
            "공통 실행 계층 · 모델 결과 통합": "모델 공통 인터페이스 · 결과 통합",
            "정량평가는 동일한 시나리오에 여러 모델을 함께 적용하고, 공통 실행 계층에서 결과를 산출합니다.":
                "동일 시나리오에 설비·빈도·누출확산·점화·노출 모델을 함께 적용해 위험도를 산출합니다.",
            "도식 읽는 법": "도식 읽는 법",
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
