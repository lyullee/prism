# External provider-root audit (2026-10-17)

PRISM now has a repeatable audit for checking more than one external
workspace at the same time. This matters because process-model exports and
older PRISM replay outputs are often stored in different folders. The audit
keeps the roots separate and reports the union only as an evidence inventory.
It never merges a diagnostic artifact into a provider packet.

## Reproduction

~~~powershell
python scripts/audit_provider_artifact_workspace_roots.py --root prism-dev="<PRISM_IJHE_step1 root>" --root lh2-digital-twin="<LH2 digital-twin root>" --output provider_roots_audit.json
~~~

The older flags named 'current-root' and 'legacy-root' remain accepted for
backward-compatible review notes.

## Recheck result

The workspace recheck is summarized in
[provider_artifact_roots_recheck_20261017.json](../examples/provider_artifact_roots_recheck_20261017.json).

| Root | JSON artifacts | Provider responses | Verification files | Qualification records |
|---|---:|---:|---:|---:|
| PRISM development replay | 84 | 2 | 12 | 0 |
| LH2 digital-twin workspace | 662 | 7 | 9 | 0 |
| **Total** | **746** | **9** | **21** | **0** |

All 746 artifacts remain diagnostic-only in this recheck. No artifact claimed
independent physical validation or a complete facility QRA. Consequently the
report keeps facility_ir_fn_allowed=false, assigns no frequency, and promotes
no release packet.

This inventory is evidence that the search boundary was widened; it is not
evidence that the missing provider qualification or physical-validation gates
are closed. A future actual packet must still carry an exact event,
component, port, source/result digest pair, release ledger, isolation and
inventory closure, and its qualification sidecar.
