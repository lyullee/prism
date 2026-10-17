# External LH2 model change recheck — 2026-10-18

This note records a fresh comparison between the current PRISM handoff and the latest local `lh2dt_models` checkout. It is a diagnostic recheck and does not replace the authoritative facility assessment.

## What changed in the external model

The checkout is at `16f7a4b38d16295ad481492ec90af7903125d4ee` with Python source digest `cef8e1965e54a1156cc914518fadf5aa955683b22f30212b6f85cf67400d1843`. Since the earlier packet generation, the model added an explicit `prism.provider_dynamic_state_closure.v1` export. The added evidence binds a provider state-history digest, inventory-feedback closure, pressure-feedback closure, residual tolerances, and the provider's own provenance. The latest changes also record native vaporizer isolation closure and reliquefier closure provenance.

The corresponding source changes are in commits `959aeff`, `65a5e70`, and `16f7a4b`. PRISM already has the receiving-side contract and preserves this record inside `provider_mass_balance.dynamic_state_closure`; no SLABx-LH2 code or validation was changed.

The latest external checkout test suite also passes: **376 passed, 1 warning**.

## What changed in the packet evidence

The latest saved external full-scope packet root contains 22 resolved-release packets. Thirteen declare the dynamic-state closure record. The remaining packets are still intentionally open for their own reasons, such as valve, pump, vent, or an older diagnostic export. This count is a packet-level diagnostic count, not a qualification count.

For the current three-branch header-bound replay:

| Selected branch | Latest packet | Dynamic state closure | Termination basis |
| --- | --- | --- | --- |
| Intake tank / receiving | `storage-shell/AREA_0.01%` | declared and ready | reviewed isolation success |
| Storage vent / standby | `pressure-relief-vent/G1` | not declared; emergency-relief packet | emergency relief discharge |
| Supply vaporizer / supply | `ambient-vaporizer/G3` | declared and ready | reviewed isolation success |

The new packet root was replayed through the existing header-bound HAZOP bridge. All three selected scenarios passed packet preflight and executed the consequence path. The candidate replay took about 126.9 s wall time for the three-branch batch. Frequency uncertainty remains partial: one branch has explicit low/published/high bounds and two do not. The facility annual IR/F-N result remains withheld.

The bridge now carries the provider dynamic-state audit into each branch record
and reports two closure-ready scenarios and one blocked scenario in its facility
audit. This is a visibility and traceability improvement; it does not change
the qualification gate.

The reconstructed single-supply inspection-centre bridge now exposes the same
audit in its branch and facility records, so current-state and header-bound
runtime paths use one closure-status vocabulary.

The earlier 2026-10-18 replay used the older packet root and classified all three components as operator-limited because the dynamic closure field was absent. That older result remains the authoritative replay record. The new run is a candidate comparison, so it does not silently replace the authoritative union assessment.

## Interpretation

The model has changed in a useful way: the tank and vaporizer branches now provide the exact dynamic closure evidence that PRISM was previously asking the provider to supply. This improves the release-to-consequence handoff and reduces one source of operator-limited status for those packet identities.

The change does not by itself provide a qualified provider packet, a facility frequency, independent physical validation, a site population basis, or facility IR/F-N. Those gates remain closed. SLABx-LH2 stays outside active development and remains the frozen validated consequence component requested by the project.

Machine-readable details are in [`external_model_change_recheck_20261018.json`](../results/20261018/external_model_change_recheck_20261018.json). The candidate bridge output is [`header_bound_facility_bridge_latest_packets_recheck.json`](../results/20261018/header_bound_facility_bridge_latest_packets_recheck.json).
