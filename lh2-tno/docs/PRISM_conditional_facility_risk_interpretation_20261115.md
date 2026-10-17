# Conditional facility-risk interpretation (15 November 2026)

This note explains the current facility-level calculation without turning a
diagnostic result into a qualified site QRA. The source record is the current
facility assessment:

`results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json`

## What the union calculation executed

The generic outdoor union contains 34 literature-frequency events, 44 cases,
and 176 risk atoms. Each conditional case reaches the consequence path and
retains its event frequency, weather condition, ignition branch, receptor harm,
and expected-death contribution. The release-boundary ledger separately records
15 reviewed-isolation rows, 25 inventory-depletion rows, one inventory-over-
600-second row, one emergency-relief row, and two two-sided-rupture rows.

The calculation therefore has the following explicit split:

- 44 conditional consequence executions are available for diagnostic review.
- 29 cases remain `EXECUTED_OPERATOR_LIMITED` for strict evidence purposes.
- 2 cases remain numerically open at the release-boundary audit because the
  provider termination evidence is invalid; the other 42 cases are numerically
  closed, with 29 still requiring operator review for strict qualification.
- No missing case is silently replaced by another accident family or another
  provider packet.

## Why the full-scope IR/F-N curve is zero

The declared generic worker receptor is at `[20.0, 0.0, 1.0] m`. At that
geometry the current model returns conditional individual risk `[0.0, 0.0]`
and an empty expected-death F/N curve. This is a geometry-specific zero, not a
claim that the facility can never harm a person.

The separate near-receptor diagnostic places a worker at `[0.5, 0.0, 1.0] m`
and reaches a conditional IR of `4.68e-5 per year` with one positive harm atom.
That record demonstrates that the release-to-dispersion-to-ignition-to-harm
chain can reach a receptor. It remains a separate diagnostic and is never
substituted into the full-scope facility result.

To publish a facility IR/F-N result, the receptor layout, population,
occupancy, weather distribution, and protection policy must be reviewed for the
actual facility. The current synthetic geometry is retained precisely so that
this distinction is visible.

## Processing-time interpretation

The union records separate stage timing for source, pool, near-field and
dispersion, cloud observation, and fire/explosion damage. A cached diagnostic
request may meet the recorded low-latency monitor target. A state change that
requires a fresh provider and SLABx-LH2 solve remains a background calculation;
the project does not claim a fresh-physics 1 Hz service level.

## Promotion boundary

The conditional IR/F-N fields are useful for model connectivity, sensitivity,
and response-screen development. They do not open:

- qualified provider evidence;
- independent physical validation;
- complete release-boundary coverage for the declared accident families; or
- facility-wide qualified IR/F-N.

The current machine-readable receptor comparison is
[`receptor_geometry_interpretation.json`](../results/20261115/receptor_geometry_interpretation.json),
and the requirement-level status remains in
[`PRISM_IJHE_objective_coverage_current_20261115.md`](PRISM_IJHE_objective_coverage_current_20261115.md).

The unresolved finite-inventory termination margin is recorded in
[`PRISM_inventory_termination_margin_20261115.md`](PRISM_inventory_termination_margin_20261115.md).
