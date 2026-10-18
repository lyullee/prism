#!/usr/bin/env python3
"""Regenerates VERIFICATION.md from the code. Never edit that file by hand."""

import json
from pathlib import Path
import warnings

import fire as F
import gh2_jet as G
import taxonomy as T
import uncertainty as U

warnings.filterwarnings("ignore")

out = []
p = out.append
p("# Verification backlog\n")
p("Generated from the code by gen_verification.py. An item leaves this list")
p("when its value is read from source, not when someone decides it is")
p("probably fine. Do not edit by hand.\n")
p("**Audit qualification (2026-08-31):** source transcription alone does not")
p("close model validation. The current pipeline is engineering screening,")
p("not validated facility acceptance. Remaining energy/phase, radiation and")
p("runtime evidence-gate issues are tracked in `26_AUDIT_FIX_STATUS_20260831.md`.\n")

c = [
    e
    for e in T.FREQUENCY_LIBRARY.values()
    if e.provenance.transcription is T.TranscriptionSource.CODE_INSPECTION
]
u = [
    e
    for e in T.FREQUENCY_LIBRARY.values()
    if e.provenance.transcription is T.TranscriptionSource.UNVERIFIED
]
cv = U.coverage()
p("## 1. Leak frequencies\n")
p(f"- observed in software, not read: **{len(c)}**")
p(f"- no source at all: **{len(u)}** ({', '.join(e.primitive.value for e in u)})")
p(f"- carrying a published distribution: **{cv['with_distribution']}/{cv['entries']}**")
p(
    f"- components with no frequency in any fuel: **{len(T.NO_DATA)}** "
    f"({', '.join(sorted(x.value for x in T.NO_DATA))})\n"
)

p("## 2. Coefficients still unread\n")
p("| module | symbol | value | reference |")
p("|---|---|---|---|")
for m, nm in ((F, "fire"), (G, "gh2_jet")):
    for x in m.NEEDS_SOURCE_LIST:
        p(f"| {nm} | {x.symbol} | {x.value:g} | {x.reference[:64]} |")
p("")

p("## 3. Independent comparison against published LH2 station QRA\n")
p("| axis | outcome |")
p("|---|---|")
p(
    "| ignition probabilities vs Yoo et al. (2021) Table 10 | identical; both cite Sandia |"
)
p(
    "| LH2 vessel catastrophic rupture | 1.20e-6 against 2.00e-6, a factor of 0.60, and their value falls inside the 5th-95th interval |"
)
p("| LH2 pipe rupture | 6.38e-6 against 7.40e-6, a factor of 0.86 |")
p("| dominant scenario | both give catastrophic rupture of the LH2 tank |")
p(
    "| incident coverage, Sakamoto et al. (2016) | flange, valve and seal leakage is 14 of 21 Japanese incidents and is enumerated |"
)
p("")
p("An initial comparison showed a factor of 412 on the storage tank. That was")
p("a comparison error here: the published figure is catastrophic rupture alone")
p("and it was being set against the sum over all five leak size bins. Like for")
p("like it is 0.60.\n")

p("## 4. Empirical ignition rates\n")
try:
    import hiad as _H

    _lo, _hi = _H.lh2_range()
    p("HIAD 2.2, 1,142 recorded events, the first empirical figure this")
    p("project has on its largest single uncertainty.\n")
    p("| set | ignited | unignited | rate |")
    p("|---|---|---|---|")
    for _r in (_H.LH2, _H.GH2, _H.VENT_RELATED_LH2, _H.VACUUM_RELATED):
        p(f"| {_r.label} | {_r.ignited} | {_r.unignited} | {_r.rate * 100:.1f}% |")
    p("")
    p("Liquid hydrogen ignites about half as often as gaseous: a ratio of")
    p(f"{_H.lh2_over_gh2():.2f} overall and {_H.lh2_over_gh2(True):.2f} at")
    p("quality grade 4 or better. **Neither ignition scheme in use")
    p("represents that**, because both are indexed on release rate alone.\n")
    p(f"The LH2 rate rises from {_lo * 100:.1f}% at quality grade 2 to")
    p(f"{_hi * 100:.1f}% at grade 5, which is what reporting bias looks like:")
    p("better documented events are more often ignited ones. It is")
    p("therefore carried as a range, and the LH2 to GH2 ratio is the more")
    p("robust quantity because whatever bias applies, applies to both.\n")
    p("This is a CONDITIONAL rate and not a frequency. There is no")
    p("denominator of facility-years, and JRC states the database could")
    p("not meet its goal of serving quantitative risk assessment for lack")
    p("of statistics.\n")
