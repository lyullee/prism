# PRISM

**Process Risk Integration and Scenario Modeling**

PRISM is an auditable research framework for connecting process and equipment state, HAZOP deviations, literature-based initiating frequencies, equipment release histories, hydrogen dispersion, and conditional facility-risk views.

> **Research software notice:** PRISM is designed for diagnostic and research workflows. A completed calculation chain does not by itself constitute regulatory certification, independent physical validation, or a complete facility QRA.

## Quick start

Install the published Python package:

```powershell
python -m pip install "prism-risk[full]==0.6.4"
prism --describe-modes
```

Or clone the public repository and run the test suite:

```powershell
git clone https://github.com/lyullee/prism.git
cd prism\lh2-tno
python -m pip install -e ".[full,test]"
python -m pytest -q
```

The package name is `prism-risk`; the command-line entry point is `prism`. Python 3.12 or newer is required. Version 0.6.4 bundles the project-authored PRISM QRA runtime, including `qra.py`, `risk.py`, `damage.py`, `fire.py`, and `ignition.py`. Standard mode runs without a private backend or a developer-specific folder.

Generate example facility tables, review them, then calculate:

```powershell
prism --mode standard template --directory standard_inputs
prism --mode standard run --name demo --sections standard_inputs/sections.csv --components standard_inputs/components.csv --assemblies standard_inputs/assemblies.csv --ignition purple --blocking none --samples 0 --extent 100 --cell 25 --out standard_result.json
```

The `full` extra installs the public PyPI versions `slabx==1.0.7` and `slabx-lh2==0.1.5`. Historical source-pinned research results retain their original backend digests; installing this release does not regenerate or requalify those results.

## What the framework connects

```mermaid
flowchart LR
    A[Measured or simulated equipment state] --> B[Operating mode and signal quality]
    B --> C[HAZOP deviation and scenario ID]
    C --> D[Equipment release provider]
    D --> E[Validated release history]
    F[Literature FrequencyPlan] --> G[PRISM orchestration]
    E --> G
    H[Weather, ignition, population, protection] --> G
    G --> I[SLABx-LH2 / consequence backend]
    I --> J[Risk ledger and response view]
```

The current-state path supports low-latency monitoring when a validated release history is available. The predicted-state path accepts a simulation state and records `input_origin="model_prediction"`. Operating mode, HAZOP selection, release history, frequency evidence, consequence output, uncertainty, latency, and response status remain separately traceable.

## Supported scope

PRISM provides the orchestration and audit boundary for generic outdoor LH2 facilities such as tanks, transfer lines, valves, pumps, vaporizers, and vents. External process and consequence models remain independent providers. PRISM does not silently infer a leak size from pressure and temperature, convert normal flow into an accident history, learn annual frequency from alarm counts, or extend a short provider history to an assumed full release.

## Documentation

The detailed package documentation is in [`lh2-tno/README.md`](lh2-tno/README.md):

- [English user manual](lh2-tno/docs/PRISM_USER_MANUAL_en.md)
- [English digital-twin interface guide](lh2-tno/docs/PRISM_INTERFACE_INTEGRATION_GUIDE_en.md)
- [English v0.6.4 distribution record](lh2-tno/docs/PRISM_v064_distribution_en.md)
- [Korean package README](lh2-tno/README_ko.md)
- [Korean source README](README_ko.md)

The interface guide defines the state-frame, HAZOP, provider release, frequency, result, and acceptance-test contracts needed to connect an equipment digital twin.

## Current IJHE audit status

The latest generic outdoor LH2 union audit is [`INCOMPLETE_EVIDENCE`](lh2-tno/docs/PRISM_IJHE_latest_audit_20261115.md): 57 checks, 52 pass, and 5 strict evidence gates remain withheld. The separate IJHE objective audit has no internal consistency blockers but retains the same five external-evidence gates; its current interpretation is documented in [`PRISM_IJHE_objective_coverage_current_20261115.md`](lh2-tno/docs/PRISM_IJHE_objective_coverage_current_20261115.md). The reconstructed inspection-centre handoff and receptor-geometry comparison are diagnostic-only; they do not promote provider qualification, independent full-chain validation, or total-facility IR/F-N. The latest facility-handoff interpretation, including the near-receptor conditional IR/F-N diagnostic and its receptor-geometry boundary, is in [`PRISM_IJHE_facility_handoff_audit_20261115.md`](lh2-tno/docs/PRISM_IJHE_facility_handoff_audit_20261115.md).

The machine-readable receptor comparison is [`PRISM_receptor_geometry_interpretation_20261115.md`](lh2-tno/docs/PRISM_receptor_geometry_interpretation_20261115.md). It explains why the declared 20 m full-scope receptor can have zero conditional IR/F-N while a separate 0.5 m diagnostic reaches one harm atom. The records remain separate and neither opens facility-QRA promotion.

The portable suite at the release preparation point reports **1,577 passed** (one environment-specific deprecation warning in the original development environment). The metadata check can be rerun with:

```powershell
cd prism\lh2-tno
python scripts/verify_latest_ijhe_audit.py --output results/20261115/latest_ijhe_audit_verification.json
```

## Release links

- [GitHub Release v0.6.4](https://github.com/lyullee/prism/releases/tag/v0.6.4)
- [PyPI: prism-risk 0.6.4](https://pypi.org/project/prism-risk/0.6.4/)
- [PyPI workflow](https://github.com/lyullee/prism/actions/workflows/publish-pypi.yml)
- [PRISM concept DOI](https://doi.org/10.5281/zenodo.23448413)
- [Version DOI — PRISM 0.6.4](https://doi.org/10.5281/zenodo.23448414)
- [Previous archive series](https://doi.org/10.5281/zenodo.23241358)

## Reproducibility

For every result, preserve the exact state frame, HAZOP row, provider release digest, `FrequencyPlan` revision, weather and protection inputs, package version or commit, and result ledger. Compare reruns by event ID, case ID, risk atom ID, and provider digest rather than by a rounded total alone.

## License

PRISM is released under the [MIT License](LICENSE). External process models, consequence backends, datasets, and source material retain their own licenses and citation requirements.
