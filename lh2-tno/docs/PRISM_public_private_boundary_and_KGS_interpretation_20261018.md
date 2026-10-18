# PRISM public/private boundary and KGS result interpretation

This note records the repository and execution boundary checked on 2026-10-18.
It is intended to prevent a public-repository status, a missing input dataset,
and an unavailable external risk engine from being described as the same issue.

## What is public

- [`lyullee/prism`](https://github.com/lyullee/prism) is currently a public
  GitHub repository.
- [`lyullee/lh2dt_models`](https://github.com/lyullee/lh2dt_models) is currently
  a public companion repository.
- The PRISM host, `lh2_tno` contracts, HAZOP/mode handoff, literature-frequency
  binding, sensor normalization, conditional risk arithmetic, evidence ledger,
  fail-closed checks, tests, and documentation are in the PRISM distribution.
- The SLABx-LH2 component remains a frozen, validated external consequence
  component. It is not the missing KGS risk-engine component and this recheck
  does not reopen its validation.

The public PRISM package contains adapters and contracts for external physics
models. It does not copy every external model source into the repository.

## What is external and currently unavailable to KGS

The standard quantitative path requires a separately supplied, version-pinned
`tno` package. Its entry point is `qra.py`; the legacy risk path also imports
modules such as `risk.py`, `damage.py`, `fire.py`, and `ignition.py`. PRISM
requires the caller to provide:

1. an interpreter;
2. the external package roots; and
3. the SHA-256 source-tree digest for each root.

`src/tno_host.py` rejects standard-mode execution when the backend is missing,
when `qra.py` is absent, or when the digest does not match. The LH2
consequence and facility campaign paths likewise require `--backend`. There is
no automatic fallback that substitutes a public approximation for the legacy
TNO engine.

Therefore, the 404 described in the KGS screenshot means that KGS cannot reach
the required external `tno` source/backend. It does not mean that the PRISM
GitHub repository is private. The local TNO source directory is not a Git
worktree and is not included in the public PRISM repository.

## Why the TNO files were not copied into PRISM

This was a distribution-boundary decision made when PRISM was packaged. The
release records state that MIT applies to PRISM's own files and does not grant
redistribution rights for external models, books, or raw data. The local TNO
directory has no repository remote and no `LICENSE`, `COPYING`, or `NOTICE`
file that would establish a public redistribution basis. One of its model
files also records a deliberate effort to keep the implementation independent
of GPL source. These facts do not prove that the TNO code is legally private;
they do show that its ownership and redistribution permission were not
documented well enough to copy it into a public MIT repository.

Accordingly, the correct status is **external source not published with PRISM**,
not “SLABx-LH2 is private” and not “PRISM is private”. If the TNO source is
confirmed to be owned by the project and released under a compatible license,
it can be published as a separately licensed public engine or added to a
separate repository. Until then, PRISM's pinned-backend adapter is the safe
public boundary.

The public package does include `src/lh2_tno/risk.py`, but that file provides
conditional probability and thermal-dose arithmetic with explicit inputs. It
is not the legacy TNO facility QRA engine and does not replace `qra.py`.

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
equipment coordinates when the coordinate basis is supplied. The missing step
for IR is the external risk engine plus the required facility evidence gates.

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

