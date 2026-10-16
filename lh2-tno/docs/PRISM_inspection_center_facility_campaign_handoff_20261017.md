# Reconstructed facility HAZOP to annual-condition handoff

The facility runtime bridge now has an explicit handoff to the existing
annual-condition and facility-ledger contract:

```powershell
python scripts/build_inspection_center_facility_campaign_handoff.py
```

The command consumes:

- `examples/inspection_center_facility_hazop_bridge.json`
- an explicit annual-condition record containing outdoor weather and receptor
  population (`results/20261009/generic_full_scope_worklist/campaign_result.json`
  in the reproducible diagnostic run)

It builds the HAZOP campaign through
`build_hazop_facility_campaign_result(...,
allow_withheld_normal_components=True)`. This option is deliberately explicit:
components with `WITHHELD_HAZOP_NO_DEVIATION` are retained in the facility
snapshot as `WITHHELD_NORMAL`, while only selected HAZOP branches may create
events, cases, or risk atoms. A normal component is never converted into a
zero-risk accident row.

The generated artifact is:

```text
examples/inspection_center_facility_campaign_handoff.json
```

The latest replay shows:

| Ledger item | Result |
| --- | --- |
| HAZOP handoff | `HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED` |
| Campaign scope | `PARTIAL_DECLARED_SCOPE` |
| Facility ledger | `PARTIAL_FACILITY_SCOPE` |
| Explicit annual condition population | `EXPLICIT_CONDITION_POPULATION` |
| Selected supply branch | 1 event, 1 case, 4 ignition-branch risk atoms |
| Withheld normal components | intake tank and storage vent |
| Known current-weather contribution | recorded in `known_contribution_annual_ir_low_high` |
| Facility total annual IR/F-N | withheld (`null`) |
| Provider packet qualification | 0 qualified cases; diagnostic model prediction |

The handoff also records the frequency-scenario ledger for the selected
`ambient-vaporizer/G3` event. The central, low, and high catalogue scenarios
all carry the published/fixed rate of `1.0e-3 per year` for this asset, so the
three reweighted IR rows are identical in this diagnostic replay. The record
explicitly reports `marginal_p05_per_year=null` and
`marginal_p95_per_year=null`: fixed catalogue scenarios are sensitivity cases,
not a statistical confidence interval.

The annual-condition file is treated as evidence input and its provenance is
copied into the handoff. The script does not create population, weather,
frequency, release duration, isolation, or inventory values. The facility
ledger remains partial because the other component accident scope is not
computed, the consumed provider packet is unqualified, and independent
physical validation is unavailable.

The provider-component identity exception in the campaign handoff is also
fail-closed. A boundary whose component differs from the observed HAZOP
component is accepted only when the runtime result contains the exact explicit
observed-to-provider mapping produced by the facility bridge. Name, port, and
geometry similarity cannot open this boundary.
