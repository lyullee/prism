# PRISM release-boundary evidence-request contract (15 November 2026)

The facility release-boundary audit now checks two separate things for every declared case:

1. **Case-key coverage** — the evidence request exists exactly once for the same `event_id`, `release_branch_id`, and `annual_condition_id`.
2. **Request-contract coverage** — the request has a non-empty request ID, does not contradict the equipment/component identity, asks for provider evidence when qualification is required, and keeps frequency inference and facility-QRA promotion disabled.

This is a bookkeeping and safety gate. It does not create a release duration, estimate a missing inventory, learn a frequency, or qualify a provider. The current generic outdoor LH2 assessment has 44 cases:

- request status: `OPEN_EVIDENCE_REQUEST`
- case-key contract: `ALIGNED` for 44/44
- blocked request contracts: 0
- strict release-boundary eligible: 13/44
- strict release-boundary blocked: 31/44
- facility IR/F-N promotion: false

The zero blocked request contracts means the request table is internally complete. It does **not** mean the requested provider evidence has been supplied. The remaining 31 release-boundary cases and all provider-qualification and independent-physical-validation gates remain fail-closed.

Every case request now states `required_input_origin=reviewed_measurement`. Synthetic
and model-prediction packets remain valid diagnostic inputs, but they cannot be
used to create a qualified provider packet. The request also records this policy
at the top level so an external equipment adapter can reject an unsuitable
packet before it reaches the promotion boundary.

The same audit now emits an `asset_summary` section. It preserves the equipment
boundary instead of pooling all cases into one facility number. In the current
run, `inventory-depletion-pipe` is now 10/10 strict-eligible after the provider
inventory residual evidence was bound to the facility event IDs. The remaining
strict-boundary bottlenecks are `storage-shell` (5/5 operator-limited),
`transfer-line` (5/5 operator-limited), `transfer-valve` (5/5 operator-limited),
and `vertical-handoff-vent` (10/10 operator-limited). The pressure-relief vent and one ambient-vaporizer case keep
their unsupported termination bases visible as blocked instead of being silently
converted to an inventory or isolation event.

## Reproduce

From the `lh2-tno` package directory:

```powershell
python scripts/audit_release_boundary_cases.py `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --facility-evidence-request results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json `
  --provider-termination-evidence results/20261115/provider_termination_evidence_catalog_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json
```

The machine-readable output is the release-boundary audit itself. Its `facility_evidence_request_contract_status_counts` and `facility_evidence_request_contract_blocking_reasons` fields show the per-case request result. The latest metadata verifier consumes these fields when present.
