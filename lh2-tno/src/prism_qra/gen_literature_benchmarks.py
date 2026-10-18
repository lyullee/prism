#!/usr/bin/env python3
"""Generate auditable literature benchmark rows, metrics, and handoff note."""

from __future__ import annotations

import argparse
import csv
import io
import json
from dataclasses import asdict
from pathlib import Path

import literature_benchmarks as B
from validation_metrics import COLUMNS


QOI_ORDER = (
    "han_lfl_distance_m",
    "ruggles_inverse_centerline_mass_fraction",
    "ruggles_half_width_mm",
    "proust_mass_flow_g_s",
    "proust_mass_flow_line_loss_g_s",
    "proust_mass_flow_cd061_sensitivity_g_s",
    "proust_flame_molkov_fit_measured_flow",
    "proust_flame_delichatsios_measured_flow",
    "proust_flame_molkov_conservative_measured_flow",
    "proust_flame_molkov_fit_predicted_flow",
    "proust_flame_delichatsios_predicted_flow",
    "proust_flame_molkov_conservative_predicted_flow",
    "royle_unattached_flame_delichatsios_cd1_assumed_288k",
    "royle_unattached_flame_delichatsios_cd061_assumed_288k",
    "ekoto_source_mass_flow_kg_s",
    "ekoto_flame_molkov_fit_measured_flow",
    "ekoto_flame_delichatsios_measured_flow",
    "ekoto_flame_molkov_conservative_measured_flow",
)

QOI_LABELS = {
    "han_lfl_distance_m": "Han LFL 거리 / 현재 전체 사슬",
    "ruggles_inverse_centerline_mass_fraction": (
        "Ruggles 중심선 역질량분율 / Schefer 식 9"
    ),
    "ruggles_half_width_mm": "Ruggles 반폭 / Schefer 식 10",
    "proust_mass_flow_g_s": "Proust 질량유량 / 현재 sharp-hole 방출원",
    "proust_mass_flow_line_loss_g_s": (
        "Proust 질량유량 / 10 m 공급관+말단 방출원"
    ),
    "proust_mass_flow_cd061_sensitivity_g_s": (
        "Proust 질량유량 / 고정 Cd=0.61 민감도"
    ),
    "proust_flame_molkov_fit_measured_flow": (
        "Proust 화염 / 실측유량+Molkov 최적합"
    ),
    "proust_flame_delichatsios_measured_flow": (
        "Proust 화염 / 실측유량+Delichatsios"
    ),
    "proust_flame_molkov_conservative_measured_flow": (
        "Proust 화염 / 실측유량+Molkov 보수식"
    ),
    "proust_flame_molkov_fit_predicted_flow": (
        "Proust 화염 / 예측유량+Molkov 최적합"
    ),
    "proust_flame_delichatsios_predicted_flow": (
        "Proust 화염 / 예측유량+Delichatsios"
    ),
    "proust_flame_molkov_conservative_predicted_flow": (
        "Proust 화염 / 예측유량+Molkov 보수식"
    ),
    "royle_unattached_flame_delichatsios_cd1_assumed_288k": (
        "Royle 비부착 화염 / 가정 288 K+Cd=1"
    ),
    "royle_unattached_flame_delichatsios_cd061_assumed_288k": (
        "Royle 비부착 화염 / 가정 288 K+Cd=0.61"
    ),
    "ekoto_source_mass_flow_kg_s": "Ekoto 질량유량 / 현재 Cd=1 방출원",
    "ekoto_flame_molkov_fit_measured_flow": (
        "Ekoto 대형화염 / 실측유량+Molkov 최적합"
    ),
    "ekoto_flame_delichatsios_measured_flow": (
        "Ekoto 대형화염 / 실측유량+Delichatsios"
    ),
    "ekoto_flame_molkov_conservative_measured_flow": (
        "Ekoto 대형화염 / 실측유량+Molkov 보수식"
    ),
}


def _csv_text(rows) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))
    return stream.getvalue()


