#!/usr/bin/env python3
"""Generate the literature validation and applicability matrix."""

from __future__ import annotations

from pathlib import Path

import validation_matrix as V


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    target = root / "핸드오프" / "17_VALIDATION_MATRIX.md"
    lines = [
        "# 17 - GH2 experimental validation matrix",
        "",
        "This matrix distinguishes an identified dataset from a numerical ",
        "benchmark and from validation of this implementation. Its primary ",
        f"routing source is {V.SANDIA_REPORT}.",
        "",
        "| phenomenon | source | conditions | quantity | finding | status |",
        "|---|---|---|---|---|---|",
    ]
    for row in V.EVIDENCE:
        clean = [getattr(row, name).replace("|", "\\|") for name in
                 ("phenomenon", "source", "conditions", "quantity",
                  "finding", "status")]
        lines.append("| " + " | ".join(clean) + " |")

    lines += [
        "", "## Design-case coverage", "",
        "| d (mm) | P (bar) | LFL-distance evidence | flame evidence |",
        "|---:|---:|---|---|",
    ]
    for d_mm, p_bar in V.DESIGN_CASES:
        lines.append(
            f"| {d_mm:g} | {p_bar:g} | "
            f"{V.dispersion_joint_coverage(d_mm, p_bar)} | "
            f"{V.flame_joint_coverage(d_mm, p_bar)} |")

    lines += [
        "", "## Priority actions", "",
        "1. Obtain the original Ruggles-Ekoto and Han machine-readable data "
        "to replace graph digitizations and retain instrument uncertainty.",
        "2. The Proust feed-pipe source term is implemented, but the reported "
        "10 m pipe changes flow only slightly and does not close the residual. "
        "A fixed Cd=0.61 sensitivity passes but is not apparatus validation. "
        "Obtain original tank-mass time-series data, its differentiation method "
        "and nozzle/restriction geometry.",
        "3. Ekoto Table 1 conditions are now implemented: measured-flow "
        "Delichatsios and Molkov-fit flame lengths pass at 20.9 and 52.5 mm. "
        "Digitize the detector geometry and heat flux next.",
        "4. Royle 6.4/9.5 mm and Ekoto 20.9 mm reduce the diameter-only gap, "
        "but no public test jointly matches the 350-700 bar design range. "
        "Treat the design cases as pressure-diameter extrapolations until "
        "commissioning or a matched independent test exists.",
        "5. See `19_LITERATURE_BENCHMARKS.md` for the completed Han, "
        "Ruggles-Ekoto and Proust numerical scores, including the rejected "
        "feed-pipe-loss explanation, and `20_PROUST_SOURCE_RESIDUAL.md` for "
        "the pressure-resolved inverse audit.",
        "", "## Numeric benchmark already available", "",
        "Sandia Table 3-4 provides measured and HyRAM+ values for the two "
        "Ekoto tests. This implementation is now separately scored for "
        "source mass flow and measured-flow flame length. The ratios below "
        "remain contextual HyRAM+ comparisons.",
        "", "| quantity | HyRAM+ / measured |", "|---|---:|",
    ]
    for key, value in V.ekoto_hyram_ratios().items():
        lines.append(f"| {key} | {value:.4f} |")

    lines += ["", "## Required next action by evidence row", ""]
    for row in V.EVIDENCE:
        lines.append(f"- **{row.source} / {row.quantity}:** {row.next_action}")

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}: {len(V.EVIDENCE)} evidence rows")


if __name__ == "__main__":
    main()
