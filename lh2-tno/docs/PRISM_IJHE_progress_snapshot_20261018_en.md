# PRISM IJHE progress snapshot (2026-10-18)

This snapshot is a requirement-level status record for the generic outdoor LH2
facility scope. It preserves the distinction between a numerically executed
diagnostic path and a qualified facility-QRA result.

| IJHE requirement | Evidence | Status |
| --- | --- | --- |
| Equipment state and operating mode reach HAZOP selection | `examples/hazop_integrated_current_forecast_recheck_20261018.json` | Diagnostic complete |
| HAZOP scenario identity reaches the provider/consequence request | HAZOP scenario trace audit in the same receipt | Diagnostic complete |
| Release rate, duration, isolation, inventory and residual mass are retained | `results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json` and native packet manifests | Diagnostic complete; strict qualification open |
| Release reaches SLABx-LH2 and damage/ignition branches | `docs/PRISM_public_backend_chain_recheck_20261018_en.md` | 7 equipment chains executed |
| Literature frequency and uncertainty are applied without sensor learning | `examples/hazop_integrated_current_forecast_recheck_20261018.json`; 3 frequency scenarios | Diagnostic complete |
| Current-state facility conditional IR/F-N path | `docs/PRISM_conditional_facility_risk_recheck_20261018_en.md` | 24 events, 24 cases, 96 atoms |
| Forecast-state trigger path | `examples/hazop_integrated_current_forecast_recheck_20261018.json` | Trigger at 10 s; diagnostic complete |
| Weather, ignition and population branches | Conditional facility view and facility assessment | Synthetic-condition diagnostic; site evidence open |
| Processing-time evidence | Conditional facility view and public chain manifest | Recorded; no 1 Hz fresh-physics claim |
| Complete facility IR/F-N promotion | Facility-QRA gate summary | Withheld |
| Independent full-chain physical validation | IJHE readiness audit | Open |
| Exact qualified provider packet coverage | Facility evidence request and qualification audit | 0 qualified cases |

## Current numeric evidence

The public-backend seven-equipment replay reached
`END_TO_END_DIAGNOSTIC_EXECUTED` for tank, transfer pipe, pump, vaporizer,
reliquefier, vent and valve. The replay took about 88.1 s and made no
frequency, qualification or physical-validation claim.

The facility conditional recheck contains 24 events, 24 cases and 96 risk
atoms. Fresh-physics case timing has a median of 16.83 s and p95 of 105.55 s;
the campaign total was about 814.29 s. These values are measured replay data
for the declared synthetic campaign and are not a service-level guarantee.

The current/forecast HAZOP receipt records three literature-frequency
scenarios (`p05`, `published`, `p95`), no frequency inference, and one forecast
risk trigger at 10 s. Forecast time is a model time coordinate, not an annual
probability.

## Remaining completion gates

The remaining work is evidence closure rather than silently filling missing
values. Every declared case needs an exact qualified provider packet with a
reviewed release boundary, and the complete facility release-to-dispersion-
to-damage chain needs independent validation. Until those artifacts exist,
the facility-wide IR/F-N result remains withheld and incomplete accident
families remain explicitly uncomputed or operator-limited.
