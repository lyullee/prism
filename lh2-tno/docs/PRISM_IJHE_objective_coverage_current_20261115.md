# PRISM IJHE objective coverage audit (15 November 2026)

This record is the current requirement-level audit for the generic outdoor liquid-hydrogen facility scope. It is deliberately separate from the 57-check completion audit: the completion audit checks the executable facility handoff, while this objective audit checks whether the IJHE claims are supported by the current evidence package.

## Current decision

The objective chain is **conditionally complete for diagnostic use**. The machine-readable record is [`ijhe_objective_coverage_current_union_receptor_geometry.json`](../results/20261115/ijhe_objective_coverage_current_union_receptor_geometry.json).

| Item | Current result |
|---|---:|
| Objective rows | 33 |
| Core blocking rows | 0 |
| Strict evidence gates still open | 4 |
| Completion-audit result | `INCOMPLETE_EVIDENCE` (57 checks: 52 PASS, 5 BLOCKED) |
| Facility IR/F-N promotion | withheld |
| Physical-validation claim | withheld |
| Fresh-physics 1 Hz claim | withheld |

The result means that the software can execute the declared conditional chain and can provide a fast cached diagnostic response. It does not mean that every facility case has a qualified release provider, that all outdoor accident families are physically validated, or that a facility-wide regulatory QRA is complete.

## Current native external full-scope replay

The latest native `lh2dt` replay is kept as a separate diagnostic supplement to
the authoritative 34-event/44-case union above. Its tracked records are
[`campaign_result.json`](../results/20261115/native_external_facility_full_scope_campaign_current/campaign_result.json),
[`facility_assessment.json`](../results/20261115/native_external_facility_full_scope_campaign_current/facility_assessment.json),
and the packet set in
[`native_external_facility_full_scope_packets_current`](../results/20261115/native_external_facility_full_scope_packets_current/).
It covers 24 reviewed literature events and produces 24 case rows and 96 risk
atoms. All 24 cases reach the consequence path; 13 have a ready diagnostic
dynamic-closure record and 11 remain explicitly operator-limited/withheld.
The conditional facility risk view is available, while
`facility_total_risk_available=false` and `facility_qra_claim=false` remain in
the saved assessment. The ambient-vaporizer G1 case was corrected from an
invalid instantaneous-depletion interpretation to an explicit
`inventory_over_600s` bounded history with residual inventory retained. This
replay strengthens the state-to-release-to-consequence evidence, but it does
not replace the authoritative union audit or close provider qualification,
independent physical validation, or strict facility-QRA gates.

The same replay now publishes a 12-family [`scope_matrix.json`](../results/20261115/native_external_facility_full_scope_campaign_current/scope_matrix.json)
and a 24-case [`facility_evidence_request.json`](../results/20261115/native_external_facility_full_scope_campaign_current/facility_evidence_request.json).
The request catalog marks 11 cases as `EXECUTED_OPERATOR_LIMITED` and keeps
unsupported/no-event families explicit. It is an intake contract for the
missing provider and validation evidence, not a frequency source or a QRA
promotion mechanism.

The full-scope processing-time record reports 24 fresh-physics cases, a total
campaign time of 814,290.39 ms, and a case p95 of 105,548.90 ms. This is an
offline diagnostic benchmark. The online monitor uses the separately measured
cached-result path; no fresh-physics 1 Hz service claim is made.

## What is connected

The current chain is explicit and auditable:

1. A process-state snapshot and operating mode are bound to HAZOP event identity.
2. The selected event is mapped to an equipment and release port.
3. The release provider supplies interval time, mass flow, pressure, temperature, phase, effective area, velocity, inventory and termination evidence.
4. The release packet is passed to the LH2 source-term and SLABx-LH2 consequence path.
5. Ignition, weather, population and receptor branches are accounted for before conditional individual-risk and F/N diagnostics are calculated.
6. Literature-based frequency ports and uncertainty cases are retained in the same event/case identity.
7. The monitor path distinguishes `cached_diagnostic_1hz` from `fresh_physics_background`; the benchmark records both timings and makes no fresh-physics 1 Hz claim.

