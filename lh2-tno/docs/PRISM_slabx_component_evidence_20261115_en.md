# PRISM SLABx-LH2 component evidence

The current facility evidence matrix records SLABx-LH2 as a consequence-model component. It does not promote the model to a validated facility-QRA engine.

## Current records

The current matrix is:

```text
results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/validation_evidence_matrix.json
```

It has nine evidence domains and remains `RESTRICTED_EVIDENCE_MATRIX` with decision `FACILITY_QRA_WITHHELD`. The matrix keeps every promotion claim false: equipment-release validation, frequency inference, independent full-chain physical validation, and facility QRA.

Two additional SLABx comparison domains are now bound to the current matrix:

| Domain | Evidence | Recorded result | Allowed interpretation |
|---|---|---|---|
| `slabx_lh2_direct_component_comparison` | FFI Test 4, 30 matched sensors, 275 s operator | MAE 0.648 vol%, RMSE 1.211 vol%, LFL TP/FN/FP = 3/0/0 | Same-operator component comparison; not an independent holdout |
| `slabx_lh2_independent_comparison` | FFI Test 6, 30 sensors | MAE 1.867 vol%, RMSE 4.536 vol%, LFL TP/FN/FP = 3/3/0 | Independent comparison is recorded, but the source/numerical gate remains a review item |

The direct comparison checks the 320/32 to 640/64 refinement, recomputed metrics, LFL classification, and no-fitting provenance. The independent comparison is kept separate because its false-negative count and source-gate status must remain visible. Neither record validates the equipment release boundary, isolation and inventory depletion, initiating-event frequency, ignition/fire/IR-F/N, or the complete facility chain.

## Rebuilding the matrix

The generic builder accepts both records:

```powershell
python scripts/build_validation_evidence_matrix.py `
  --pool-record results/20261009/validation_evidence/dynamiclh2poolx_stage_c_prism_record_git_blob.json `
  --equipment-audit results/20261009/validation_evidence/equipment_validation_audit_live.json `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --native-contract results/20261022/lh2dt_native_contract_audit_native_catalog.json `
  --slabx-validation results/20261024/slabx_lh2_validation_audit_v1.json `
  --ijhe-audit results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json `
  --external-sweep examples/center_lh2_external_sweep_audit.json `
  --slabx-direct-comparison results/20261106/slabx_lh2_direct_comparison_audit.json `
  --slabx-independent-comparison results/20261115/slabx_lh2_independent_comparison_high_resolution.json `
  --output results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/validation_evidence_matrix.json
```

When rebuilding a native union with `scripts/bind_native_full_scope_union_evidence.py`, use `--slabx-direct-comparison-evidence` and `--slabx-independent-comparison-evidence`. These options only add traceable component domains; they cannot open the physical-validation or facility-QRA gates.
