# PRISM dynamic-closure reclassification audit

The current facility union contains 44 numerical cases. Some of its source
packets were created before the equipment providers exported their dynamic
state-closure record, so those cases are deliberately labelled
`EXECUTED_OPERATOR_LIMITED` even when the consequence chain itself ran.

The newer native external equipment campaign is now compared against the
authoritative union with:

```powershell
python scripts/audit_dynamic_closure_reclassification.py `
  --current-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/campaign_result.json `
  --candidate-result results/20261115/native_external_facility_full_scope_campaign_current/campaign_result.json `
  --output results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/dynamic_closure_reclassification_audit.json
```

The generated audit matches 24 of the 44 union cases. Thirteen candidate rows
have a provider-owned `READY` dynamic closure and numerical execution; nine of
those would improve a currently `EXECUTED_OPERATOR_LIMITED` row. The remaining
four were already numerically executed in the union. The audit does not rewrite
the union and does not grant facility-QRA eligibility.

Promotion remains blocked until the ordinary gates are satisfied: exact
provider-packet qualification, physical-validation evidence, complete release
termination coverage, and the facility IR/F-N boundary. This separation keeps
the useful new dynamic evidence visible without silently treating a newer
diagnostic packet as qualified facility evidence.

The machine-readable record is
`results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/dynamic_closure_reclassification_audit.json`.
