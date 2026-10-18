"""Generate the statistics-pilot handoff from verified machine results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def generate(result_dir: Path, regression_xml: Path, output: Path) -> None:
    s = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    counts = s["counts"]
    ranks = [(measure, layout, row) for measure, group in s["rank"].items()
             for layout, row in group["layouts"].items()]
    changes = [row["priority_set_change_fraction"] for _, _, row in ranks]
    active_changes = [row["priority_set_change_active_both_fraction"] for _, _, row in ranks]
    fit_empty = [row["curves"]["fit"]["empty_fraction"] for _, _, row in ranks]
    upper_empty = [row["curves"]["development_upper"]["empty_fraction"] for _, _, row in ranks]
    edge_sensitivity = [v for key, v in s["sensitivity"].items() if "|edges:" in key]
    continuous_sensitivity = [v for key, v in s["sensitivity"].items()
                              if key.endswith("|total_rate_kg_s") or key.endswith("|max_flame_fit_m")]
    test_suite = next(ET.parse(regression_xml).iter("testsuite")).attrib
    lines = [
        "# 28 — 통계 예비 계산 (2026-09-01)", "", "## 결론", "",
        "GH2 방출량–Molkov 화염 길이–가상 배치의 방향 미정 잠재 도달관계를 대상으로 조건부 통계 예비 계산을 완료했다. "
        "이 결과는 시스템의 통계 분석 가능성을 확인하지만, 독립 실험이나 실제 설비 검증을 추가하지 않는다.", "",
        "가장 중요한 진단은 현재의 ‘도달 가능한 방출원 개수’ 지표가 상당수 조건에서 유일한 관리 순위를 만들지 못한다는 점이다. "
        "따라서 논문은 강제로 하나의 순위를 만드는 것보다 가능한 최고집합, 동률, 무도달 및 모델 대안을 함께 보존하는 의사결정 안정성 연구로 가는 것이 타당하다.", "",
        "## 계산 규모를 구분해서 기록", "", "| 구분 | 수 |", "|---|---:|",
        f"| 각 scramble 기본 표본 | {counts['base_n_per_scramble']} |",
        f"| 독립 scramble | {counts['scrambles']} |",
        f"| 설계 표본화 방식 | {counts['design_measures']} |",
        f"| 입력 변수 | {counts['parameters']} |",
        f"| 가상 배치 | {counts['synthetic_layouts']} |",
        f"| 서로 연관된 화염 곡선 | {counts['related_flame_curves']} |",
        f"| 고유 열역학 상태 계산 | {counts['unique_thermodynamic_source_states']:,} |",
        f"| 전역 민감도용 전체 입력행 | {counts['pick_freeze_parameter_rows']:,} |",
        f"| 배치×곡선 도달관계 계산 | {counts['layout_curve_evaluations']:,} |",
        f"| 독립 물리 실험 추가 | {counts['independent_physical_experiments_added']} |",
        f"| 방출원 계산 실패 | {counts['source_failures']} |", "",
        "13,312개 입력행은 256개 독립 실험이 커진 것이 아니다. A/B 기본표본, 변수 교체 표본, 두 표본화 방식과 두 scramble을 포함한 구조화된 수치실험이다. "
        "가상 배치와 화염 곡선도 같은 물리 계산을 짝지어 비교한 것이므로 독립 사례로 세지 않는다.", "",
        "## 순위 안정성 결과", "",
        f"전체 기본 설계에서 두 관련 화염 곡선 사이 최고집합 변화는 {pct(min(changes))}–{pct(max(changes))}였다. "
        f"양쪽 곡선에서 적어도 하나의 도달관계가 존재한 조건으로 한정하면 {pct(min(active_changes))}–{pct(max(active_changes))}였다.", "",
        f"최적합 곡선의 무도달 비율은 {pct(min(fit_empty))}–{pct(max(fit_empty))}, 개발자료 상한곡선은 {pct(min(upper_empty))}–{pct(max(upper_empty))}였다. "
        "무도달을 임의의 1위로 바꾸지 않았고, 최고 점수 동률도 모두 보존했다.", "",
        "| 표본화 | 배치 | 기본행 | 최고집합 변화 | 양쪽 활성행 | 활성행 중 변화 | 양쪽 유일 1위 | 유일 1위 역전 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for measure, layout, row in ranks:
        lines.append(f"| {measure} | {layout} | {row['rows']} | {pct(row['priority_set_change_fraction'])} | "
                     f"{row['active_both_rows']} | {pct(row['priority_set_change_active_both_fraction'])} | "
                     f"{row['unique_both_rows']} | {row['unique_leader_reversal_rows']} |")
    lines += ["", "위 변화는 실제 사고확률이나 실제 시설에서의 순위 역전확률이 아니다. 선언한 가상 설계 범위에서 계산된 조건부 분율이다.", "",
              "## 민감도와 표본 수렴", "",
              f"도달관계 점수의 전역 민감도 지표 {len(edge_sensitivity)}개 중 "
              f"{sum(v['requires_more_samples'] for v in edge_sensitivity)}개가 예비 수렴 기준에서 추가 표본 필요로 표시됐다. "
              f"반면 질량유량·최대 화염 길이 지표 {len(continuous_sensitivity)}개는 모두 같은 기준을 통과했다.", "",
              "모든 배치·곡선·표본화 조합에서 배치 간격의 총효과 추정치가 도달관계 점수 변수 중 가장 컸다. "
              "이는 해당 가상 배치 범위의 결과이며 실제 시설의 보편적 중요도 순위가 아니다. 불연속 임계값 지표는 연속 물리량보다 표본 수렴이 느리므로, 다음 계산은 단순히 표본 수만 늘리기 전에 지표 정의를 먼저 보완해야 한다.", "",
              "## 정보 보강 결과의 제한", "",
              "Cd를 모르는 상태와 특정 Cd 또는 모든 Cd를 가상으로 정확히 알게 된 상태를 비교했다. 모든 Cd를 알아도 유일한 1위가 보장되지 않는 조건이 다수 남았다. "
              "남은 원인은 두 화염 곡선의 차이, 동률 및 무도달이다. 비용·손실함수·실측 사전분포가 없으므로 정식 Value of Information은 아니다.", "",
              "## 사용한 범위와 제외한 범위", "",
              "- 포함: GH2 직접홀 방출량, 0.5–10 mm 설계 구경, 10–70 MPa 공통 압력배율, 283.15–303.15 K, Cd 0.5–1.0 민감도, 공개 가상 배치 3종, Molkov 최적합/개발자료 상한곡선.",
              "- 제외: 미해결 가상 노즐, 분산과 LFL, 복사 22.7 문제, LH2, 시간의존 방출, 점화·누출 빈도, 기상·장애물·부력, 설비 취약도, 전체 QRA 및 운전 디지털 트윈 검증.",
              "- 두 Molkov 곡선은 같은 식의 관련 대안이며 독립 모델이나 보장된 안전 한계로 해석하지 않는다.",
              "- 구경의 로그/선형 표본화는 실제 확률분포가 아니라 결과의 설계가정 의존성을 확인하기 위한 두 측도다.", "",
              "## 검증", "",
              f"이번 전체 회귀검사는 {test_suite['tests']} passed, failures {test_suite['failures']}, errors {test_suite['errors']}, skipped {test_suite['skipped']}였다. "
              "별도 무변경 검사는 모든 산출물 체크섬, 전체 입력행, 방출원 면적×Cd 재사용, 모든 배치–곡선 도달관계 및 민감도 벡터를 원시행에서 재계산해 일치시켰다. "
              "이는 소프트웨어·데이터 무결성 증거이며 실험 검증이 아니다.", "",
              "생산 물리 코드, 기존 results.json 및 현재 원고는 변경하지 않았다. 새 통계 도구와 테스트, 별도 분석 의존성 파일 및 본 산출물 폴더만 추가했다.", "",
              "## 논문 판단", "",
              "이 결과만으로 PSEP 또는 JLPPI 논문이 완성되지는 않는다. 그러나 논문을 ‘대량 계산’ 자체가 아니라 ‘입력·모델·배치 조건에서 관리 판단이 언제 정의되고 안정적인가’로 전환할 근거는 확보했다. "
              "다음 본 계산은 (1) 무도달/동률을 결함으로 보지 않는 집합형 판단 지표, (2) 별도 미사용 배치군, (3) 공개 실험 적용범위 지도, (4) 수렴하지 않은 불연속 지표의 추가 scramble과 표본 수를 포함해야 한다.", "",
              "## 파일", "",
              "- `../논문/통계예비계산_20260901/통계예비계산_결과.md`: 생성된 상세 보고서와 그림",
              "- `../논문/통계예비계산_20260901/protocol.json`: 실행 전 범위·가정·코드 지문",
              "- `../논문/통계예비계산_20260901/summary.json`: 모든 표와 해석의 수치 원본",
              "- `../논문/통계예비계산_20260901/design_results.jsonl`: 전체 입력·출력행",
              "- `../논문/통계예비계산_20260901/artifact_hashes.json`: 산출물 체크섬",
              "- `../코드/statistical_pilot.py`: 계산·집계·그림 생성",
              "- `../코드/verify_statistical_pilot.py`: 읽기 전용 재검산",
              "- `../코드/test_statistical_pilot.py`: 통계·경계·무사용 경로 시험", ""]
    output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.result, args.tests, args.out)
