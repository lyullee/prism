# Native external base recheck (2026-10-18)

The latest external LH2 equipment campaign was re-bound as a diagnostic
replacement for the 24-case base campaign and merged with the existing
vertical-handoff and inventory-depletion extensions. The authoritative union
was left unchanged because the candidate provider result digests differ from
the currently bound packets.

## Result

- 34 events, 44 cases and 176 risk atoms were retained.
- Numerical execution changed from 15 to 23 cases.
- `EXECUTED_OPERATOR_LIMITED` changed from 29 to 21 cases.
- The comparison identifies 9 new reclassification candidates with explicit
  provider-owned `READY` dynamic closure.
- No row is promoted automatically: the candidate is a diagnostic ledger, not
  a qualified provider packet.
- Qualified provider packets: 0/44.
- Facility total IR/F-N and facility-QRA promotion: `false`.
- Physical-validation claim: `false`.
- Conditional diagnostic annual IR for `worker-01`:
  `3.7804000000730242e-06` to `3.780422204259991e-06` per year.

The candidate is useful because it proves that newer provider closure evidence
can reduce the operator-limited portion of the chain. It does not prove that
the changed packets are interchangeable with the current union: exact source
and result identity, state-snapshot binding, provider qualification and
independent validation still have to be reviewed.

## Reproduction

```powershell
python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261115/native_full_scope_frequency_assessment_isolation_current `
  --base-campaign results/20261115/native_external_facility_full_scope_campaign_current/campaign.json `
  --base-campaign-result results/20261115/native_external_facility_full_scope_campaign_current/campaign_result.json `
  --vertical-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/vertical_handoff_rebound_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/inventory_depletion_rebound_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --extension-state-snapshot-audit results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/extension_state_snapshot_coverage.json `
  --output-dir results/20261115/native_full_scope_union_assessment_external_base_recheck_current

python scripts/audit_dynamic_closure_reclassification.py `
  --current-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/campaign_result.json `
  --candidate-result results/20261115/native_full_scope_union_assessment_external_base_recheck_current/campaign_result.json `
  --output results/20261115/native_full_scope_union_assessment_external_base_recheck_current/dynamic_closure_reclassification_audit_vs_authoritative_union.json
```

Machine-readable evidence is stored in the candidate directory, especially
`verification.json`, `campaign_result.json`,
`dynamic_closure_reclassification_audit_vs_authoritative_union.json`, and
`equipment_state_release_audit.json`.
