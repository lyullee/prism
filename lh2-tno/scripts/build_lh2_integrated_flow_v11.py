"""Build the neutral, multi-model LH2 risk-assessment flow figure (v11)."""
from pathlib import Path
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"
SOURCE = FIG / "lh2_hazop_multiequipment_integrated_flow_v10.svg"
OUT_SVG = FIG / "lh2_hazop_multiequipment_integrated_flow_v11.svg"
OUT_PNG = FIG / "lh2_hazop_multiequipment_integrated_flow_v11.png"

def replace_all(svg: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        if old not in svg:
            raise ValueError(f"Expected source text was not found: {old}")
        svg = svg.replace(old, new)
    return svg

def build() -> None:
    svg = SOURCE.read_text(encoding="utf-8")
    svg = replace_all(svg, {
        "액화수소 인수기지 통합 위험평가 흐름": "액화수소 인수기지 위험분석 통합 흐름",
        "현장 상태 + 운전 모드 → HAZOP 판정 → 다중 위험모델 결합 → 현재·예측 상태 평가":
            "현장 입력(설비 상태·운전 모드) → HAZOP 판단 → 공통 계산 계층 → 현재·예측 위험도",
        "결정된 위험 시나리오를 공통 정량평가 계층에 전달":
            "결정된 위험 시나리오를 공통 정량분석 계층에 전달",
        "현재·예측 경로가 같은 시나리오 ID와 모델 조합을 사용":
            "현재·예측 경로가 같은 시나리오 ID와 모델 조합을 사용",
        "정량 위험평가 모델 결합 계층": "공통 정량분석 계층",
        "동일 시나리오에 설비·빈도·누출확산·점화·노출 모델을 함께 적용해 위험도를 산출합니다.":
            "HAZOP가 고른 동일 시나리오에 설비·빈도·누출확산·점화·노출 모델을 함께 적용합니다.",
        "운전 모드는 현장 입력에 포함되어 HAZOP 판단과 시나리오 선택에 직접 반영됩니다.":
            "운전 모드는 센서·설비 상태와 함께 HAZOP 판단 및 시나리오 선택에 직접 반영됩니다.",
        "위험도 통합 계산": "결과·위험도 통합",
        "모델 공통 인터페이스 · 결과 통합": "공통 계산 인터페이스 · 결과 통합",
    })
    # Make the model-layer heading visually neutral and peer-oriented.
    svg = svg.replace('font-weight="800" fill="#153D5B"', 'font-weight="700" fill="#315B77"')
    OUT_SVG.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(OUT_PNG), output_width=2400, output_height=1350)
    print(OUT_SVG)
    print(OUT_PNG)

if __name__ == "__main__":
    build()