Every campaign result now also carries a `prism.facility_receptor_geometry.v1`
contract. It records each receptor coordinate, the nearest non-boundary
component used for geometry interpretation, and the annual-condition population
set. The contract requires zero-population rows to be explicit and marks a
population-set mismatch as review-required. Facility-ledger merging preserves
one identical geometry contract across equipment campaigns and rejects
conflicting geometry instead of silently combining incompatible IR/F-N results.
The current union-side diagnostic record is
[`facility_receptor_geometry_current.json`](../results/20261115/facility_receptor_geometry_current.json);
it has one declared receptor and a closed population set for the synthetic
annual conditions. This is a traceability improvement and does not close the
independent validation, qualified-provider, strict-scope, or facility-QRA gates.

The latest 57-check audit also includes the forecast facility-campaign evidence gate. The two forecast requests remain withheld because their quantitative evidence coverage is incomplete. The inspection-center handoff and receptor-geometry comparisons remain separate diagnostic records; a near-receptor result must not be substituted for the declared facility receptor geometry.

The inspection-centre source boundary is documented separately in
[`PRISM_inspection_center_source_suitability_20261115.md`](PRISM_inspection_center_source_suitability_20261115.md).
It records 17 workbooks and 78 sheets with timestamped process signals, while
keeping unit/tag/calibration review, accident-release evidence, frequency
evidence, and independent physical validation as explicit open gates.

The source folder was re-audited for this current package. The compact record
[`inspection_center_evidence_reaudit_current.json`](../results/20261115/inspection_center_evidence_reaudit_current.json)
binds the 3 CSV files/52 scenario rows (41 outdoor candidates and 11 rows
outside the declared outdoor scope) to the 17-workbook/78-sheet signal audit.
All 522 numeric signal columns remain `MISSING_OR_UNCONFIRMED` for engineering
units. The re-audit therefore refreshes provenance only; it does not turn
normal-operation observations into accident releases, frequencies, provider
qualification, or facility QRA evidence.

The re-audit is reproducible with
[`build_inspection_center_evidence_reaudit.py`](../scripts/build_inspection_center_evidence_reaudit.py).
It runs the scenario importer, scenario-structure audit, and time-series audit
together; the compact output keeps the 41/11 scope split and the 522
unconfirmed-unit signal count. Its contract is covered by
[`test_inspection_center_evidence_reaudit.py`](../tests/test_inspection_center_evidence_reaudit.py),
and the command never assigns a frequency or creates a provider packet.

The interpretation of the current facility-level conditional IR/F-N fields,
including the declared receptor geometry and the separate near-receptor
diagnostic, is documented in
[`PRISM_conditional_facility_risk_interpretation_20261115.md`](PRISM_conditional_facility_risk_interpretation_20261115.md).

The finite-inventory termination margin probe is documented in
[`PRISM_inventory_termination_margin_20261115.md`](PRISM_inventory_termination_margin_20261115.md);
it confirms that the remaining open inventory cases cannot be closed by
extrapolating the current provider horizon.

The independent FFI Test 6 SLABx comparison now has an accepted actual-source
numerical-gate recheck in
[`PRISM_FFI_Test6_actual_source_numerical_gate_20261115.md`](PRISM_FFI_Test6_actual_source_numerical_gate_20261115.md).
The 40,960-to-81,920 refinement is below the 2% criterion for every monitored
quantity, so the numerical-resolution gate is accepted. The record remains a
component numerical result and does not support an independent physical-
validation or facility-QRA claim.

## Open evidence gates

The following gates remain intentionally fail-closed:

- **`independent_physical_validation`**: the current matrix contains screening and comparison evidence, but not an independent full-chain validation claim.
- **`qualified_provider_evidence`**: current packets are native diagnostic packets; no exact qualified provider packet has been promoted.
- **`strict_facility_scope`**: some declared equipment/accident families remain partial or operator-limited for strict qualification.
- **`strict_facility_qra`**: facility-wide IR/F/N promotion stays false until the previous gates close.

The current evidence package closes the inspection-centre source suitability diagnostic, observed-state replay, runtime-frame, external-equipment-readiness and provider-request diagnostics. Two non-strict diagnostic rows remain visibly blocked because the latest 44-case completion audit still contains an open release-closure worklist and does not align with a strict full-completion claim. They do not disappear from the record and they do not promote facility QRA.

These are evidence gaps, not silent software substitutions. A missing release boundary, physical validation record, or runtime frame remains visible as blocked.

## Completion criteria

The audit uses the following five criteria:

