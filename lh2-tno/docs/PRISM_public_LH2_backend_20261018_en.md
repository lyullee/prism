# Public LH2 backend configuration and numerical chain

This is development work after the published PRISM 0.6.4 release. Use the
GitHub source checkout for the commands below. The immutable 0.6.4 PyPI wheel
and its DOI remain the release baseline and do not include this later work.

## What changed

LH2 workers can now use the bundled project-authored `prism_qra` for heat harm
and facility IR/F-N arithmetic. The canonical source pin is `prism_qra`.
Historical `tno` pins retain their original numerical implementation; declaring
both aliases is rejected. There is no automatic switch between source trees.

Public SLABx-LH2 0.1.5 and the public repository's 0.2.0 snapshot do not contain
the local `integrated_lh2_source`, `lh2_jet_cloud_transition`, or
`freejet_handoff` interfaces used in historical PRISM chains. Installing those
versions alone therefore did not make the full LH2 integration reproducible.
Nine source/transition modules and their MIT dependency closure are now
distributed as `prism_lh2_models`, with the original Korea Gas Safety
Corporation license. Their Python source is preserved; portable hashes are in
[`SOURCE_PROVENANCE.json`](../src/prism_lh2_models/SOURCE_PROVENANCE.json).

The separately installed, validated SLABx-LH2 dispersion component is not
modified or revalidated by this work. The new package exposes previously local
source and transition code; its availability does not qualify a facility
provider history or establish independent full-chain validation.

## Configure the current interpreter

From `prism/lh2-tno`:

```powershell
python -m pip install -e ".[full,test,xlsx]"
python -m lh2_tno.public_backend --require-operation integrated_source --require-operation consequence_chain --output build/public_backend.json
prism --mode lh2 examples/consequence_facility.json --backend build/public_backend.json --consequences examples/consequence_request.json --output build/public_chain.json
```

The configurator pins exactly the installed model roots and their Python-source
SHA-256 digests in this interpreter. Built-in QRA and LH2 source roots must
belong to the same distribution as the adapter, preventing another checkout
from being selected inadvertently. Requested missing models or interface files
cause an error before a config is written. Interface-file presence is not a
physical validation certificate; the numerical run still checks actual APIs,
source origins, contracts, mass accounting, and case limits.

For QRA arithmetic only:

```powershell
python -m lh2_tno.public_backend --packages prism_qra --require-operation facility_risk_aggregate --output build/qra_backend.json
```

Pool and equipment operations require their own reviewed, public installed
providers. Add `dynamiclh2poolx` and/or `lh2dt` explicitly with `--packages`;
the configurator does not download or substitute a missing provider. Regenerate
the config after changing a model revision. Do not copy a recorded machine's
absolute paths as an executable configuration for another computer.

## Verified numerical results

An isolated environment used only this PRISM checkout and public PyPI runtime
packages: SLABx 1.0.7, SLABx-LH2 0.1.5, NumPy 2.5.4, and CoolProp 8.0.0.

- Single synthetic source-to-harm run: approximately 3.29 s, nonzero receptor
  harm, ignition probabilities summing to one, and end-to-end mass residual
  0 kg. This is one fresh run, not a repeated-run latency percentile.
- QRA-only cold and persistent workers: real heat-harm and IR/F-N computations
  matched independent arithmetic; old source-pin compatibility was checked.
- Full portable suite: 1,587 tests passed in the public-dependency environment.
- A separately built candidate wheel included the source provenance and MIT
  license. It was installed outside the checkout and completed the same chain
  in approximately 3.05 s with a 0 kg mass residual. This development wheel
  was not uploaded over the immutable PyPI 0.6.4 artifact.
- A separate facility campaign generated G1/G2/G3 literature events, two
  annual weather conditions and explicit outdoor populations. G3/west executed
  with four ignition risk atoms. The south-west G3 case reached the 120 s worker
  deadline and remains `FAILED`. G1/G2 have no full-inventory provider histories
  and remain four explicit `UNCOMPUTED` weather cases.
- The campaign took approximately 123.99 s including the failed case. Its
  known near-worker IR contribution is approximately 8.60e-7/year; independent
  IR and expected-death-convention F/N recalculation both have zero error.
  Total facility IR/F-N remains withheld.

Reproduce the campaign with:

```powershell
python scripts/validate_public_lh2_backend.py --output-dir build/public_lh2_campaign
```

This command intentionally retains the difficult wind-direction case. A fresh
run can consume the full configured deadline; failure is reported rather than
replaced by the successful weather result.

The recorded result and verification are under
[`results/20261018/public_backend_chain`](../results/20261018/public_backend_chain/).
They are synthetic integration evidence, not measured accident data. Model
source hashes and release claims in older evidence ledgers retain their own
version boundaries; these new runs do not overwrite the authoritative 44-case
union or qualify its missing provider evidence.

## Remaining IJHE work

This closes a public distribution and numerical connection gap. The objective
remains active: qualified equipment histories, case-specific physical release
termination, the declared facility accident scope, independent facility-chain
validation, frequency uncertainty for a complete facility, and fresh-physics
latency remain subject to the existing completion gates. The crosswind deadline
is now explicit public execution evidence requiring further work.
