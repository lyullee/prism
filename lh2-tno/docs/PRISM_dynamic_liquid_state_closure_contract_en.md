# Dynamic LH2 release-state closure contract

PRISM now distinguishes two different things that can both look like a
time-resolved LH2 release:

1. a provider that calculated a release history while holding the upstream
   tank pressure and inventory effectively constant; and
2. a provider that fed the changing equipment state back into the release
   calculation and can prove that feedback.

The first case still runs through the gas or liquid/two-phase, pool,
SLABx-LH2, ignition, radiation, blast, and conditional-risk chain, but it is
reported as `EXECUTED_OPERATOR_LIMITED` for accidental leaks and emergency
relief releases. The second case may remove that source-dynamics limitation,
provided the separate termination, provider qualification, and
physical-validation gates also pass. Normal operating vents are outside this
accident-state gate.

## Provider payload

Add the following object under `data.provider_meta` in an external accident
response. It is optional for backwards compatibility, but omission keeps the
existing fail-closed behavior.

```json
{
  "initial_mass_kg": 71.76,
  "final_mass_kg": 71.73,
  "cumulative_mass_out_kg": 0.03,
  "isolation_time_s": 0.18,
  "post_isolation_observation_s": 0.10,
  "isolation_success": true,
  "dynamic_state_closure": {
    "schema_version": "prism.provider_dynamic_state_closure.v1",
    "inventory_feedback_closed": true,
    "pressure_feedback_closed": true,
    "state_history_digest": "<64 lowercase hexadecimal characters>",
    "max_abs_inventory_residual_kg": 1.0e-9,
    "inventory_tolerance_kg": 1.0e-8,
    "max_abs_pressure_residual_pa": 2.0,
    "pressure_tolerance_pa": 10.0,
    "provenance": "equipment-twin dynamic state ledger"
  }
}
```

The adapter validates this record as
`prism.provider_dynamic_state_closure.v1` and preserves it inside
`prism.provider_mass_balance.v1`. The state-history digest must identify the
provider's pressure/inventory history used to produce the release packet. It
is not a digest of the PRISM result and it cannot be replaced by a prose
statement.

## Release of the operator limitation

The gas and liquid workers release the source-dynamics limitation only when
all of the following are true:

- the dynamic closure object is present;
- both inventory and pressure feedback flags are explicitly `true`;
- the history digest and both residual/tolerance pairs are valid and within
  tolerance;
- the provider initial mass, cumulative output, final mass, and accounting
  residual close;
- the packet uses a reviewed isolation, inventory-depletion, or emergency
  relief termination basis; and
- reviewed isolation declares `isolation_success=true`, while inventory
  depletion reaches the declared final-mass tolerance.

The result carries a `dynamic_state_closure` audit object with each check and
its blocking reasons. A missing field, malformed digest, failed residual, or
unsupported termination basis leaves `operator_limited=true`; PRISM never
repairs the provider record or infers a pressure response from the outlet
flow.

The campaign case ledger preserves this audit at the equipment boundary with
`dynamic_state_closure_status` (`READY`, `BLOCKED`, `NOT_DECLARED`, or
`NOT_EVALUATED`). The merged facility ledger reports the same counts globally
and for each component. This makes it possible to see which equipment can
support a dynamic release calculation without mistaking a conditional
diagnostic total for a qualified facility QRA.

The standalone provider mass-balance audit reports the same status for each
external response before campaign execution. A scalar `CLOSED` mass ledger
with no explicit pressure/inventory feedback record is still reported as
`BLOCKED` for an accidental or relief release.

## Cross-ledger consistency audit

The independent `dynamic_state_closure_audit` recomputes status counts from
the raw case identities and compares them with the stored campaign coverage,
facility coverage, and per-component coverage. When all campaign files used
for a merge are supplied, it also compares the campaign identity ledger with
the merged facility ledger. It catches a stale READY/BLOCKED count or a
component row that was changed after execution.

```powershell
python scripts/audit_dynamic_state_closure_ledger.py `
  --campaign results/campaign_tank.json `
  --campaign results/campaign_transfer_line.json `
  --facility results/facility_ledger.json `
  --output results/dynamic_state_closure_ledger_audit.json
```

The report uses schema
`prism.dynamic_state_closure_ledger_audit.v1`. `PASS` means only that the
stored counts agree with explicit case rows. It does not qualify an external
provider, close physical validation, or promote facility IR/F-N.

The command accepts a direct facility ledger or a saved facility-assessment
JSON containing an explicit `facility_risk_ledger` object. Campaign inputs may
likewise be direct ledgers or an explicit `result` wrapper; no fields are
inferred while unwrapping.

The latest saved 44-case union snapshot was re-audited in
`results/20261115/dynamic_state_closure_ledger_audit_current.json`. It is
`BLOCKED` (40 checks, 29 blockers) because that snapshot predates the explicit
dynamic-state coverage fields. The record is retained as an evidence gap; it
does not convert the numerical release/consequence results into a qualified
facility result.

Attach the same report to the IJHE completion audit with
`--dynamic-state-closure-ledger-audit`. The completion audit records a
separate diagnostic check; a ledger-consistency pass never becomes a provider
or facility qualification pass.

## What this does not qualify

This contract closes one source-model connection for the selected accident
packet. It does not create an annual
frequency, prove that the provider represents a real facility, qualify the
external model against experiments, or make a two-sided rupture interaction
closed. The facility campaign still requires exact provider-packet evidence,
frequency provenance, weather/ignition/population inputs, independent physical
validation, and complete coverage of the declared accident families before an
IR/F-N or facility-QRA claim is promoted.

## Test coverage

The portable tests cover both paths:

- a normal liquid packet without this object remains operator-limited;
- an accidental gas packet without this object remains operator-limited;
- fully validated dynamic gas and liquid closure packets clear only the
  source-dynamics limitation; and
- residuals outside the provider-declared tolerance are rejected at the
  adapter boundary.
