# PRISM facility-QRA gate summary

PRISM keeps the conditional diagnostic IR/F-N calculation separate from the
strict facility-QRA decision. The machine-readable summary
`results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_qra_gate_summary.json`
reconciles the independent records without rerunning equipment or consequence
physics.

The summary checks six gates:

1. declared outdoor facility scope and case accounting;
2. release duration, isolation, inventory and mass-closure boundaries;
3. exact qualified provider release coverage;
4. independent physical validation for release, dispersion and damage;
5. reviewed accident-port/frequency binding without frequency inference; and
6. case-to-risk-atom traceability, including withheld operator-limited cases.

All gates are required before `FACILITY_QRA_ALLOWED` can be emitted. A
diagnostic IR/F-N sum may remain available when the result is
`FACILITY_QRA_WITHHELD`; missing evidence is never converted to zero risk.

Rebuild the current summary with:

```powershell
python scripts/build_facility_qra_gate_summary.py `
  --assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --provider-audit results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_audit.json `
  --validation-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/validation_evidence_matrix.json `
  --scope-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json `
  --output results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_qra_gate_summary.json
```

The strict scope gate now requires this explicit matrix to have
`matrix_complete=true`, `conditional_chain_complete=true`, one `COMPLETE` row
for every required outdoor accident family, no operator-limited or strictly
uncomputed row, and a case count matching the assessment. Omitting the matrix
keeps the gate closed. The current record is `FACILITY_QRA_WITHHELD`. The full
union contains 34 events and 44 cases; 29 cases remain withheld by the strict
release boundary.
The frequency-port gate is aligned, qualified provider packets are `0/26`, and
the physical-validation matrix remains restricted. The summary currently has
50 explicit blocking reasons. The provider qualification audit remains a
separate input, so missing provider evidence cannot be hidden by the full-scope
assessment.
The summary is therefore a review control and does not claim a regulatory or
publication-ready facility QRA.

The IJHE completion-audit CLI accepts the same record with
`--facility-qra-gate-summary`. It adds a structural audit check and blocks the
audit if the six-gate status, promotion flag, or gate identities are
inconsistent. It does not turn a withheld summary into a passing QRA claim.