def _diagnostic_csv_text(rows: list[dict]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=list(rows[0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{100.0 * value:.1f}%"


def _markdown(summary: dict) -> str:
    metrics = summary["metrics_by_qoi"]
    decisions = summary["screening_by_qoi"]
    lines = [
        "# 19 - GH2 문헌 수치 벤치마크",
        "",
        "## 결론",
        "",
        "현재 코드의 방향성 풋프린트를 좌우하는 **반폭 식은 매우 잘 맞지만, "
        "중심선 농도감쇠는 Ruggles-Ekoto 조건에서 비보수적**이다. Han의 고압 "
        "LFL 거리 12점은 통과하므로 하나의 전역 보정계수를 즉시 적용할 근거는 "
        "없다. 압력·노즐 조건별 적용범위를 분리해야 한다.",
        "",
        "Proust 3 mm 화염은 실측 질량유량을 사용할 때 Delichatsios가 가장 "
        "정확하고 Molkov 최적합도 사전 기준을 통과한다. Molkov 보수식은 이름대로 "
        "상한 역할을 하며 평균 정확도 기준은 통과하지 못한다. 세 화염식의 외피는 "
        "실험점을 100% 포함한다.",
        "",
        "보고된 10 m, 내경 10 mm 공급관을 새 압력손실 모델에 넣어도 `Cd=1` "
        "질량유량 과대예측은 거의 해소되지 않는다. 고정 `Cd=0.61` 민감도는 "
        "screening을 통과하지만, 이를 원 장치의 검증된 계수로 해석할 수는 없다. "
        "남는 차이는 실제 제한부·노즐 형상·온도 측정위치와 질량시계열 미분 "
        "방법에서 확인해야 한다.",
        "",
        "Royle의 6.4·9.5 mm 시험과 Ekoto의 20.9 mm 시험을 추가해 직경 "
        "공백은 일부 해소했다. Ekoto 실측유량 기준 Delichatsios는 nRMSE "
        "5.6%로 통과한다. Royle은 온도·실측유량이 없고 제한부 길이도 본문 "
        "12 mm와 그림 20 mm가 충돌하므로 민감도 자료로만 유지한다. 어느 "
        "자료도 350--700 bar 설계압력과 직경을 동시에 덮지는 않는다.",
        "",
        "## 수치 결과",
        "",
        "사전 screening: |NMB| <= 20%, nRMSE <= 30%, FAC2 >= 0.90. 이는 "
        "연구팀 판정규칙이며 법정 허용기준이 아니다.",
        "",
        "| 비교 | n | NMB | nRMSE | MAPE | FAC2 | 모델외피 포함 | 판정 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for qoi in QOI_ORDER:
        row = metrics[qoi]
        decision = decisions[qoi]["passes_all"]
        lines.append(
            f"| {QOI_LABELS[qoi]} | {row['n']} | "
            f"{_percent(row['normalized_mean_bias'])} | "
            f"{_percent(row['normalized_rmse'])} | "
            f"{_percent(row['mean_absolute_percentage_error'])} | "
            f"{row['fraction_within_factor_two']:.3f} | "
            f"{_percent(row['model_envelope_coverage'])} | "
            f"{'PASS' if decision else 'FAIL'} |"
        )

    lines += [
        "",
        "## 해석",
        "",
        "1. **Ruggles 반폭:** NMB -2.4%, nRMSE 3.5%로 통과한다. 현재 "
        "점수는 그림의 가상원점 기준 기울기 비교다. 운영 함수의 원점·주변조건 "
        "변환을 해결하기 전에는 운영 농도장 검증으로 승격하지 않는다.",
        "2. **Ruggles 중심선:** 역질량분율 NMB +33.7%, nRMSE 34.0%로 "
        "실패한다. 역분율을 크게 예측한다는 것은 중심선 수소농도를 낮게, 따라서 "
        "가연거리도 짧게 예측할 수 있다는 뜻이다.",
        "3. **Han LFL 거리:** NMB +10.2%, nRMSE 11.3%로 통과한다. 다만 "
        "원 시험은 길이 30 mm의 작은 홀이고 현재 방출원은 sharp-hole이므로, "
        "정확한 방출원 검증과 농도감쇠 검증이 결합된 값이다.",
        "4. **Proust 질량유량:** `Cd=1` sharp-hole 보수경계는 평균 +80.1%, "
        "nRMSE 98.3%이고, 보고된 공급관을 연결해도 NMB +76.4%, nRMSE "
        "94.1%다. 공급관은 전체 평균편향 잔차의 4.6%만 설명한다. 고정 "
        "`Cd=0.61` 민감도는 NMB +9.9%, nRMSE 20.0%로 통과하지만 원문에 "
        "노즐 축방향 길이와 입구 형상이 없으므로 검증 판정이 아니다.",
        "5. **Proust 화염모델 분리평가:** 실측유량 기준 Delichatsios의 "
        "nRMSE는 10.5%, Molkov 최적합은 16.3%, Molkov 보수식은 31.2%다. "
        "Molkov 개발자료에 Proust/INERIS 계열이 포함되어 독립검증이 아니다. "
        "보수식은 개발자료의 상한 외피이며 보편적 안전상한이 아니다.",
        "6. **오차상쇄:** 예측유량+Molkov 최적합의 nRMSE 7.4%는 방출유량 "
        "과대예측과 화염길이 과소예측이 상쇄된 결과다. 이 수치를 개별 모델의 "
        "검증성능으로 인용하지 않는다.",
        "7. **Ekoto 대형화염:** 20.9·52.5 mm 실측유량 기준 Delichatsios "
        "nRMSE 5.6%, Molkov 최적합 20.5%로 통과한다. 이는 화염길이 구성요소 "
        "비교이며 방출원·분산 검증은 아니다. Molkov eq.8의 개발 지름 "
        "0.4–10.1 mm 밖에 있는 두 점의 외삽 확인으로 표시한다.",
        "8. **Royle 중구경 화염:** Cd=0.61 민감도는 통과하지만 누락된 "
        "온도·실측유량·형상 때문에 장치 검증으로 승격하지 않는다. 다만 "
        "6.4·9.5 mm에서 화염길이의 직경 추세를 점검하는 근거가 된다.",
        "",
        "## 논문에서 가능한 주장",
        "",
        "- Ruggles-Ekoto 그림 가상원점 기준 반폭 기울기 비교가 기준을 "
        "충족한다. 운영 함수와 좌표 연결이 미해결이고 식 9가 실패하므로 "
        "전체 방향성 풋프린트가 검증됐다고 주장하지 않는다.",
        "- 고압 소구경 LFL 거리는 Han 자료범위에서 사전 성능기준을 충족한다.",
        "- 3 mm 고압 화염에서 실측유량을 사용하면 Delichatsios와 Molkov "
        "최적합은 기준을 충족하고, 세 모델 외피는 관측을 모두 포함한다.",
        "- Proust 장치의 보고된 공급관 마찰을 명시적으로 반영해도 `Cd=1` "
        "질량유량 잔차는 유지되므로, 공급관 길이 누락을 주된 불일치 원인으로 "
        "지목하지 않는다.",
        "- `Cd=0.61`은 사전에 선언한 민감도 경계로 screening을 통과한다. "
        "원 장치의 측정 계수 또는 독립검증값이라고 주장하지 않는다.",
        "- 시스템은 모델형식 외피와 적용범위 이탈을 명시적으로 관리한다.",
        "- 실측유량을 사용한 Delichatsios 화염길이는 Ekoto 20.9·52.5 mm "
        "두 대형시험에서 사전 기준을 충족했다.",
        "",
        "다음 주장은 아직 불가능하다: 6--25 mm와 350--700 bar를 동시에 "
        "만족하는 설계 누출의 독립 전체사슬 검증, "
        "액화수소 인수기지 전체의 절대위험도 검증, Proust 조건에서의 특정 `Cd` "
        "또는 공급관 결합 방출원 검증.",
        "",
        "## 재현성과 한계",
        "",
        f"- 총 {summary['n_rows']}개의 reference-versus-prediction 행을 "
        "`코드/literature_benchmark_observations.csv`에 기록했다.",
        "- 원 마커 좌표, 축 보정점, Proust Table 1 온도, Figure 5 유량과 "
        "Figure 8 화염점은 `코드/literature_benchmarks.py`에 보존했다.",
        "- 그래프 디지털화 자료는 원 계측파일보다 낮은 등급이다. Proust 화염의 "
        "논문상 불확도는 +/-0.20 m이며, 나머지 그래프 판독 오차는 조건 메모에 "
        "별도로 남겼다.",
        "- Proust의 64개 화염점은 한 blowdown의 시계열 표본이지 64개 독립 "
        "실험이 아니다. 표본수를 독립 반복수처럼 해석하지 않는다.",
        "- 화염길이의 직경 축은 Royle 6.4·9.5 mm와 Ekoto 20.9 mm까지 "
        "확장됐다. 그러나 설계사례의 350--700 bar 압력과 공동으로 겹치는 "
        "자료가 없어 전체사슬 관점에서는 여전히 외삽이다.",
        "- 공급관 모델은 정상·등온·일정내경·저 Mach GH2만 다룬다. 배관 내 "
        "재고의 시간변화, 열전달, Fanno choking, 2상 유동은 검증범위 밖이다.",
        "- 후속 2021 모델은 Proust의 실제 노즐 상세가 없어 다른 시험장치와 "
        "유사한 5 mm 길이 노즐 구성을 가정했다. 후속 계산은 원 장치 형상의 "
        "독립 확인자료가 아니다.",
        "",
        "## 출처",
        "",
        f"- {B.SANDIA_SOURCE}",
        f"- {B.PROUST_SOURCE}",
        f"- {B.VENETSANOS_SOURCE}",
        f"- {B.ROYLE_SOURCE}",
        f"- {B.EKOTO_SOURCE}",
    ]
    return "\n".join(lines) + "\n"


def _residual_markdown(summary: dict, rows: list[dict]) -> str:
    residual = summary["proust_source_residual"]
    fixed = summary["metrics_by_qoi"][
        "proust_mass_flow_cd061_sensitivity_g_s"
    ]
    fitted = residual["fitted_constant_cd_metrics"]
    lines = [
        "# 20 - Proust 방출원 잔차 진단",
        "",
        "## 판정",
        "",
        "현재 `Cd=1` 결과는 **보수경계**로는 유지할 수 있지만 평균 정확도 "
        "검증에는 실패한다. `Cd=0.61` 고정 민감도는 사전 screening을 통과하지만, "
        "원 장치의 계수로 확인된 값이 아니므로 검증 통과로 승격하지 않는다.",
        "",
        "압력별 역산 `Cd`가 일정하지 않고, 보고된 배관만으로 관측유량을 만들려면 "
        "통상 피팅 손실보다 훨씬 큰 등가 부차손실이 필요하다. 우선순위는 "
        "추가 배관마찰 정교화보다 노즐 도면·원시 질량시계열·미분 절차 확보이다.",
        "",
        "## 핵심 수치",
        "",
        f"- 고정 Cd=0.61: NMB {_percent(fixed['normalized_mean_bias'])}, "
        f"nRMSE {_percent(fixed['normalized_rmse'])}, FAC2 "
        f"{fixed['fraction_within_factor_two']:.3f}.",
        f"- 같은 13점에 최소제곱 적합한 Cd: "
        f"{residual['fitted_constant_cd_same_series']:.3f}; NMB "
        f"{_percent(fitted['normalized_mean_bias'])}, nRMSE "
        f"{_percent(fitted['normalized_rmse'])}. 이는 calibration 성능이다.",
        f"- 압력별 유효 Cd: {residual['effective_cd_direct_min']:.3f}--"
        f"{residual['effective_cd_direct_max']:.3f}.",
        f"- nominal 3 mm에 대한 등가 구경: "
        f"{residual['equivalent_orifice_diameter_mm_min']:.2f}--"
        f"{residual['equivalent_orifice_diameter_mm_max']:.2f} mm.",
        f"- 보고 배관의 잔차 설명률: "
        f"{_percent(residual['reported_line_residual_explained_fraction'])}.",
        f"- Cd=1을 고정한 등온 10 mm 배관 역산 등가 부차손실 K: "
        f"{residual['required_equivalent_minor_loss_k_min']:.0f}--"
        f"{residual['required_equivalent_minor_loss_k_max']:.0f}.",
        "",
        "## 압력별 역산",
        "",
        "| P (bar) | 실측 (g/s) | Cd=1 (g/s) | 배관+Cd=1 (g/s) | "
        "유효 Cd | 등가 d (mm) | 필요 등가 K |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['pressure_bar']:.0f} | {row['measured_g_s']:.3f} | "
            f"{row['direct_cd1_g_s']:.3f} | "
            f"{row['reported_line_cd1_g_s']:.3f} | "
            f"{row['effective_cd_direct']:.3f} | "
            f"{row['equivalent_orifice_diameter_mm']:.2f} | "
            f"{row['required_equivalent_minor_loss_k']:.0f} |"
        )
    lines += [
        "",
        "## 원인 가설 우선순위",
        "",
        "1. **실제 교환식 노즐의 내부 형상·제한구경 미상:** 원 논문 사진은 "
        "얇은 오리피스판보다 두꺼운 삽입형 노즐을 보여 주지만 길이, 입구 수축, "
        "모따기와 거칠기를 보고하지 않는다. 가장 먼저 도면/제작기록을 확보한다.",
        "2. **질량유량 산출 절차 미상:** 유량은 직접 유량계가 아니라 ±10 g "
        "저울의 탱크질량 시계열을 미분해 얻었다. 필터, 미분창, 압력 동기화와 "
        "원시 시계열이 없으므로 곡선점들은 독립 반복시험이 아니다.",
        "3. **노즐 직전 상태의 시간변화:** 원문은 밸브 개방 직후 잔류 공기 "
        "압축 온도피크를 보고한다. 이후 탱크와 노즐 직전 온도는 유사하지만, "
        "현 모델의 정상·등온 가정은 초기 과도와 벽 열용량을 재현하지 않는다.",
        "4. **보고 공급관 마찰:** 이미 반영했으며 전체 잔차의 약 4.6%만 "
        "설명한다. 추가 정교화는 위 세 자료가 확보된 뒤 진행한다.",
        "",
        "## 시스템 적용 규칙",
        "",
        "- 기본 Cd=1은 그대로 두고 보수경계라고 표시한다.",
        "- Cd<1 입력에는 `ENGINEERING_ASSUMPTION`, `MANUFACTURER_CERTIFIED`, "
        "`MEASURED`, `CALIBRATED` 중 근거와 출처/시험 메모를 의무화한다.",
        "- `CALIBRATED`는 해당 자료에 대한 독립검증으로 주장할 수 없도록 "
        "provenance에 자동 기록한다.",
        "- 실제 설비 적용은 제조사 유량계수/용량인증 또는 별도 방출시험이 "
        "없으면 Cd=1 본 결과와 선언된 Cd 민감도 결과를 함께 제시한다.",
        "",
        "## 출처와 한계",
        "",
        f"- {B.PROUST_SOURCE}",
        f"- {B.VENETSANOS_SOURCE}",
        "- 후속 2021 계산은 Proust의 실제 노즐 상세가 없어 유사 구성을 "
        "가정했다. 이를 원 장치 형상의 확인자료로 사용하지 않았다.",
        "- 등가 K는 Cd=1과 현재 정상·등온 10 mm 배관모델을 강제로 유지한 "
        "역산 진단이다. 실제 국부손실계수 측정값이 아니다.",
    ]
    return "\n".join(lines) + "\n"


def _write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"generated artifact drift: {path}")
        return
    path.write_text(content, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if generated files drift"
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    rows = B.observations()
    summary = B.metric_summary(rows)
    diagnostics = B.proust_source_residual_diagnostics()
    outputs = {
        root / "코드" / "literature_benchmark_observations.csv": _csv_text(rows),
        root / "코드" / "literature_benchmark_summary.json": json.dumps(
            summary, indent=2, ensure_ascii=False
        ) + "\n",
        root / "핸드오프" / "19_LITERATURE_BENCHMARKS.md": _markdown(summary),
        root / "코드" / "proust_source_residual_diagnostics.csv": (
            _diagnostic_csv_text(diagnostics)
        ),
        root / "핸드오프" / "20_PROUST_SOURCE_RESIDUAL.md": (
            _residual_markdown(summary, diagnostics)
        ),
    }
    for path, content in outputs.items():
        _write_or_check(path, content, args.check)
    verb = "checked" if args.check else "wrote"
    print(f"{verb} {len(outputs)} benchmark artifacts: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
