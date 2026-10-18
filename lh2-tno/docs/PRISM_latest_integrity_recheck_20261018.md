# Latest integrity recheck — 2026-10-18

## Result

The authoritative union audit was regenerated with the current PRISM code and the current external LH2 model evidence. The prior checks were reproduced with the same five strict blockers. Three diagnostic checks are now present:

- `diagnostic_external_pump_test_point_audit`: eight NASA pump test points were extracted from two source documents. The exact PRISM configuration match and independent holdout review remain open, so this evidence cannot promote a provider packet, frequency, physical validation, or facility QRA.
- `diagnostic_nasa_tn_d4171_hem_benchmark`: 21 NASA TN D-4171 homogeneous-equilibrium pressure points were replayed as a negative model-limit benchmark. The mean predicted/observed ratio is 0.4797, MAPE is 52.03%, and NRMSE is 0.3703. This result informs model selection and uncertainty discussion; it is not a physical-validation claim.
- `diagnostic_state_release_mass_consistency`: the numeric inventory handoff between an equipment state snapshot and the provider mass balance was checked for all 44 campaign cases. Eight cases were comparable, seven matched, one storage-shell case differed by 99.96%, and 36 cases lacked both fields needed for comparison. The mismatch is classified as `MASS_BASIS_UNDECLARED_REVIEW_REQUIRED`: neither side declares an explicit comparable inventory-basis token, so the audit does not guess whether the values represent different inventory owners or scopes. No value is corrected and no packet or QRA claim is promoted.

The numeric handoff is now also enforced at runtime in `ConsequenceRequest.valid()`. If both values are present, the state snapshot inventory must match the provider's initial/available inventory within the declared numerical tolerance; otherwise the request is rejected before consequence evaluation. This is a fail-closed boundary check, not an automatic correction. The current storage-shell artifact still requires provider re-export with a consistent snapshot because it predates this gate.

The storage-shell native frequency case has since been re-exported with the
current provider initialization. Its new snapshot records `71.7644005715 kg`,
matches the provider packet exactly, and preserves the previous `0.0284920619
kg` snapshot digest and value as an explicit rebaseline record. This closes the
single-case diagnostic mismatch; the authoritative 44-case union still retains
its legacy mismatch until the full provider catalog is re-exported.

The campaign state-snapshot binder now applies the same numeric check before it
embeds a provider snapshot into a campaign request. A stale snapshot therefore
fails compilation instead of reaching the consequence chain with a valid digest
but an invalid inventory boundary.

The separate reconciliation record
`examples/state_release_mass_reconciliation_20261115.json` links the one legacy
authoritative mismatch to the explicit native rebaseline. It marks the row as
resolved diagnostically while keeping `authoritative_campaign_replaced=false`.
This distinction prevents a single re-export from being presented as a full
44-case facility requalification.

The updated authoritative audit is therefore `INCOMPLETE_EVIDENCE` with 60 checks: 55 PASS and 5 BLOCKED. The facility QRA claim, independent physical-validation claim, provider-packet promotion, and sensor-derived frequency inference remain false.

## SLABx-LH2 boundary

SLABx-LH2 remains a frozen, validated consequence component. Its existing 5/5 component audit and publication evidence are retained. No SLABx source, coefficients, validation files, or consequence logic were changed in this recheck. Remaining work concerns the upstream provider release boundary, isolation and inventory termination evidence, facility scope, qualified provider packets, and facility IR/F-N—not SLABx revalidation.

## External model workspace

The external `lh2dt` Python source tree was rechecked at source commit `7072374c59b726f4e938cd37e7695684ddc70b68` with source-tree digest `3b186dff343bd787567033e13b62954a748bce0f12ba26b981d03bafe3d02d74`. Its full suite passed `377` tests with one warning. The workspace has one untracked benchmark document, `docs/benchmarks/nasa_tn_d4171_hem_validation.md`; this is documentation intake, not a source-code change.

PRISM's full portable suite passed `1551` tests with one warning after the numeric boundary, provider-state rebaseline and campaign-binder gate changes. The audit artifact remains fail-closed and diagnostic-only.

## Continuous integration

GitHub Actions run #1439 for commit `a53511e8` completed successfully. The API record is the authoritative status; the web page may briefly show a stale in-progress view during the recheck.


