# PRISM IJHE Requirement Traceability Matrix (2026-11-15)

This matrix maps the IJHE objective to the current PRISM evidence for a
generic outdoor liquid-hydrogen facility. Diagnostic execution is kept
separate from qualified facility-QRA promotion.

The authoritative audit is [`ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`](../results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json).
It currently reports **60 checks: 55 PASS and 5 BLOCKED** with overall status
`INCOMPLETE_EVIDENCE`.

## Requirement matrix

| IJHE requirement | Current evidence | Current judgement | Promotion condition |
| --- | --- | --- | --- |
| Equipment state and operating mode select a HAZOP deviation | [`header_bound_facility_bridge_runtime.json`](../results/20261115/header_bound_facility_bridge_runtime.json), [`inspection_center_facility_ijhe_handoff_audit.json`](../examples/inspection_center_facility_ijhe_handoff_audit.json) | **Diagnostic connected**. Receiving, standby, and supply modes are explicit inputs; mode inference is disabled. | Reviewed tag-to-equipment mapping and a provider-owned state snapshot for every declared case. |
| HAZOP output selects an accident identity and release port | [`facility_assessment.json`](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json) | **Connected**. All 34 union events are port-scoped and case/risk-atom port mismatches are zero. | Exact provider event/component/port identity and source/result digests for every case. |
| Release duration, isolation, and inventory depletion reach the consequence model | [`release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json`](../results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json), [`release_closure_worklist_current.json`](../results/20261115/release_closure_worklist_current.json) | **Partially closed**. 42 cases are numerically closed; 29 isolation and 24 inventory evidence gaps remain, with 2 numerically open cases. | Provider-owned start/end clock, termination basis, isolation ledger, initial/final inventory, residual mass, and explicit mass basis for every case. |
| SLABx-LH2 receives the release and produces dispersion/consequence outputs | [`PRISM_IJHE_facility_handoff_audit_20261115.md`](PRISM_IJHE_facility_handoff_audit_20261115.md) | **Component path closed diagnostically**. SLABx-LH2 remains the frozen validated consequence component. | Independent validation of the complete facility release-to-damage chain; this is separate from the completed SLABx component audit. |
| Ignition, weather, population, IR, and F/N are aggregated | [`conditional_facility_risk_view_with_release_trace.json`](../results/20261115/conditional_facility_risk_view_with_release_trace.json), [`facility_qra_gate_summary.json`](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_qra_gate_summary.json) | **Conditional diagnostic only**. Weather, ignition, receptor harm, and conditional IR/F-N ledgers are available; qualified total-facility IR/F-N is withheld. | Complete outdoor scope, reviewed receptor/population evidence, qualified provider packets, and independent ledger recomputation. |
| Literature frequency uncertainty is visible without sensor learning | [`facility_frequency_uncertainty_audit.json`](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_frequency_uncertainty_audit.json) | **Diagnostic uncertainty closed**. Five explicit central/low/high and independent-event sensitivity scenarios are stored. No sensor signal is used to infer a frequency. | Reviewed frequency provenance for every declared event and a complete qualified scope before interpreting a facility-wide interval. |
| Missing or unsupported accidents are explicit | [`scope_matrix.json`](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json), [`facility_evidence_request.json`](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json) | **Fail-closed**. 44 case requests are retained; 31 release-boundary rows are blocked and no unsupported family is substituted. | Resolve or explicitly approve each declared exclusion; no implicit zero-risk treatment. |
| New calculation processing time is reported | `facility_assessment.json` timing ledger and `header_bound_facility_bridge_runtime.json` | **Measured diagnostically**. Per-case and per-stage elapsed times are recorded. Cached unchanged-state lookup has a 1 Hz diagnostic benchmark; fresh physics is slower and has no 1 Hz claim. | Repeated-run benchmark with declared hardware, input size, concurrency, and provider/SLABx execution mode. |
| Inspection-center data can seed state/mode monitoring | [`inspection_center_source_inventory_suitability.json`](../results/20261115/inspection_center_source_inventory_suitability.json), [`inspection_center_facility_ijhe_handoff_audit.json`](../examples/inspection_center_facility_ijhe_handoff_audit.json) | **Screening and diagnostic only**. 17 workbooks/78 sheets and 522 numeric signals still have missing or unconfirmed units; no accident-release packet or frequency is created. | Reviewed units, calibration/quality, tag-to-equipment mapping, and provider-owned accident-release exports. |

## Strict promotion gate

The total-facility IR/F-N result may be promoted only when all of the
following are true:

1. Every declared outdoor case has an exact qualified provider packet.
2. Every packet closes duration, isolation, inventory, residual mass, and mass
   ownership with reproducible digests.
3. The declared accident-family matrix contains no uncomputed case or implicit
   substitution.
4. Receptor geometry, population, weather, and ignition conditions are
   reviewed facility inputs.
5. The complete release-to-damage chain has independent physical-validation
   evidence and an independent IR/F-N recomputation.

Until then, PRISM preserves conditional diagnostic risk atoms and reports
`facility_qra_promotion=false`. A structural verifier `PASS` means that the
stored artifacts and their pointers are internally consistent; it does not
mean that the strict gates are open.

## Deliberately excluded from this IJHE scope

Field accident-frequency collection, sensor-based frequency learning, indoor
release, detonation, and whole-facility domino escalation remain outside the
required scope. Their exclusion is recorded explicitly rather than replaced by
an unsupported surrogate accident.
