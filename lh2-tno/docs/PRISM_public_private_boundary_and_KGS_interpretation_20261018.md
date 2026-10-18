# PRISM public/private boundary and KGS result interpretation

This note records the repository and execution boundary checked on 2026-10-18.
It is intended to prevent a public-repository status, a missing input dataset,
and an optional external model from being described as the same issue.

## What is public

- [`lyullee/prism`](https://github.com/lyullee/prism) is currently a public
  GitHub repository.
- [`lyullee/lh2dt_models`](https://github.com/lyullee/lh2dt_models) is currently
  a public companion repository.
- The PRISM host, `lh2_tno` contracts, HAZOP/mode handoff, literature-frequency
  binding, sensor normalization, conditional risk arithmetic, evidence ledger,
  fail-closed checks, tests, and documentation are in the PRISM distribution.
- The project-authored standard quantitative implementation is bundled under
  `src/prism_qra`; standard mode can run from a clean public checkout without
  a private path.
- The SLABx-LH2 component remains a frozen, validated external consequence
  component and is available from its public repository. This recheck does not
  reopen its validation.

The public PRISM package contains the standard QRA implementation and adapters
for optional external physics models. It does not need to copy the public
SLABx source into the PRISM repository.

## Bundled standard QRA and optional dependencies

The standard path uses `src/prism_qra/qra.py` and companion modules such as
`risk.py`, `damage.py`, `fire.py`, and `ignition.py`. Install the public
dispersion dependencies with:

```powershell
python -m pip install -e ".[full]"
```

The `full` extra installs pinned public PyPI distributions of `slabx` and `slabx-lh2`. An
explicit `--backend` remains available for a separately pinned research model.
The LH2 facility consequence path can also require public equipment models such
as `lh2dt` and a declared pool model, together with the facility configuration
and evidence required by its gates.

The 404 described in the KGS screenshot was caused by an old external backend
reference. It does not mean that the PRISM or SLABx-LH2 repositories are
private. The old local source directory is retained only as provenance for the
bundled implementation and is no longer required for standard execution.

## Why the files were previously absent from PRISM

The first public package used a conservative distribution boundary because the
local source folder had no repository remote, license, or notice file. That
absence described the release packaging at the time; it did not establish that
the project-authored implementation was private. The project owner has now
confirmed that these modules were written for this project from published
Purple Book methods and are owned by the project.

The implementation is therefore published in this repository under the PRISM
MIT license at `src/prism_qra`. The source cites the equations and method
provenance, but the repository does not copy book text, raw third-party data,
or a third-party engine. The old local source directory is retained only as
historical provenance and is not needed to run a clean checkout.

The correct current status is **bundled project-authored standard QRA**. The
public SLABx-LH2 repository remains an optional consequence component, while
an explicitly pinned backend remains available for independent research
comparisons.

The public package does include `src/lh2_tno/risk.py`, but that file provides
conditional probability and thermal-dose arithmetic with explicit inputs. It
is not the facility-wide QRA command and does not replace `qra.py`.

## What is missing data rather than private code

Even after the external engine is supplied, a formal facility IR/F-N result
needs qualified facility evidence: equipment and receptor coordinates,
geometry and orientation, population/occupancy, weather and barrier basis,
reviewed initiating frequencies, and qualified release histories. If these
are absent or unqualified, PRISM keeps the result conditional or uncomputed.
Those are evidence and input-boundary gaps, not repository-visibility gaps.

The KGS result described in the screenshot already demonstrates a useful
partial path: `lh2dt` can derive an event-time release rate from pressure,
temperature, and inventory signals, and SLABx-LH2 can use that rate to report
dispersion distances. PRISM can then intersect the reported distance with
equipment coordinates when the coordinate basis is supplied. The remaining
IR limits are facility evidence gates and qualified input data, not an
inaccessible standard risk engine.

## Meaning of “상호영향” in this project

For this project, “상호영향” means **process-simulator-based dynamic risk
prediction**: the simulator predicts the evolving operating state, and a new
risk evaluation is requested when the predicted state reaches a defined risk
condition. It is not a domino-effect or accident-propagation calculation.

The separate documentation that excludes “full domino” or “chain escalation”
refers to a different scope item. It must not be used to describe the dynamic
process-simulator coupling. The KGS interface should use a name such as
`process_state_coupled_dynamic_prediction` and should pass the operating mode
along with the live or predicted state into the HAZOP decision table.

## Screenshot/source consistency

The file `docs/09_기관별_요청서.md` referenced in the screenshot is not present
in the current PRISM checkout. Its K17-K23 questions therefore appear to come
from an external draft and are not the current repository source of truth.
The repository’s current boundary is documented by the backend contract,
fail-closed execution gates, and the IJHE readiness audit.

