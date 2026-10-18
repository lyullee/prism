# Conditional facility risk recheck (2026-10-18)

The public-backend chain replay was joined to the existing generic outdoor LH2
facility campaign and its release-boundary audit. This step applies the
declared literature frequency plan and the synthetic weather/population
condition to the executed cases, then exports a conditional diagnostic IR/F-N
view.

```powershell
python scripts/build_conditional_facility_risk_view.py `
  --facility-assessment results/20261115/native_external_facility_full_scope_campaign_current/facility_assessment.json `
  --release-boundary-case-audit results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261018/conditional_facility_risk_view_current.json
```

The output contains 24 events, 24 cases, and 96 risk atoms. The frequency
plan, ignition/consequence branches, weather condition, and synthetic worker
receptor are carried into the diagnostic view. The current evidence summary is
stored in [`conditional_facility_risk_recheck_20261018.json`](../examples/conditional_facility_risk_recheck_20261018.json).

The result is `CONDITIONAL_DIAGNOSTIC_FACILITY_RISK`. Facility IR and F/N are
kept `null` for the promoted facility result because all 24 consumed provider
packets remain unqualified. The gate reports `provider_packet_promoted=false`,
`qualified_provider_packet_case_count=0`, and `physical_validation_claim=false`.
This is an explicit facility-level connection and a useful conditional
diagnostic output; it is not a formal facility-QRA claim.

The source campaign recorded 24 fresh-physics cases with a median case time of
16.83 s, p95 of 105.55 s, and total campaign time of about 814.29 s. These are
observed replay timings for the declared synthetic campaign, not a 1 Hz service
guarantee. The separate seven-equipment public-backend replay is documented in
`PRISM_public_backend_chain_recheck_20261018_en.md`.
