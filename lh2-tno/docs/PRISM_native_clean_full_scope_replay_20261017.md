# Clean-source full-scope LH2 facility replay (2026-10-17)

PRISM was replayed against a clean archive of the public `lh2dt_models`
repository at commit `16f7a4b` (source tree digest
`81aa33dd24531f3d661617b49a2d6b830a9a36212d725282404e759ea48a9648`). The
generic outdoor facility frequency plan contains 24 event identities across
the storage tank, transfer line, transfer valve, relief vent, transfer pump,
ambient vaporizer, and reliquefier. All 24 clean-source packet identities
matched the plan and all 24 reached the PRISM consequence runner.

The replay produced 96 conditional diagnostic risk atoms. Twenty-two case
records remain operator-limited or withheld by the strict facility gate; the
replay therefore exposes the complete diagnostic chain without converting
screening evidence into a facility QRA claim. The run took 416,823.569 ms
(about 6.95 minutes) for the 24 fresh-physics cases. This is an offline
diagnostic timing result, not a one-hertz real-time guarantee.

The exact HAZOP binding is generated from the reviewed frequency plan with:

```powershell
python scripts/build_hazop_event_mode_binding_from_frequency_plan.py `
  --frequency-plan results/20261115/native_external_facility_full_scope_campaign_current/frequency_plan.json `
  --output results/20261115/native_external_facility_full_scope_campaign_current/hazop_event_mode_binding_clean_source.json
```

The generator requires explicit event ID, component ID, release mode,
operating mode, and HAZOP scenario ID. It performs no inference. This fixes a
historical mismatch in the older 2026-11-12 binding, where vaporizer G1 still
used `instantaneous_inventory`; the current packet and binding both use the
fail-closed `inventory_over_600s` boundary with residual inventory retained.

The small tracked evidence set is:

- [`clean_source_replay_summary.json`](../results/20261115/native_external_facility_full_scope_clean_source_replay_20261017/clean_source_replay_summary.json)
- [`packet_catalog_verification.json`](../results/20261115/native_external_facility_full_scope_clean_source_replay_20261017/packet_catalog_verification.json)
- [`facility_campaign_verification.json`](../results/20261115/native_external_facility_full_scope_clean_source_replay_20261017/facility_campaign_verification.json)
- [`state_snapshot_binding_audit.json`](../results/20261115/native_external_facility_full_scope_clean_source_replay_20261017/state_snapshot_binding_audit.json)
- [`hazop_event_mode_binding_clean_source.json`](../results/20261115/native_external_facility_full_scope_campaign_current/hazop_event_mode_binding_clean_source.json)

The no-isolation replay above remains preserved as a baseline. A follow-up
replay also exercised the explicit provider isolation branch after fixing a
time-step accounting bug in the valve adapter: splitting a step at the
isolation command had previously caused the precomputed loop count to stop
before the end of the observation horizon. The corrected adapter integrates
until the declared end time and proves the external actuator's zero-flow
observation without inferring field isolation reliability.

The isolation replay uses `isolation_time_s=0.05` and
`post_isolation_observation_s=0.10` with a `0.05 s` stroke. It produced 24/24
exact packet identities, 24/24 executed cases, 0 uncomputed cases, 0 failed
cases, 96 diagnostic risk atoms, and 5/5 transfer-valve isolation successes.
The campaign took 388,256.043 ms (about 6.47 minutes) offline. Its compact
evidence is recorded in:

- [`clean_source_isolation_replay_summary.json`](../results/20261115/native_external_facility_full_scope_clean_source_isolation_replay_20261017/clean_source_isolation_replay_summary.json)
- [`packet_catalog_verification.json`](../results/20261115/native_external_facility_full_scope_clean_source_isolation_replay_20261017/packet_catalog_verification.json)
- [`facility_campaign_verification.json`](../results/20261115/native_external_facility_full_scope_clean_source_isolation_replay_20261017/facility_campaign_verification.json)
- [`facility_risk_summary.json`](../results/20261115/native_external_facility_full_scope_clean_source_isolation_replay_20261017/facility_risk_summary.json)

The risk summary preserves the actual conditional facility connection: one
synthetic outdoor receptor, three literature-frequency scenarios, explicit
weather/population and ignition cross-products, component ranking, release
termination/inventory ledger, and a conditional annual IR/F-N curve. In the
recorded synthetic condition the worker receptor's diagnostic annual IR is
`3.37e-6` at both uncertainty endpoints and the F-N diagnostic curve is
available at the `N >= 1` threshold. These values are screening outputs from
the declared atoms, not a qualified facility-wide annual risk claim.

The follow-up remains diagnostic: provider qualification is zero, independent
physical validation is absent, literature frequency inference was not
performed, facility IR/F-N is withheld, and `facility_qra_claim=false` remains
enforced. The excluded receiving boundary is still outside the generic
equipment scope.