- **A — Equipment state and release:** conditional pass; the state-to-release interface is implemented, with qualified provider evidence still open.
- **B — Release to final damage:** conditional pass; the source-term, dispersion, ignition and damage path runs, with qualified provider and strict facility-QRA gates still open.
- **C — Facility IR/F/N and scope:** conditional pass; the accounting path exists, but strict scope and facility-QRA promotion remain withheld.
- **D — Literature frequency uncertainty:** conditional pass; literature frequency ports and uncertainty cases are represented, while provider qualification remains open.
- **E — Validation and processing time:** conditional pass; the cached diagnostic benchmark is available and fresh physics is measured separately, while independent physical validation remains open.

## Real-time interpretation

The benchmark must be read as two modes:

- `cached_diagnostic_1hz` reuses a previously qualified result for the same request identity and meets the recorded 1 Hz cache deadline.
- `fresh_physics_background` recalculates the source term and SLABx-LH2 consequence path when the state or release boundary changes. Its measured latency is retained, but it is not presented as a 1 Hz service-level guarantee.

The monitor path does not learn annual accident frequency from alarm counts, infer an accident release from pressure/temperature alone, extend a provider interval, or silently substitute a similar event.

The latest audit metadata verifier also checks the actual FFI Test 6 numerical-gate
pointer in `CURRENT_STATUS.json`. It requires the declared gate schema, matching
`ACCEPTED`/`accepted=true` state, the sibling refinement record, and explicit
`physical_validation_claim=false` and `facility_qra_claim=false` flags. A verifier
`PASS` therefore confirms numerical-gate consistency; it does not mean that
independent physical validation or facility QRA is complete.

The current objective ledger contains 33 checks after reconciling the latest completion audit and
independently reproducing the conditional facility IR/F-N sum from 176 saved risk atoms.
The external-release inventory remains a separate optional diagnostic row when it is not embedded
in the completion audit.

The verifier now also binds the latest union facility scope matrix and release-boundary
case audit. It cross-checks the 44-case count and the 13 eligible/31 blocked release
split against `CURRENT_STATUS.json`, requires the declared scope matrix and audit
schemas, and keeps facility IR/F-N, provider qualification, and physical-validation
claims false. This prevents a stale scope or release ledger from being mistaken for
the current IJHE evidence package.

The release-boundary audit now performs a second, per-case evidence-request contract
check. It verifies the request ID, equipment identity, event/branch/annual-condition
key, required provider-evidence list, and the root policy flags that forbid frequency
inference and facility-QRA promotion. The current 44-case catalog is aligned
(`ALIGNED: 44`, `BLOCKED: 0`); the request status remains `OPEN_EVIDENCE_REQUEST`
because the evidence has not yet been supplied and qualified.
The detailed contract definition and reproduction command are in
[`PRISM_release_boundary_request_contract_20261115.md`](PRISM_release_boundary_request_contract_20261115.md).
The same release audit also reports an equipment-level `asset_summary`, so the
facility-wide blocked count can be traced back to individual tanks, lines,
valves, pumps, vents, vaporizers, and reliquefiers.

## Reproduction

Run from the `lh2-tno` package directory. The exact evidence paths are listed in the audit JSON and in `CURRENT_STATUS.json`. The essential command is:

```powershell
python scripts/build_ijhe_objective_coverage_audit.py `
  --union-verification results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/verification.json `
  --completion-audit results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json `
  --scope-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --facility-aggregate-closure-audit results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_aggregate_closure_audit.json `
  --inspection-center-source-inventory results/20261115/inspection_center_source_inventory_suitability.json `
  --inventory-termination-margin-probe results/20261115/inventory_termination_margin_probe.json `
  --realtime-cache-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --output results/20261115/ijhe_objective_coverage_current_union_receptor_geometry.json
```

The full campaign command adds the native catalog, state-snapshot, provider-request, release-closure, validation, extension-coverage and external-equipment evidence paths. A nonzero exit status is expected while strict evidence gates remain open; the JSON status is the authoritative result.

To verify the latest pointer and its fail-closed FFI gate metadata:

```powershell
python scripts/verify_latest_ijhe_audit.py `
  --scope-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json `
  --release-boundary results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/latest_ijhe_audit_verification.json
```

## Scope exclusions

This audit does not claim field-frequency learning, indoor dispersion, detonation, or a complete domino analysis. Those are explicit follow-up scopes. The current paper claim should remain limited to the declared generic outdoor LH2 diagnostic chain and its evidence-qualified boundaries.
