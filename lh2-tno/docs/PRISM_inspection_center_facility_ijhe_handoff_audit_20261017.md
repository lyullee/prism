# Inspection-centre facility handoff audit

The new audit record is a narrow, fail-closed traceability check for the
reconstructed generic outdoor LH2 facility example. It is separate from the
full IJHE completion audit because it covers one new bridge and one annual
handoff record without pretending that the whole facility has been qualified.

Run it with:

```powershell
python scripts/audit_inspection_center_facility_ijhe_handoff.py
```

It checks eleven items:

1. the facility bridge schema is the declared PRISM contract;
2. one HAZOP deviation is evaluated while two normal components remain
   explicitly withheld;
3. provider identity is carried by an explicit observed-to-provider mapping;
4. each runtime state snapshot is carried to the mapped provider boundary with
   its digest, while provider echo remains explicitly withheld;
5. the annual campaign handoff uses its declared schema;
6. weather and population come from an explicit annual-condition record;
7. the partial ledger does not claim facility-wide IR/F-N;
8. frequency rows are literature catalogue sensitivity cases, with no inferred
   p05/p95 interval; and
9. provider qualification, physical validation, and facility-QRA promotion stay
   closed; and
10. every declared outdoor major-accident family is marked either as the
    explicitly selected diagnostic branch or as `NOT_EVALUATED_EXPLICIT`.
11. facility wall time, case time, and consequence-stage processing times are
    present as finite diagnostic measurements.

The annual handoff now also carries the canonical provider-bound state snapshot
into its case identity. The reconstructed example therefore closes the
equipment-state-to-release identity audit for its one selected case. The
release-to-consequence audit is structurally closed for that case, including
stage timing and domain completeness. It remains diagnostic because the
example uses an operator-limited provider packet and does not claim provider
qualification or facility-QRA promotion.

The expected result is `PASS_WITH_SCOPE_LIMITATIONS`. That status means the
new handoff is structurally traceable. It is not a claim that the missing
normal equipment releases, qualified provider packets, independent physical
validation, or complete facility IR/F-N have been supplied. The full IJHE audit
therefore remains fail-closed until those evidence gates are closed.

The machine-readable record is
[`inspection_center_facility_ijhe_handoff_audit.json`](../examples/inspection_center_facility_ijhe_handoff_audit.json).
