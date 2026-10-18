# PRISM latest external LH2 model compatibility recheck (2026-10-18)

## Result

The latest external `lh2dt_models` packet root was checked against the current 24-event generic outdoor LH2 frequency campaign before any facility result was promoted. All 24 exact packet identities and provider result digests match the current campaign. The current campaign already classifies ambient-vaporizer G1 as `inventory_over_600s`, so the provider's bounded 600-second termination is applied with the matching frequency mode.

| Check | Result |
|---|---:|
| Generated frequency events checked | 24 |
| Packet-compatible events | 24 |
| Packet/frequency compatibility blocks | 0 |
| Diagnostic base cases | 24 |
| Numerically executed base cases | 24 |
| Base risk atoms | 96 |
| Diagnostic union events / cases / risk atoms | 34 / 44 / 176 |
| Qualified facility QRA | No |
| Facility IR/F-N promotion | No |

The machine-readable record is [`results/20261018/latest_external_model_compatibility_recheck_20261018.json`](../results/20261018/latest_external_model_compatibility_recheck_20261018.json).

## Frequency reconciliation

An earlier diagnostic comparison used an older isolation campaign whose G1 frequency row was still `instantaneous_inventory`. That comparison was correctly blocked and has been retained as historical evidence. It was not the current external facility campaign. The current campaign in `results/20261115/native_external_facility_full_scope_campaign_current` uses the latest packet root and declares G1 as `inventory_over_600s`; no frequency rate was invented or changed during this recheck.

## Candidate facility execution

The current campaign has already been run through the existing PRISM chain: literature frequency binding, provider-resolved release, outdoor consequence calculation, weather and population conditions, and facility ledger aggregation. It reports 24 cases, 24 executed cases, 11 operator-limited cases, and 96 risk atoms. The facility union with the existing vertical-handoff and inventory-depletion ledgers contains 34 events, 44 cases, and 176 risk atoms.

Dynamic state closure is visible in the current ledger. The base campaign contains 13 `READY`, 9 `BLOCKED`, and 2 `NOT_DECLARED` closure states. The union contains 13 `READY`, 9 `BLOCKED`, and 22 `NOT_DECLARED` states because the extension campaigns retain their independent evidence limits.

These are diagnostic comparison outputs. `facility_total_risk_available=false`, `qualified_facility_qra_available=false`, `provider_packet_promoted=false`, and `physical_validation_claim=false` remain enforced. The remaining work is evidence qualification and facility-scope closure, not packet/frequency identity reconciliation.

## Current dirty-worktree recheck

The external worktree was rechecked again after the latest source changes. The
24-event catalog still produced 24 exact packets with zero uncomputed events.
The native layered-tank adapter now stores the canonical equipment-state
payload in its verification sidecar as well as the provider echo digest. The
state audit therefore reports **24/24 `BOUND_AND_ECHOED`**, with zero unbound
or digest-mismatch rows. A fresh 24-case facility replay completed all 24
diagnostic chains, produced 96 risk atoms, retained 11 operator-limited cases,
and took 603.72 s. This is a traceability improvement; the external worktree
is still dirty, all packets remain synthetic diagnostic evidence, and the
facility IR/F-N and qualification gates remain closed.

The updated compact records are [`external_lh2dt_full_scope_worktree_catalog_verification_20261018.json`](../examples/external_lh2dt_full_scope_worktree_catalog_verification_20261018.json), [`external_lh2dt_full_scope_worktree_campaign_verification_20261018.json`](../examples/external_lh2dt_full_scope_worktree_campaign_verification_20261018.json), and [`external_lh2dt_full_scope_worktree_state_snapshot_binding_20261018.json`](../examples/external_lh2dt_full_scope_worktree_state_snapshot_binding_20261018.json).

## Release-boundary recheck

The provider termination catalog was also rebuilt from the current 24-packet
worktree catalog plus the existing vertical-handoff and inventory-depletion
extension records. It contains 35 packet rows covering 34 event IDs with no
catalog errors. Re-running the case-level release-boundary audit increased
strictly eligible cases from 13 to **21 of 44** and reduced blocked cases from
31 to **23**. The result remains partial because 20 cases require operator
review, three cases have numerically open boundaries, provider qualification is
still absent, and facility IR/F-N promotion remains closed. The records are
[`external_lh2dt_provider_termination_catalog_recheck_20261018.json`](../examples/external_lh2dt_provider_termination_catalog_recheck_20261018.json)
and [`external_lh2dt_release_boundary_audit_recheck_20261018.json`](../examples/external_lh2dt_release_boundary_audit_recheck_20261018.json).

## Code change made during the check

The campaign packet rebind adapter now maps provider termination metadata to the contract-compatible equipment operator. It also sets `source_duration_mode=model_natural` for pressure-equalisation packets and selects the liquid or gas operator as appropriate for inventory boundaries. This prevents stale campaign templates from rejecting a valid provider packet while preserving provider duration, mass, and frequency ownership.

Regression coverage was added for pressure-equalisation rebinding. The full test suite passes (`1498 passed, 1 warning`).

## Reproduction

```powershell
# Historical comparison only: this uses the older isolation campaign and
# intentionally exposes the G1 frequency-mode mismatch described above.
python scripts/rebind_campaign_to_worklist_packets.py `
  --campaign results/20261115/native_full_scope_frequency_assessment_isolation_current/campaign.json `
  --packet-evidence results/20261018/latest_full_scope_packet_evidence_20261018.json `
  --packet-root results/20261115/native_external_facility_full_scope_packets_current `
  --output results/20261018/latest_full_scope_campaign_rebound_20261018.json `
  --provenance-output results/20261018/latest_full_scope_campaign_rebound_20261018.provenance.json

python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261115/native_external_facility_full_scope_campaign_current/campaign.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output-dir results/20261115/native_external_facility_full_scope_campaign_current

python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261115/native_external_facility_full_scope_campaign_current `
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
```
