# PRISM IJHE objective coverage audit (15 November 2026)

This record is the current requirement-level audit for the generic outdoor liquid-hydrogen facility scope. It is deliberately separate from the 49-check completion audit: the completion audit checks the executable facility handoff, while this objective audit checks whether the IJHE claims are supported by the current evidence package.

## Current decision

The objective chain is **conditionally complete for diagnostic use**. The machine-readable record is [`ijhe_objective_coverage_current_union_receptor_geometry.json`](../results/20261115/ijhe_objective_coverage_current_union_receptor_geometry.json).

| Item | Current result |
|---|---:|
| Objective rows | 20 |
| Core blocking rows | 0 |
| Strict or diagnostic evidence gates still open | 7 |
| Completion-audit result | `INCOMPLETE_EVIDENCE` (49 checks: 45 PASS, 4 BLOCKED) |
| Facility IR/F-N promotion | withheld |
| Physical-validation claim | withheld |
| Fresh-physics 1 Hz claim | withheld |

The result means that the software can execute the declared conditional chain and can provide a fast cached diagnostic response. It does not mean that every facility case has a qualified release provider, that all outdoor accident families are physically validated, or that a facility-wide regulatory QRA is complete.

## What is connected

The current chain is explicit and auditable:

1. A process-state snapshot and operating mode are bound to HAZOP event identity.
2. The selected event is mapped to an equipment and release port.
3. The release provider supplies interval time, mass flow, pressure, temperature, phase, effective area, velocity, inventory and termination evidence.
4. The release packet is passed to the LH2 source-term and SLABx-LH2 consequence path.
5. Ignition, weather, population and receptor branches are accounted for before conditional individual-risk and F/N diagnostics are calculated.
6. Literature-based frequency ports and uncertainty cases are retained in the same event/case identity.
7. The monitor path distinguishes `cached_diagnostic_1hz` from `fresh_physics_background`; the benchmark records both timings and makes no fresh-physics 1 Hz claim.

The latest 49-check audit also includes the reconstructed inspection-center handoff and the receptor-geometry comparison. Those two checks are diagnostic only. A near-receptor result must not be substituted for the declared facility receptor geometry.

## Open evidence gates

The following gates remain intentionally fail-closed:

- **`independent_physical_validation`**: the current matrix contains screening and comparison evidence, but not an independent full-chain validation claim.
- **`qualified_provider_evidence`**: current packets are native diagnostic packets; no exact qualified provider packet has been promoted.
- **`strict_facility_scope`**: some declared equipment/accident families remain partial or operator-limited for strict qualification.
- **`strict_facility_qra`**: facility-wide IR/F/N promotion stays false until the previous gates close.
- **`strict_facility_state_snapshot_coverage`**: the canonical state-snapshot campaign does not yet cover every vertical-handoff and inventory-depletion case with strict evidence.
- **`diagnostic_observed_state_source_replay`**: observed-state source/replay evidence is not complete for the full declared chain.
- **`diagnostic_observed_state_runtime_frames`**: complete runtime-frame and source/frame digest evidence is not available for the full monitor campaign.

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

## Reproduction

Run from the `lh2-tno` package directory. The exact evidence paths are listed in the audit JSON and in `CURRENT_STATUS.json`. The essential command is:

```powershell
python scripts/build_ijhe_objective_coverage_audit.py `
  --union-verification results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/verification.json `
  --completion-audit results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current_with_receptor_geometry.json `
  --scope-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --realtime-cache-benchmark results/20261026/native_full_scope_union_assessment/realtime_cache_benchmark.json `
  --output results/20261115/ijhe_objective_coverage_current_union_receptor_geometry.json
```

The full campaign command adds the native catalog, state-snapshot, provider-request, release-closure, validation, extension-coverage and external-equipment evidence paths. A nonzero exit status is expected while strict evidence gates remain open; the JSON status is the authoritative result.

## Scope exclusions

This audit does not claim field-frequency learning, indoor dispersion, detonation, or a complete domino analysis. Those are explicit follow-up scopes. The current paper claim should remain limited to the declared generic outdoor LH2 diagnostic chain and its evidence-qualified boundaries.
