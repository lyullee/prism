# PRISM outdoor LH2 consequence-backend contract

This document describes the contract that connects an outdoor LH2 equipment
state to the conditional facility risk ledger.  It is the reproducible model
handoff used by the diagnostic campaign and is written for review and IJHE
methods documentation.

## Declared chain

Each executed case carries the same event, equipment, release branch, annual
condition, and provider-packet identity through these stages:

1. **Source** — the equipment process model supplies the resolved gas or liquid
   release, its time history, termination basis, isolation state, and mass
   ledger.
2. **Cryogenic pool** — DynamicLH2PoolX accounts for ground liquid, evaporation,
   residual pool mass, and numerical mass closure.
3. **Near field and dispersion** — the SLABx-LH2 handoff uses the declared
   source state, ambient condition, release position, and release direction.
4. **Cloud observation** — the dispersed hydrogen field is sampled at every
   declared outdoor receptor.
5. **Ignition and harm** — direct fire, delayed flash fire, delayed explosion,
   and no-ignition branches are evaluated with the declared branch weights.
6. **Facility aggregation** — annual weather and population conditions,
   initiating frequency, release/barrier probability, ignition branch, and
   receptor harm are combined into conditional individual-risk and F-N ledgers.

The machine-readable contract is
`examples/lh2_consequence_backend_chain_contract.json`.

## Required identity and accounting fields

The standard release path requires every case to retain:

- `provider_packet_identity`, `termination`, and `mass_ledger.released_kg`;
- `annual_condition_id` and `annual_condition_probability`;
- `release_branch_probability` and `initiating_frequency_per_year`;
- `domain_assessment` for finite-domain and outside-cloud accounting.

Every risk atom must retain:

- `annual_condition_id` and `release_branch_id`;
- `ignition_branch` and `conditional_weight`;
- `receptor_harm_low_high` and `expected_deaths_low_high`.

At facility level, the contract requires the annual condition table and its
population accounting, the conditional IR ledger,
`conditional_diagnostic_facility_expected_death_fn_low_high`, and explicit
flags for `facility_total_risk_available` and `complete_facility_qra_claim`.
The flags are deliberately required even when they are `false`, so a withheld
result cannot disappear from a report.

## Explicit accident-family matching

A case with a named scenario family can only use a backend path that lists that
family.  The audit never routes an unknown or unsupported accident through a
generic release path.  If no path matches, the case is emitted as
`BACKEND_CHAIN_INCOMPLETE` with `no backend path matches the case scenario
family`, and its risk contribution remains uncomputed.

The published contract lists the declared outdoor families: vessel, pipe,
valve, vent, pump, vaporizer, reliquefier, liquid/two-phase, finite inventory,
600-second bounded inventory, vertical handoff, and two-sided rupture.

## Reproduction

From the `lh2-tno` package directory:

```powershell
python scripts/audit_consequence_backend_chain.py `
  --campaign-result results/20261026/native_full_scope_union_assessment/campaign_result.json `
  --backend-contract examples/lh2_consequence_backend_chain_contract.json `
  --output results/20261115/consequence_backend_chain_audit_current.json
```

The current replay produces 44 cases, 44 structurally closed diagnostic
cases, and eight declared backend stages.  The audit verifies the chain only;
it does not qualify an external provider, infer an initiating frequency, or
promote facility IR/F-N.

## Interpretation boundary

The chain can produce a conditional diagnostic IR/F-N result when all declared
inputs are present.  The strict facility result remains withheld when a case
uses synthetic or operator-limited provider input, when a release boundary is
not independently qualified, or when independent physical validation is
missing.  The current campaign therefore reports the conditional ledger and
the unresolved evidence requests together.  It does not present the
conditional value as a qualified site risk.

The required scope excludes indoor dispersion, detonation modelling, full
domino escalation, sensor-derived frequency learning, and field accident-rate
inference.  Those exclusions are recorded as scope decisions rather than
silently substituted with an outdoor model.