except Exception as _e:
    p(f"_(HIAD summary failed: {_e})_\n")

p("### How the schemes in use compare\n")
try:
    from ignition import (
        IgnitionScheme as _IS,
        ReleaseType as _RT,
        build_ignition_tree as _bit,
    )

    p("| scheme | probability | against the recorded LH2 range |")
    p("|---|---|---|")
    for _l, _q, _s, _d in [
        ("HYRAM, smallest band", 0.06, _IS.HYRAM, None),
        ("HYRAM, largest band", 60.0, _IS.HYRAM, None),
        ("PURPLE method A, quiet site", 6.08, _IS.PURPLE_SOURCES, 0.10),
        ("PURPLE free field bound", 6.08, _IS.PURPLE, None),
    ]:
        _p = _bit(_RT.CONTINUOUS, _q, _s, delayed_conditional=_d).p_ignited
        _c = _H.check_scheme(_s.value, _p, "LH2")
        _w = (
            "inside"
            if _c.within_recorded_range
            else ("above" if _p > _c.recorded_high else "below")
        )
        p(f"| {_l} | {_p:.3f} | {_w}, {_c.ratio_to_midpoint:.2f}x the midpoint |")
    p("")
    p("Only HyRAM's largest band lands inside. Its smaller bands are an")
    p("order of magnitude below and the free field bound is above")
    p("everywhere, so no scheme in use matches the record across its")
    p("whole range.\n")
    p("The comparison is reported with every result and is NOT applied as")
    p("a correction. Scaling a scheme by the recorded ratio would treat a")
    p("quantity conditional on a release being REPORTED as if it were")
    p("conditional on one OCCURRING, and would assume the rate dependence")
    p("is the same in both phases, which nothing here tests.\n")
except Exception as _e:
    p(f"_(scheme comparison failed: {_e})_\n")

p("## 5. The highest-value outstanding data task\n")
p("Yoo et al. (2021) assign the cryogenic pump 5.0e-5/yr for catastrophic")
p("rupture, citing their reference [60]. Jiepu et al. (2026) independently")
p("classify the booster-pump system as the dominant risk unit at a 5 mm leak,")
p("with public individual risk outside the station boundary exceeding the")
p("criterion. PUMP_SEAL is the only unsourced row in this library.")
p("**The component most likely to dominate the answer carries the weakest")
p("evidence in it.** Tracing Yoo reference [60] is worth more than any")
p("remaining physics work.\n")

p("## 6. What actually moves the answer\n")
p("Sensitivity on the reference site, each item perturbed to the")
p("alternative the disagreement is with, one at a time. Ratios are")
p("alternative over baseline on maximum individual risk and on risk")
p("integrated over the grid.\n")
try:
    _registered = json.loads(
        (Path(__file__).resolve().parent.parent / "results.json").read_text(
            encoding="utf-8"
        )
    )["results"]
    _sh = {
        key.rsplit(".", 1)[-1]: item["value"]
        for key, item in _registered.items()
        if key.startswith("sens.outcome_share.")
    }
    p(
        "Risk here is carried by: "
        + ", ".join(f"{k} {v * 100:.0f}%" for k, v in _sh.items())
        + ".\n"
    )
    p("| item | max IR | integrated | verdict |")
    p("|---|---|---|---|")
    _keys = sorted(
        {
            key.removeprefix("sens.").removesuffix(".max_ir_ratio")
            for key in _registered
            if key.startswith("sens.") and key.endswith(".max_ir_ratio")
        }
    )
    for key in _keys:
        ratio = _registered[f"sens.{key}.max_ir_ratio"]["value"]
        integrated = _registered[f"sens.{key}.integrated_ratio"]["value"]
        d = max(ratio, 1.0 / max(ratio, 1e-12))
        v = "dominant" if d >= 2 else ("material" if d >= 1.2 else "minor")
        p(f"| {key} | {ratio:.2f} | {integrated:.2f} | {v} |")
    p("")
    p("Three of these read as insensitive on the first attempt because the")
    p("perturbation never ran: one patched a constant already bound as a")
    p("default argument, one changed a label where both branches route to")
    p("the same physics, and one was masked by a memoised dispersion")
    p("result. A clean ratio of 1.00 is ambiguous and is now asserted")
    p("against in the test suite.\n")
    p("Sensitivity is not error. An item that moves nothing here is")
    _flash_share = _sh.get("FLASH_FIRE", 0.0) * 100.0
    p(
        f"unimportant to THIS component mix, not correct. On this site "
        f"{_flash_share:.0f}% of"
    )
    p("the risk is flash fire, so the fireball, flame length and radiant")
    p("fraction items cannot move it whatever their state.\n")
