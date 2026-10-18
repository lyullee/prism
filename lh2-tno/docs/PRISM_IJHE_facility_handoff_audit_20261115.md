# PRISM IJHE Facility Handoff Audit (2026-11-15)

## Purpose

This record documents the latest full IJHE completion audit after adding the reconstructed liquid-hydrogen receiving-facility handoff. It is a diagnostic integration record for a generic outdoor LH2 facility. It does not convert inspection-center data into a qualified facility risk claim.

The handoff path is:

`equipment state + operating mode -> HAZOP deviation -> selected accident port -> literature frequency scenario -> provider release -> duration/isolation/inventory ledger -> SLABx-LH2 consequence -> ignition/damage risk atom -> conditional facility IR/F-N ledger`.

## Latest full-audit result

| Item | Result |
|---|---:|
| Audit record | [`ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`](../results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json) |
| Overall status | `INCOMPLETE_EVIDENCE` |
| Checks | 62 total: 57 pass, 5 blocked |
| Facility handoff diagnostic check | `PASS` (`diagnostic_only=true`) |
| Qualified provider packets | 0 |
| Independent full-chain physical validation | Not claimed |
| Qualified total-facility IR/F-N | Withheld |

The latest release-boundary ledger has 44 declared cases, 13 strict-eligible rows, and 31 blocked rows. The five blocking gates are deliberately preserved:

1. The release boundary is not closed for every declared case.
2. Available provider releases are synthetic or screening evidence.
3. Provider qualification or independent full-chain physical validation is open.
4. Facility cases do not all have an exact qualified provider packet.
5. Qualified total-facility IR/F-N is withheld while scope/evidence is incomplete or synthetic.

A blocked gate is not treated as zero risk, and no unsupported accident family is substituted for a missing case.

The default full-union receptor is a synthetic worker location at 20 m, so its conditional harm envelope is zero for the saved diagnostic atoms. The audit also consumes a separate near-receptor replay at 0.5 m: one positive harm atom reaches `worker-01`, with conditional IR `4.68e-5/year` and an `N >= 1` F/N point at the same conditional frequency. These two outputs are deliberately kept separate. The zero at the distant receptor is not interpreted as zero facility risk, and the near-receptor value is not promoted to a qualified facility total.

The machine-readable comparison is [`receptor_geometry_interpretation.json`](../results/20261115/receptor_geometry_interpretation.json), produced by [`audit_receptor_geometry_interpretation.py`](../scripts/audit_receptor_geometry_interpretation.py). It records the two manifest geometries, nearest declared equipment distances, input hashes, and the fail-closed promotion boundary.

## Inspection-center facility handoff

The dedicated handoff audit is [`inspection_center_facility_ijhe_handoff_audit.json`](../examples/inspection_center_facility_ijhe_handoff_audit.json). It has 12 structural checks and status `PASS_WITH_SCOPE_LIMITATIONS`. It verifies:

- the three reconstructed components and their receiving, standby, and supply operating modes;
- explicit HAZOP selection and provider/component/port identity;
- the canonical equipment-state snapshot and digest handoff;
- the selected supply-vaporizer diagnostic branch;
- explicit annual outdoor weather/population conditions;
- literature frequency sensitivity without sensor-based frequency learning;
- stage timing and processing-time evidence;
- conditional facility IR/F-N aggregation while the qualified total remains closed; and
- the declared major-accident boundary, including 11 explicitly unevaluated families.

The selected diagnostic branch is `vaporizer_hole`. The other declared families remain `NOT_EVALUATED_EXPLICIT`; `implicit_substitution_performed=false`.

## Reproduction

Run the facility handoff audit first:

```powershell
python scripts/audit_inspection_center_facility_ijhe_handoff.py
```

Then run the full audit with the handoff record as an optional diagnostic input. The complete command is maintained in [`PRISM_IJHE_latest_audit_20261115.md`](PRISM_IJHE_latest_audit_20261115.md). The essential additional argument is:

```powershell
--inspection-center-facility-ijhe-handoff-audit examples/inspection_center_facility_ijhe_handoff_audit.json
```

## Interpretation for a digital twin

The diagnostic chain is now connected at the data-contract level: a live state and operating mode can select a HAZOP scenario, the scenario can identify a literature event and provider port, and the resulting consequence can be accumulated into a conditional facility ledger. The current audit still prevents that chain from being presented as a validated annual facility risk. Qualification requires real accident-release exports, closed termination and inventory evidence for the declared scope, independent validation of the full consequence chain, and complete facility evidence.

## Metadata consistency check

Use the metadata verifier after regenerating the audit:

```powershell
python scripts/verify_latest_ijhe_audit.py `
  --current-status CURRENT_STATUS.json `
  --audit results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/latest_ijhe_audit_verification.json
```

A `PASS` result means that `CURRENT_STATUS.json` points to the stored audit, the check and blocker counts agree, and the facility handoff remains diagnostic-only. It does not mean that the five strict IJHE gates are open.

## Current union packet-identity re-audit

The current 34-event union was independently scanned using exact event identity
and `provider_result_digest` matching. The saved records are
[`facility_chain_packet_evidence_scan_current.json`](../results/20261115/facility_chain_packet_evidence_scan_current.json)
and [`facility_chain_closure_audit_current_union.json`](../results/20261115/facility_chain_closure_audit_current_union.json).

The rebuilt base catalog contains 23 exact native packet exports out of 24
declared base events. Combined with five existing vertical-handoff packets and five explicit
inventory namespace-rebound packets, 33 of the 34 union event identities pass
the diagnostic chain-closure check. One ambient-vaporizer G1 event remains
uncomputed. The inventory packets are source-traced diagnostic rebinds and do
not count as qualified provider evidence. Ten explicit inventory-basis aliases were
accepted only after duration, mass, and provenance checks and are recorded per
event. Conditional IR/F-N aggregation remains a diagnostic calculation, while
facility total QRA, provider qualification, frequency binding from qualified
packets, and independent facility validation remain withheld. This current-union
record supersedes the historical 24-event chain record for current status
reporting.

The rebuilt union was also converted into a new facility assessment
without rerunning provider or SLABx physics. It retains 34 events, 44 cases, and
176 risk atoms, provides conditional diagnostic IR/F-N, and keeps total facility
QRA withheld because the qualified case coverage is 0/44.

The rebuilt packet catalog and machine-readable chain audit are
[`native_full_scope_packet_catalog_current_rebuild`](../results/20261115/native_full_scope_packet_catalog_current_rebuild/)
and [`facility_chain_closure_audit_rebuilt_current_union.json`](../results/20261115/facility_chain_closure_audit_rebuilt_current_union.json).

SLABx-LH2 is treated as the frozen validated consequence component. The open
gates concern equipment release evidence, termination/inventory closure, and
facility-level qualification around that fixed component.\n

The initial inventory-extension scan found only embedded identities; that historical
gap is preserved in [`inventory_extension_packet_gap_recheck_current.json`](../results/20261115/inventory_extension_packet_gap_recheck_current.json).
The current recheck materializes five source-traced packets under an explicit
namespace rebind, checks 40 identity/value fields, and records the result in
[`inventory_extension_packet_rebind_recheck_current.json`](../results/20261115/inventory_extension_packet_rebind_recheck_current.json).
These packets remain diagnostic and unqualified.
