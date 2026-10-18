"""Generate handoff 29 from verified synthetic-transfer artifacts."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import set_valued_decision as D
import statistical_pilot as S
import statistical_transfer as T


def percent(value: float) -> str:
    return f"{value:.1%}"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "논문" / "통계전이평가_20260901"
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    counts = summary["counts"]
    unknown, known = Counter(), Counter()
    with (output / "decision_results.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            for decision in row["decisions"].values():
                unknown[decision["retained_cd_curve_uncertainty"]["category"]] += 1
                known[decision["all_cd_known_curve_uncertainty_retained"]["category"]] += 1
    total_decisions = sum(unknown.values())
    edge = {key: value for key, value in summary["sensitivity"].items()
            if "|edges:" in key}
    continuous = {key: value for key, value in summary["sensitivity"].items()
                  if "|edges:" not in key}
    supported_edges = sum(v["exploratory_convergence_supported"] for v in edge.values())
    supported_continuous = sum(v["exploratory_convergence_supported"]
                               for v in continuous.values())
    spacing_consensus = sum(v["dominant_total_effect_consensus"] == "spacing_m"
                            and v["dominant_total_effect_consensus_fraction"] == 1.
                            for v in edge.values())

    category_iqr = []
    robust_unique_medians = []
    top_changes = []
    active_changes = []
    for measure in S.MEASURES:
        for layout in T.ALL_LAYOUTS:
            decision = summary["set_valued"][measure][layout]
            robust_unique_medians.append(
                decision["category_fraction_median"]["ROBUST_UNIQUE"])
            for category in D.CATEGORIES:
                category_iqr.append(
                    decision["category_fraction_q75"][category]
                    - decision["category_fraction_q25"][category])
            rank = summary["rank"][measure][layout]
            top_changes.append(rank["priority_set_change_fraction"]["median"])
            conditional = rank["priority_set_change_active_both_fraction"]
            if conditional:
                active_changes.append(conditional["median"])

    lines = [
        "# 29 — 집합형 관리판단·가상배치 전이평가 (2026-09-01)", "",
        "## 결론", "",
        "최고 점수 설비 하나를 강제로 고르는 기존 표현을 보완해, Cd 구간과 두 관련 화염곡선에서 가능한 상관 점수벡터를 정확히 보존하는 집합형 관리판단을 구현했다. 결과는 무도달, 항상 유일 최고, 항상 동일 동률집합, 무도달 포함 판단 불가, 활성 상태 판단 불가를 구분한다.", "",
        "기존 3개 분석 배치에 더해 예비계산 이후 선택하되 출력 계산 전에 고정한 새 가상 배치 3개와 새 Sobol scramble 6개를 평가했다. 이는 내부 수치 전이평가이며 외부 실험검증, 실제 설비 검증 또는 운전 디지털 트윈 검증이 아니다.", "",
        "## 계산 규모", "", "| 구분 | 수 |", "|---|---:|",
        f"| 각 scramble 기본 표본 | {counts['base_n_per_scramble']:,} |",
        f"| 전체/신규 독립 scramble | {counts['total_scrambles']} / {counts['new_scrambles']} |",
        f"| 설계 표본화 방식 | {counts['design_measures']} |",
        f"| 입력 변수 | {counts['parameters']} |",
        f"| 기존 분석/신규 전이 가상배치 | {counts['analysis_layouts']} / {counts['transfer_layouts']} |",
        f"| 신규 고유 열역학 상태 | {counts['new_thermodynamic_source_states']:,} |",
        f"| 신규 pick-freeze 입력행 | {counts['new_pick_freeze_rows']:,} |",
        f"| 집합형 기본행 | {counts['set_valued_base_rows']:,} |",
        f"| 집합형 배치판단 | {counts['set_valued_layout_evaluations']:,} |",
        f"| 신규 방출원 실패 | {counts['new_source_failures']} |",
        f"| 독립 물리실험 추가 | {counts['independent_physical_experiments_added']} |", "",
        "## 집합형 판단이 바꾼 해석", "",
        f"Cd와 곡선 불확실성을 유지한 전체 {total_decisions:,}개 배치판단 중 항상 유일 최고는 {unknown['ROBUST_UNIQUE']:,}개({percent(unknown['ROBUST_UNIQUE']/total_decisions)})뿐이었다. 무도달은 {percent(unknown['ALL_NO_REACH']/total_decisions)}, 무도달 포함 판단 불가는 {percent(unknown['INDETERMINATE_WITH_NO_REACH']/total_decisions)}, 활성 상태 판단 불가는 {percent(unknown['INDETERMINATE_ACTIVE']/total_decisions)}, 항상 같은 동률집합은 {percent(unknown['ROBUST_TIED_SET']/total_decisions)}였다.", "",
        f"모든 Cd를 정확히 안다고 가정해도 두 관련 곡선을 유지하면 항상 유일 최고는 {percent(known['ROBUST_UNIQUE']/total_decisions)}에 그쳤다. 즉 인증 Cd 확보는 중요하지만 곡선 차이·동률·무도달을 단독으로 제거하지 못한다.", "",
        f"배치·표본화별 항상 유일 최고 비율 중앙값 범위는 {percent(min(robust_unique_medians))}–{percent(max(robust_unique_medians))}였다. 집합형 범주 비율의 8개 scramble 최대 IQR은 {percent(max(category_iqr))}여서, 직접 범주분율은 불연속 Sobol 지수보다 훨씬 안정적이었다.", "",
        "집합형 판단은 설비별 가능한 최고집합의 합집합과 모든 허용상태에서 공통인 교집합을 함께 저장한다. 상관된 점수벡터를 보존한 pairwise robust outranking도 계산하므로 설비별 독립 최소·최대 구간으로 바꾸며 생기는 잘못된 조합을 만들지 않는다.", "",
        "## 새 가상배치로의 전이", "",
        f"분석/전이 배치 전체에서 fit↔development-upper 최고집합 변화의 scramble 중앙값은 {percent(min(top_changes))}–{percent(max(top_changes))}였다. 양쪽 곡선이 모두 활성인 조건만 보면 {percent(min(active_changes))}–{percent(max(active_changes))}였다.", "",
        "새 배치에서도 곡선 선택에 따른 최고집합 변화가 사라지지 않았다. 특히 cluster_remote는 다른 배치보다 도달 활성과 판단 불명확성이 크게 증가했다. 이는 결론이 단순 직선/밀집 배치에만 생긴 인공물이 아님을 보여주지만, 동시에 관리판단이 배치기하에 강하게 조건부임을 보여준다.", "",
        "## 추가 scramble과 수렴성", "",
        f"연속 지표 4개 중 {supported_continuous}개가 사전 선언한 탐색적 수렴 기준을 통과했다. 불연속 edge-count 지표 {len(edge)}개 중에는 {supported_edges}개만 통과했다.", "",
        f"edge-count 지표 {spacing_consensus}/{len(edge)}개에서 spacing이 모든 8개 scramble의 최대 총효과 변수였다. 이 정성적 순서는 강하게 반복됐지만, 개별 Sobol 총효과 크기는 N=128→256 변화가 커서 대부분 아직 논문의 정밀 정량결론으로 쓰면 안 된다.", "",
        "따라서 다음 계산은 두 갈래다. 집합형 범주분율과 곡선별 최고집합 변화는 현재 8개 scramble 자료를 주결과로 사용할 수 있다. 반면 불연속 edge-count Sobol 수치는 N=512 이상을 새 순차 프로토콜로 고정해 재평가하거나, 부록의 탐색결과로 낮춰야 한다.", "",
        "## 검증", "",
        "읽기 전용 검증에서 신규 열역학 상태 24,576개, 신규 설계행 39,936개, 저장된 배치×곡선 관계 479,232개, 집합형 판단 49,152개, 민감도 레코드 1,344개를 확인했다. 방출원 실패는 0건이었다. 상태는 `VERIFIED_SOFTWARE_AND_DATA_INTEGRITY_ONLY`이며 실험검증은 false다.", "",
        "최종 전체 회귀시험은 436 passed, failures/errors/skips 0, 의도된 ScopeWarning 1건이었다. 경고는 0.3 m/s가 SLABX 검증범위 [0.5, 12] m/s 밖임을 드러내는 기존 범위 시험이다.", "",
        "생산 물리 코드, 기존 results.json, 현재 원고 및 통계 예비계산 산출물은 변경하지 않았다. 이번 계산은 별도 코드·테스트·출력 폴더로 격리했다.", "",
        "## 논문 스토리의 현재 형태", "",
        "가장 방어 가능한 스토리는 ‘대규모 사례를 계산했다’가 아니다. `전임상/구축단계 수소 설비 디지털 트윈에서 물리모델과 입력 불확실성을 단일 허위정밀 순위로 축약하지 않고, 집합형 관리검토 후보로 전달하는 방법`이다.", "",
        "주결과는 (1) 항상 유일 최고가 드물다는 정량증거, (2) Cd를 알아도 곡선·동률·무도달 때문에 판단 불명확성이 남는다는 분해, (3) 새 기하에서도 곡선민감성이 반복되지만 크기는 배치에 따라 달라진다는 전이 결과, (4) 직접 범주분율은 안정적인 반면 불연속 Sobol 지수는 추가 N이 필요하다는 수렴 진단이다.", "",
        "이 스토리는 검증완료 디지털 트윈 논문이 아니라, 구축단계의 불확실성 보존형 안전 의사결정지원 방법론 논문이다. 공개 실험 비교와 기존 모델 적용범위 지도는 여전히 필요하고, M01 가상노즐·분산/LFL·복사·LH2/M02·과도 결합·취약도는 해결되지 않았다.", "",
        "## 파일", "",
        "- `../논문/통계전이평가_20260901/집합형_전이평가_결과.md`: 생성된 상세 보고서와 그림",
        "- `../논문/통계전이평가_20260901/protocol.json`: 결과 전 고정한 배치·scramble·판단정의·수렴기준",
        "- `../논문/통계전이평가_20260901/summary.json`: 표와 그림의 수치 원본",
        "- `../논문/통계전이평가_20260901/new_design_results.jsonl`: 새 scramble 전체 입력·출력행",
        "- `../논문/통계전이평가_20260901/decision_results.jsonl`: 집합형 판단 원시행",
        "- `../논문/통계전이평가_20260901/artifact_hashes.json`: 산출물 체크섬",
        "- `../코드/set_valued_decision.py`: 정확 집합형 판단",
        "- `../코드/statistical_transfer.py`: 전이·scramble 계산과 보고서 생성",
        "- `../코드/verify_statistical_transfer.py`: 읽기 전용 전수 재검산",
        "- `../코드/test_set_valued_decision.py`, `../코드/test_statistical_transfer.py`: 경계·불변조건 시험", "",
    ]
    (root / "핸드오프" / "29_SET_VALUED_TRANSFER_20260901.md").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