except Exception as _e:
    p(f"_(sensitivity run failed: {_e})_\n")

p("## 7. Assumptions with no source\n")
p("| quantity | status |")
p("|---|---|")
p(
    "| pump seal frequency | see above; OREDA named by published QRA, subscription only |"
)
p("| assembly compositions | which primitives and how many, assumed |")
p(
    "| VJ liquid fraction | one point from one recorded incident; should be swept 0.0 to 0.45 |"
)
p("")

p("## 8. Widest published intervals\n")
p("| component | fuel | bin | 5th | median | 95th | span |")
p("|---|---|---|---|---|---|---|")
rows = []
for (pr, f), e in T.FREQUENCY_LIBRARY.items():
    if not e.sigma:
        continue
    for i, lab in enumerate(T.BIN_LABELS):
        lo, hi = e.percentile(0.05)[i], e.percentile(0.95)[i]
        rows.append((hi / lo, pr.value, f.value, lab, lo, e.medians[i], hi))
for sp, pr, f, lab, lo, md, hi in sorted(rows, reverse=True)[:4]:
    p(f"| {pr} | {f} | {lab} | {lo:.1e} | {md:.1e} | {hi:.1e} | {sp:,.0f}x |")
p("")

p("## 9. Not propagated\n")
for s in U.NOT_PROPAGATED:
    p(f"- {s}")
p("")

p("## 10. Declared gaps\n")
p("- **Density ratio 0.60 to 1.00.** Too heavy for the jet correlation to be")
p("  interpolation, too light to be a dense gas.")
p("- **Exchanger, vaporizer, arm.** No published frequency in any fuel;")
p("  Sandia marks them infinite rather than estimating them.")
p("- **Vent stack** as a primitive. Decomposed into the relief devices that")
p("  feed it, and kept as a no-data row so its absence stays visible.")
p("- **Leakage III**, human error and external impact. Component enumeration")
p("  cannot reach it; Purple Book chapter 3 shares this limitation and")
p("  declares it the same way.")
p("- **Premixing inside a vent tube.** At Emeryville the premixed gas")
p("  ignited with a loud boom before the jet flame established. The primary")
p("  report does not establish detonation. The release is now enumerated;")
p("  the internal premixed combustion/explosion is not modelled.")
p("- **Pool fire.** The ignition tree branches to it; cryogenic burning rate")
p("  and surface emissive power are not established.")
p("- **Jacket brittle fracture and fragment throw** after loss of vacuum.")
p("  EIGA TB 11/20 records the mechanism on a nitrogen tank; it is a")
p("  transferable cryogenic analogue, not LH2 validation.")
p("- **Blast decay.** Refused; the Baker curves are figures.")
p("")

p("## 11. Unresolved against cross-checks\n")
p(f"- Molina radiant fraction residual, factor {float(F.MOLINA_UNEXPLAINED_FACTOR):g}.")
p("- Molkov and Delichatsios remain different model choices; this is not a")
p("  same-correlation implementation mismatch.")
p("")
p("## 12. Resolved source-reading defects\n")
p("- The 20 kg/s Delichatsios flame now agrees within 1% after replacing an")
p("  unburned-density term with the published flame-temperature rise.")
p("- Schefer equation 10 is the radial mass-fraction half-radius, not a")
p("  centreline mole-fraction decay equation. Equation 11 now supplies the")
p("  radial flammable contour and removes the former 7x false disagreement.")

content = "\n".join(out) + "\n"
code_dir = Path(__file__).resolve().parent
targets = [
    code_dir / "VERIFICATION.md",
    code_dir.parent / "핸드오프" / "VERIFICATION.md",
]
for target in targets:
    target.write_text(content, encoding="utf-8")
    print(f"wrote {target}, {len(out)} lines")
