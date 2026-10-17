# Latest integrity recheck — 2026-10-18

## Result

The authoritative union audit was regenerated with the current PRISM code and the current external LH2 model evidence. The prior checks were reproduced with the same five strict blockers. Three diagnostic checks are now present:

- `diagnostic_external_pump_test_point_audit`: eight NASA pump test points were extracted from two source documents. The exact PRISM configuration match and independent holdout review remain open, so this evidence cannot promote a provider packet, frequency, physical validation, or facility QRA.
- `diagnostic_nasa_tn_d4171_hem_benchmark`: 21 NASA TN D-4171 homogeneous-equilibrium pressure points were replayed as a negative model-limit benchmark. The mean predicted/observed ratio is 0.4797, MAPE is 52.03%, and NRMSE is 0.3703. This result informs model selection and uncertainty discussion; it is not a physical-validation claim.
- `diagnostic_state_release_mass_consistency`: the numeric inventory handoff between an equipment state snapshot and the provider mass balance was checked for all 44 campaign cases. Eight cases were comparable, seven matched, one storage-shell case differed by 99.96%, and 36 cases lacked both fields needed for comparison. The mismatch is retained as an open model-input issue; no value is corrected and no packet or QRA claim is promoted.

The numeric handoff is now also enforced at runtime in `ConsequenceRequest.valid()`. If both values are present, the state snapshot inventory must match the provider's initial/available inventory within the declared numerical tolerance; otherwise the request is rejected before consequence evaluation. This is a fail-closed boundary check, not an automatic correction. The current storage-shell artifact still requires provider re-export with a consistent snapshot because it predates this gate.

The updated authoritative audit is therefore `INCOMPLETE_EVIDENCE` with 60 checks: 55 PASS and 5 BLOCKED. The facility QRA claim, independent physical-validation claim, provider-packet promotion, and sensor-derived frequency inference remain false.

## SLABx-LH2 boundary

SLABx-LH2 remains a frozen, validated consequence component. Its existing 5/5 component audit and publication evidence are retained. No SLABx source, coefficients, validation files, or consequence logic were changed in this recheck. Remaining work concerns the upstream provider release boundary, isolation and inventory termination evidence, facility scope, qualified provider packets, and facility IR/F-N—not SLABx revalidation.

## External model workspace

The external `lh2dt` Python source tree was rechecked at source commit `7072374c59b726f4e938cd37e7695684ddc70b68` with source-tree digest `3b186dff343bd787567033e13b62954a748bce0f12ba26b981d03bafe3d02d74`. Its full suite passed `377` tests with one warning. The workspace has one untracked benchmark document, `docs/benchmarks/nasa_tn_d4171_hem_validation.md`; this is documentation intake, not a source-code change.

PRISM's full portable suite passed `1525` tests with one warning after the numeric boundary change. The audit artifact remains fail-closed and diagnostic-only.

## Continuous integration

GitHub Actions run #1401 for commit `c8ec1cf2` completed successfully. The API record is the authoritative status; the web page may briefly show a stale in-progress view during the recheck.


