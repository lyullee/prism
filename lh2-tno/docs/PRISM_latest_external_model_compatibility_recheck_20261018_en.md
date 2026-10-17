# PRISM latest external LH2 model compatibility recheck (2026-10-18)

## Result

The latest external `lh2dt_models` packet root was checked against the 24-event generic outdoor LH2 frequency campaign before any facility result was promoted. The packet root is usable for 23 events. One event is blocked because the provider changed its release termination contract without a corresponding change to the existing frequency catalogue.

| Check | Result |
|---|---:|
| Generated frequency events checked | 24 |
| Packet-compatible events | 23 |
| Packet/frequency compatibility blocks | 1 |
| Diagnostic base cases | 24 |
| Numerically executed base cases | 23 |
| Base risk atoms | 92 |
| Diagnostic union events / cases / risk atoms | 34 / 44 / 172 |
| Qualified facility QRA | No |
| Facility IR/F-N promotion | No |

The machine-readable record is [`results/20261018/latest_external_model_compatibility_recheck_20261018.json`](../results/20261018/latest_external_model_compatibility_recheck_20261018.json).

## Blocking mismatch

`generic-lh2-full-scope-frequency-example/ambient-vaporizer/G1` is still classified in the frequency catalogue as `instantaneous_inventory`. The latest provider packet declares `inventory_over_600s` and uses `equipment_inventory_over_600s`. PRISM correctly rejects this combination because it would apply an instantaneous-inventory frequency to a 600-second provider boundary.

The recheck therefore keeps the existing compatible packet for this one event in a separate diagnostic candidate. It does not rewrite the frequency mode, invent a new rate, or claim that the latest packet root is a complete facility input. The remaining 23 routes use the latest packet root.

## Candidate facility execution

The compatible diagnostic candidate was run through the existing PRISM chain: literature frequency binding, provider-resolved release, outdoor consequence calculation, weather and population conditions, and facility ledger aggregation. The resulting base candidate reports 11 `EXECUTED`, 12 `EXECUTED_OPERATOR_LIMITED`, and 1 failed case; the failed case is the blocked G1 route. The candidate union with the existing vertical-handoff and inventory-depletion ledgers contains 34 events, 44 cases, and 172 risk atoms.

Dynamic state closure is visible in the candidate ledger. The base candidate contains 11 `READY`, 10 `BLOCKED`, and 3 `NOT_DECLARED` closure states. The union contains 11 `READY`, 10 `BLOCKED`, and 23 `NOT_DECLARED` states because the extension campaigns retain their independent evidence limits.

These are diagnostic comparison outputs. `facility_total_risk_available=false`, `qualified_facility_qra_available=false`, `provider_packet_promoted=false`, and `physical_validation_claim=false` remain enforced. The latest root can become the facility input only after one of the following is supplied:

1. a frequency catalogue row explicitly defined for the 600-second inventory-over-600s event; or
2. a provider packet for G1 whose termination basis is compatible with the existing instantaneous-inventory frequency row.

## Code change made during the check

The campaign packet rebind adapter now maps provider termination metadata to the contract-compatible equipment operator. It also sets `source_duration_mode=model_natural` for pressure-equalisation packets and selects the liquid or gas operator as appropriate for inventory boundaries. This prevents stale campaign templates from rejecting a valid provider packet while preserving provider duration, mass, and frequency ownership.

Regression coverage was added for pressure-equalisation rebinding. The full test suite passes (`1498 passed, 1 warning`).

## Reproduction

```powershell
python scripts/rebind_campaign_to_worklist_packets.py `
  --campaign results/20261115/native_full_scope_frequency_assessment_isolation_current/campaign.json `
  --packet-evidence results/20261018/latest_full_scope_packet_evidence_20261018.json `
  --packet-root results/20261115/native_external_facility_full_scope_packets_current `
  --output results/20261018/latest_full_scope_campaign_rebound_20261018.json `
  --provenance-output results/20261018/latest_full_scope_campaign_rebound_20261018.provenance.json

python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261018/latest_compatible_campaign_rebound_20261018.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output-dir results/20261018/native_full_scope_frequency_assessment_latest_compatible_candidate

python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261018/native_full_scope_frequency_assessment_latest_compatible_candidate `
  --base-campaign results/20261018/native_full_scope_frequency_assessment_latest_compatible_candidate/campaign.json `
  --base-campaign-result results/20261018/native_full_scope_frequency_assessment_latest_compatible_candidate/campaign_result.json `
  --vertical-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/vertical_handoff_rebound_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/inventory_depletion_rebound_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --extension-state-snapshot-audit results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound/extension_state_snapshot_coverage.json `
  --output-dir results/20261018/native_full_scope_union_assessment_latest_compatible_candidate
```
