"""Generate handoff 30 from verified N=512 convergence artifacts."""
from __future__ import annotations

import json
from pathlib import Path
import statistics

import statistical_pilot as S


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "논문" / "불연속Sobol_N512_20260901"
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    counts = summary["counts"]
    metrics = summary["metrics"]
    eligible_by_measure = {
        measure: sum(value["status"] == "PRIMARY_ELIGIBLE"
                     for key, value in metrics.items() if key.startswith(f"{measure}|"))
        for measure in S.MEASURES
    }
    eligible_by_curve = {
        curve: sum(value["status"] == "PRIMARY_ELIGIBLE"
                   for key, value in metrics.items() if key.endswith(f":{curve}"))
        for curve in S.CURVES
    }
    iqr_failures = sum(value["max_total_n512_iqr"] > .1
                       for value in metrics.values())
    excursions = sum(value["estimator_excursion_n512"] for value in metrics.values())
    spacing_consensus = sum(value["dominant_n512_consensus"] == "spacing_m"
                            and value["dominant_n512_consensus_fraction"] == 1.
                            for value in metrics.values())
    changes = [value["max_absolute_paired_change_n256_to_n512"]
               for value in metrics.values()]

    lines = [
        "# 30 — 불연속 Sobol N=512 순차 확장 (2026-09-01)", "",
        "## 최종 판정", "",
        f"불연속 edge-count Sobol 지표 {counts['edge_metrics']}개 중 {counts['primary_eligible_metrics']}개가 결과 전 고정한 N=512 개별 기준을 통과했다. 계열 전체의 본문 유지 기준은 최소 {counts['family_required_metrics']}개였으므로, 최종 판정은 `{summary['family_decision']}`이다.", "",
        "따라서 불연속 Sobol 총효과의 정확한 크기는 논문 본문의 핵심 정량결론에서 제외하고, 수치수렴 한계를 투명하게 제시하는 탐색적 부록으로 이동한다. 통과한 13개만 골라 본문에 싣지 않는다.", "",
        "집합형 범주분율, 곡선별 최고집합 변화 및 새 가상배치 전이 결과는 별도의 8-scramble 안정성 결과가 있으므로 본문 주결과로 유지한다.", "",
        "## 사전 고정한 순차 규칙", "",
        "- 같은 8개 scrambled Sobol sequence에서 N=256 앞부분을 그대로 재사용하고 인덱스 256–511만 새로 계산했다.",
        "- 개별 통과: 11개 변수 전체에서 seed별 |ST(N512)−ST(N256)| 최대값 ≤0.1, N=512 scramble IQR 최대값 ≤0.1, 추정치 [-0.05, 1.05] 이탈 없음.",
        "- 계열 통과: 24개 중 최소 80%, 즉 20개가 개별 통과.",
        "- 계열 미달 시 `EXPLORATORY_APPENDIX`; 결과를 본 뒤 N=1024를 자동 추가하지 않음.", "",
        "## 계산 규모", "", "| 구분 | 수 |", "|---|---:|",
        f"| 기존/최종 base N | {counts['prior_n']} / {counts['final_n']} |",
        f"| 독립 scramble | {counts['scrambles']} |",
        f"| 잠긴 앞부분 재사용 행 | {counts['locked_prefix_rows_reused']:,} |",
        f"| 신규 열역학 상태 | {counts['new_thermodynamic_source_states']:,} |",
        f"| 신규 후반부 행 | {counts['new_tail_rows']:,} |",
        f"| 신규 배치×곡선 관계 | {counts['new_tail_layout_curve_relations']:,} |",
        f"| 신규 방출원 실패 | {counts['new_source_failures']} |",
        f"| 독립 물리실험 추가 | {counts['independent_physical_experiments_added']} |", "",
        "## 수렴 결과 분해", "",
        f"N=256→512 최악 변화의 지표별 범위는 {min(changes):.3f}–{max(changes):.3f}, 중앙값은 {statistics.median(changes):.3f}였다.", "",
        f"개별 미달 {counts['appendix_metrics']}개는 모두 N 변화가 0.1을 넘었다. 그중 {iqr_failures}개는 N=512 scramble IQR도 0.1을 넘었다. 추정범위 이탈은 {excursions}개였다.", "",
        f"표본화별 통과는 log-diameter {eligible_by_measure['log_diameter']}/12, linear-diameter {eligible_by_measure['linear_diameter']}/12였다. 곡선별 통과는 fit {eligible_by_curve['fit']}/12, development-upper {eligible_by_curve['development_upper']}/12였다.", "",
        f"spacing은 {spacing_consensus}/{counts['edge_metrics']}개 지표에서 N=512의 모든 8개 scramble에서 최대 총효과 변수였다. 이 정성적 반복은 남지만, 선언한 가상 배치와 5–40 m 설계범위에 조건부이며 정확한 총효과 크기나 보편적 물리 중요도 순위로 사용하지 않는다.", "",
        "## 검증", "",
        "읽기 전용 전수 검증에서 잠긴 앞부분 53,248행을 다시 구성하고, 신규 열역학 상태 32,768개, 신규 후반행 53,248개, 저장된 배치×곡선 관계 638,976개를 확인했다.", "",
        "N=256/512 민감도 레코드 384개, 총 8,448개 Sobol 스칼라를 원시행에서 재계산했다. 저장값과의 최대 절대오차 및 잠긴 N=256과의 최대 절대오차는 모두 0이었다. 상태는 `VERIFIED_SOFTWARE_AND_DATA_INTEGRITY_ONLY`이며 실험검증은 false다.", "",
        "최종 전체 회귀시험은 440 passed, failures/errors/skips 0, 기존 의도된 ScopeWarning 1건이었다. 경고는 0.3 m/s가 SLABX 검증범위 [0.5, 12] m/s 밖임을 드러내는 범위 시험이다.", "",
        "## 논문에서의 사용", "",
        "본문: 집합형 관리판단의 정의, 항상 유일 최고의 희소성, Cd 확보 후 남는 곡선·동률·무도달 불확실성, 새 배치로의 전이, 직접 범주분율의 scramble 안정성을 중심으로 구성한다.", "",
        "부록: N=128→256 및 N=256→512 수렴경로, 24개 지표의 Jansen 1차·총효과 원시 추정, spacing의 정성적 최대효과 반복, 사전 종료규칙과 `EXPLORATORY_APPENDIX` 판정을 제시한다.", "",
        "본문에서 피할 표현: ‘Sobol 지수가 수렴했다’, ‘spacing의 총효과는 정확히 X다’, ‘실제 설비에서도 spacing이 지배한다’. 허용되는 표현은 ‘선언한 합성 설계에서 spacing이 모든 scramble의 최대 총효과 변수였지만, 불연속 지수 계열은 N=512 family 기준을 충족하지 못했다’이다.", "",
        "## 남은 경계", "",
        "이번 확장은 수치 표본수렴만 다룬다. 독립 실험, 실제 운전분포, 모델형식 오차, M01 가상노즐, 분산/LFL, 복사, LH2/M02, 과도 결합, 취약도 또는 현장 디지털 트윈 검증을 추가하지 않는다.", "",
        "## 파일", "",
        "- `../논문/불연속Sobol_N512_20260901/불연속_Sobol_N512_결과.md`: 상세 판정표와 그림",
        "- `../논문/불연속Sobol_N512_20260901/protocol.json`: 결과 전 고정한 순차·판정·종료규칙",
        "- `../논문/불연속Sobol_N512_20260901/summary.json`: 판정 수치 원본",
        "- `../논문/불연속Sobol_N512_20260901/tail_design_results.jsonl`: 신규 인덱스 256–511 원시행",
        "- `../논문/불연속Sobol_N512_20260901/sensitivity_estimates.json`: N=256/512 원시 Jansen 추정",
        "- `../논문/불연속Sobol_N512_20260901/artifact_hashes.json`: 산출물 체크섬",
        "- `../코드/statistical_convergence_extension.py`: 순차 확장·판정·보고서 생성",
        "- `../코드/verify_statistical_convergence_extension.py`: 읽기 전용 전수 재검산",
        "- `../코드/test_statistical_convergence_extension.py`: prefix·판정·fail-closed 시험", "",
    ]
    (root / "핸드오프" / "30_DISCONTINUOUS_SOBOL_N512_20260901.md").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
