#!/usr/bin/env python3
"""
Command line interface.

    qra template                       write the input spreadsheets
    qra run --sections s.csv ...       calculate and export

The point is that a site can be described, calculated and exported
without writing Python. Everything the library refuses to decide -- the
ignition scheme, the acceptance criterion, what happens when a model is
outside its premise -- is an explicit flag with no default that hides it.

The ignition scheme has no safe default
----------------------------------------
It moves the answer by a factor of about fifty and it is a choice between
two irreconcilable bodies of data, not a distribution to sample. So it is
required on the command line rather than defaulted, and it is written
into the output.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


def cmd_template(args) -> int:
    import siteio
    out = Path(args.directory)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in siteio.all_templates().items():
        p = out / f"{name}.csv"
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p}")
    print("\nFill these in, then:")
    print(f"  python3 qra.py run --name SITE "
          f"--sections {out}/sections.csv "
          f"--components {out}/components.csv "
          f"--assemblies {out}/assemblies.csv "
          f"--ignition hyram --out result.json")
    return 0


def cmd_run(args) -> int:
    import decision as dec
    import export
    import pipeline
    import siteio
    import uncertainty as U
    from gating import RefusePolicy
    from ignition import IgnitionScheme

    try:
        site = siteio.load_site(args.name, args.sections, args.components,
                                args.assemblies)
    except siteio.SheetErrors as e:
        print(str(e), file=sys.stderr)
        return 2

    scheme = {"purple": IgnitionScheme.PURPLE,
              "purple-sources": IgnitionScheme.PURPLE_SOURCES,
              "hyram": IgnitionScheme.HYRAM}[args.ignition]
    environment = None
    if scheme is IgnitionScheme.PURPLE_SOURCES:
        import ignition_sources as IS
        rows = siteio.read_rows(args.ignition_sources) \
            if args.ignition_sources else []
        if not rows:
            print("purple-sources needs --ignition-sources: Purple Book "
                  "4.7.2 method A is defined by the sources actually "
                  "present, and an empty list means the survey has not "
                  "been done", file=sys.stderr)
            return 2
        srcs = [IS.IgnitionSource(
            name=r["name"], kind=IS.SourceKind(r["kind"].strip().upper()),
            x=float(r.get("x_m") or 0), y=float(r.get("y_m") or 0),
            p_present=float(r.get("p_present") or 1.0),
            length_m=float(r.get("length_m") or 0),
            population=float(r.get("population") or 0)) for r in rows]
        environment = pipeline.IgnitionEnvironment(
            sources=srcs, cloud_residence_s=args.cloud_residence)
    policy = {"exclude": RefusePolicy.EXCLUDE,
              "bound": RefusePolicy.BOUND,
              "escalate": RefusePolicy.ESCALATE}[args.on_refusal]

    print(f"{site.name}: {len(site.sections)} sections, "
          f"{len(site.all_components())} components after expansion")
    run_kwargs = dict(
        half_extent_m=args.extent, cell_size_m=args.cell,
        ignition_scheme=scheme, ignition_environment=environment,
        blocking=__import__("blocking").BlockingSystem[
            args.blocking.upper()],
        isolation_s=args.isolation,
        population_per_cell=args.population, refuse_policy=policy)
    result = pipeline.run(
        site, flame_model=pipeline.FlameModel(args.flame_model), **run_kwargs)

    model_form = None
    if args.flame_envelope:
        alternatives = {result.flame_model.value: result}
        for model in pipeline.FlameModel:
            if model.value not in alternatives:
                alternatives[model.value] = pipeline.run(
                    site, flame_model=model, **run_kwargs)
        model_form = U.flame_model_envelope(alternatives)
        print(model_form.statement())

    interval = (U.propagate_linear(result.contributions, n=args.samples)
                if args.samples > 0 else None)
    report = dec.build_report(result, interval=interval,
                              ir_criterion=args.criterion)

    print()
    for line in report.lines():
        print(line)

    payload = export.export(result, interval=interval, report=report,
                            model_form=model_form,
                            origin_lon=args.lon, origin_lat=args.lat)
    payload["run"] = {
        "site": site.name,
        "ignition_scheme": scheme.value,
        "ignition_scheme_note": (
            "the two schemes differ by about fifty at the level of "
            "individual risk; this is a choice between bodies of data, "
            "not an uncertainty that was sampled"),
        "refuse_policy": policy.value,
        "blocking_system": args.blocking,
        "flame_model": result.flame_model.value,
        "flame_model_envelope_evaluated": bool(model_form),
        "ir_criterion_per_year": args.criterion,
        "grid_half_extent_m": args.extent,
        "grid_cell_m": args.cell,
    }
    export.write(args.out, payload)
    print(f"\nwrote {args.out}")
    if args.cell > 12.5:
        print(f"note: maximum individual risk has not converged at "
              f"{args.cell:g} m cells. On the reference site it rises "
              f"about 12% from 25 m to 12.5 m and settles there. The "
              f"area-integrated risk is resolution independent and is in "
              f"the output as risk_integral_per_year_m2.")

    if args.geojson:
        with open(args.geojson, "w", encoding="utf-8") as f:
            json.dump(payload["ir_contours_geojson"], f, indent=2)
        print(f"wrote {args.geojson}")

    # Exceeding is a finding, not a failure of the run.
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="qra",
        description="PRISM screening QRA for liquid and gaseous "
                    "hydrogen facilities")
    sub = ap.add_subparsers(dest="command", required=True)

    t = sub.add_parser("template", help="write blank input spreadsheets")
    t.add_argument("--directory", default="qra_input")
    t.set_defaults(func=cmd_template)

    r = sub.add_parser("run", help="calculate and export")
    r.add_argument("--name", required=True)
    r.add_argument("--sections", required=True)
    r.add_argument("--components")
    r.add_argument("--assemblies")
    r.add_argument("--ignition", required=True,
                   choices=["purple", "purple-sources", "hyram"],
                   help="no default. purple-sources is Purple Book 4.7.2 "
                        "method A, required for societal risk; purple is "
                        "the free field reading without its escape clause "
                        "and is a bound; hyram is the hydrogen-specific set")
    r.add_argument("--ignition-sources",
                   help="CSV of ignition sources, for purple-sources")
    r.add_argument("--cloud-residence", type=float, default=60.0,
                   help="seconds a source is exposed to the cloud")
    r.add_argument("--criterion", type=float, default=1e-6,
                   help="individual risk limit per year; 1e-6 is the Dutch "
                        "value for new situations and is policy, not physics")
    r.add_argument("--on-refusal", default="exclude",
                   choices=["exclude", "bound", "escalate"],
                   help="what to do when a model is outside its premise")
    r.add_argument("--extent", type=float, default=400.0,
                   help="grid half extent, m")
    r.add_argument("--cell", type=float, default=25.0,
                   help="grid cell, m. Purple Book 6.2.1 asks for 25 below "
                        "about 300 m of effect distance and 100 beyond, "
                        "but on the reference site the maximum individual "
                        "risk is still 12%% below its converged value at "
                        "25 m and settles near 12.5 m. Halve it and rerun "
                        "before quoting a maximum.")
    r.add_argument("--blocking", default="automatic",
                   choices=["automatic", "remote", "hand", "none"],
                   help="blocking system grade, Purple Book 4.4.1. Closing "
                        "times 120, 600 and 1800 s and failure on demand "
                        "0.001, 0.01 and 0.01. HyRAM credits the same "
                        "barrier by removing the outcome with a factor of "
                        "0.9 instead; that is NOT also applied here")
    r.add_argument("--isolation", type=float,
                   help="override the closing time, s. The previous "
                        "default of 30 s was faster than any grade the "
                        "book recognises")
    r.add_argument("--population", type=float, default=0.0,
                   help="people per cell, for societal risk")
    r.add_argument("--samples", type=int, default=5000,
                   help="Monte Carlo draws over leak frequency; 0 to skip")
    r.add_argument("--flame-model", default="molkov-conservative",
                   choices=["molkov-conservative", "molkov-fit",
                            "delichatsios"],
                   help="GH2 jet-flame correlation used for the point run")
    r.add_argument("--flame-envelope", action="store_true",
                   help="also run all three jet-flame model forms and "
                        "export their non-probabilistic risk envelope")
    r.add_argument("--lon", type=float, help="site origin longitude")
    r.add_argument("--lat", type=float, help="site origin latitude")
    r.add_argument("--out", default="result.json")
    r.add_argument("--geojson", help="also write the contours alone")
    r.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
