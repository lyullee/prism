# PRISM receptor-geometry interpretation (2026-11-15)

## Why this record exists

The latest generic outdoor LH2 union has 34 events, 44 conditional cases, and
176 risk atoms. Its declared synthetic worker receptor is at `[20, 0, 1] m`.
The saved conditional IR and F/N arrays are zero at that receptor. A zero at
one declared point can mean that the calculated harm envelope does not reach
that point; it does not prove that the facility has zero risk.

PRISM therefore keeps a separate near-receptor diagnostic at `[0.5, 0, 1] m`.
That replay has 24 events, 24 cases, and 96 risk atoms. One atom reaches
`worker-01`, giving a conditional IR of `4.68e-5/year` and an `N >= 1` F/N
point at the same conditional frequency.

The two records are deliberately **not merged**. The near-receptor value is a
chain-connectivity proof, not a replacement for the full-scope receptor or a
qualified facility total.

## What is checked

`src/lh2_tno/receptor_geometry_interpretation.py` checks that:

1. each assessment matches its manifest facility ID;
2. the full-scope receptor is the declared 20 m geometry and has zero saved
   conditional IR/F/N;
3. the separate near-receptor replay retains a positive harm contribution;
4. the geometries are distinct and the near receptor is closer to declared
   equipment; and
5. both records keep facility-total IR/F/N, facility-QRA, and physical
   validation claims closed.

The result is machine-readable at
`results/20261115/receptor_geometry_interpretation.json` with SHA-256 hashes of
all four inputs. Its status is `PASS_DIAGNOSTIC_ONLY`.

## Reproduce

```powershell
python scripts/audit_receptor_geometry_interpretation.py `
  --full-scope-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --near-receptor-verification results/20261111/native_isolation_catalog_facility_chain_near_receptor_v3/verification.json `
  --full-scope-manifest examples/generic_lh2_full_scope_manifest.json `
  --near-receptor-manifest examples/generic_lh2_near_receptor_manifest.json `
  --output results/20261115/receptor_geometry_interpretation.json
```

The latest IJHE metadata verifier also follows the pointer in
`CURRENT_STATUS.json` and fails closed if the geometry record is missing,
inconsistent, or attempts to open a qualification gate:

```powershell
python scripts/verify_latest_ijhe_audit.py `
  --output results/20261115/latest_ijhe_audit_verification.json
```

## Boundary

This diagnostic does not add a site survey, population map, independent
physical validation, or a full-union near-receptor recomputation. It explains
the meaning of the two existing conditional records while preserving the
declared outdoor scope and the four strict IJHE evidence blockers.
