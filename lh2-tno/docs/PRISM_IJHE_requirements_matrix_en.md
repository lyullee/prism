# PRISM IJHE requirements and evidence matrix

This matrix is the working completion record for the generic outdoor LH2
facility objective. It distinguishes a diagnostic connection from a qualified
facility-QRA claim. A row is promoted only when its stated evidence and gate
criteria are satisfied; missing evidence is not treated as zero risk.

| Requirement | Current evidence | State | Completion criterion |
|---|---|---|---|
| Generic outdoor LH2 scope | 34 HAZOP-bound events, 44 release/weather cases, 9 equipment components, 12 declared accident families | **Partial diagnostic** | Every declared family has an exact provider case or an explicit `UNCOMPUTED`/blocked row with reviewed scope rationale |
| Process state and operating mode to HAZOP | `realtime_hazop_facility_bridge.v1`, explicit `operating_mode`, `hazop_scenario_id`, and mode-trace audit with zero mismatches | **Pass, diagnostic** | Reviewed state units, tag mapping, and mode authority are accepted for every deployed component |
| Release duration, isolation, and inventory depletion | Facility ledger consumes 44 provider-shaped packets; 15 rows are complete and 29 are `EXECUTED_OPERATOR_LIMITED` | **Partial** | Each declared case has provider-owned duration, isolation response, termination basis, residual inventory, and mass/energy closure |
| Release-to-consequence chain | `risk_atom_chain_audit.json`: 44/44 cases complete across source, pool, near-field/dispersion, cloud observation, and fire/explosion-damage stages; 176 atoms matched | **Pass, diagnostic** | Independent holdout validation covers the complete facility release-to-damage chain |
| Literature frequency binding | 44/44 event-port bindings; five explicit central/P05/P95 sensitivity scenarios; 34 independent event-bound events and 9 fixed-rate events | **Pass, diagnostic** | Reviewed literature catalogue and uncertainty bounds cover the final qualified event scope; no sensor-derived frequency is used |
| Current-state and forecast paths | Current and forecast HAZOP handoff records contain explicit mode-bound triggers and four-block quantitative evidence; orchestration p50/p95/p99 is 1.019/1.084/1.084 ms; the latest three-mode replay executed 3/3 branches and took 12.827 s | **Pass, diagnostic; provider-limited** | Deployment supplies a fresh-provider deadline and proves cache age, state identity, and fallback behavior for the target control loop |
| Fresh quantitative processing time | Facility fresh-physics case median/p95/p99 is 2.193/10.400/12.738 s; campaign wall median/p95/p99 is 19.298/134.471/144.709 s | **Measured, background only** | Timing is repeated on the target deployment and reported separately from cached monitor latency; no 1 Hz fresh-physics claim is made |
| Weather, ignition, population, and IR/F-N | Five synthetic annual conditions; 176 risk atoms; all harm is zero at the declared 20 m worker receptor; conditional IR/F-N output is available | **Conditional only** | Reviewed site weather, ignition, receptor geometry, and population data replace synthetic/unqualified inputs and all strict cases are covered |
| Facility-QRA promotion | `facility_qra_gate_summary.json` is `FACILITY_QRA_WITHHELD`; qualified provider packet count is 0; facility IR/F-N promotion is false | **Blocked by evidence** | Provider qualification, release-boundary closure, declared scope, independent physical validation, and population qualification gates all pass |
| SLABx-LH2 consequence component | Five-of-five component audit checks pass; source/unit/clock handoff is retained | **Frozen validated component** | No further SLABx development is required for this objective; facility/provider validation remains separate |
| Explicit exclusions | Field accident-frequency learning, indoor dispersion, detonation, and full domino escalation are excluded from the declared scope | **Deliberate scope boundary** | Any future expansion adds a new reviewed scope matrix and does not reinterpret an omitted family as zero risk |

## Authoritative records

- Completion audit: `results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`
- Facility assessment: `results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json`
- Facility-QRA gate: `results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_qra_gate_summary.json`
- Risk-atom chain audit: `results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/risk_atom_chain_audit.json`
- Frequency uncertainty audit: `results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_frequency_uncertainty_audit.json`
- Current-state recheck: `docs/PRISM_현재상태_재점검_20261018.md`
- Latest header-bound runtime replay: `docs/PRISM_header_bound_facility_bridge_current_recheck_20261018.md`

The current IJHE result remains `INCOMPLETE_EVIDENCE`. This matrix is complete
as a status-and-criteria record; it is not evidence that the blocked facility
QRA gates have passed.
