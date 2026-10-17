# PRISM external evidence inventory (2026-11-15)

This note records the latest non-promoting scan of the external workspaces that
can supply LH2 equipment, SLABx-LH2, or inspection-centre evidence.  The scan is
an intake check.  It does not convert a JSON file into a qualified release
packet, infer a frequency, or open the facility IR/F-N result.

## What was scanned

| Workspace | Scan result | JSON artifacts | Supporting files | Provider responses | Qualification records | Physical-validation claims | Complete facility-QRA claims |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `_external_lh2dt_models_20261016` | `EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY` | 1 | 2 | 0 | 0 | 0 | 0 |
| `_prism_clean_lh2dt_models_16f7a4b` | `EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY` | 1 | 2 | 0 | 0 | 0 | 0 |
| `SLABx_LH2/.release-work/DynamicLH2PoolX-review` | `EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY` | 40 | 15 | 0 | 0 | 0 | 0 |
| `액화수소검사지원센터 데이터` | `NO_EXTERNAL_JSON_ARTIFACTS` | 0 | 24 | 0 | 0 | 0 | 0 |

The inspection-centre workspace is primarily workbook and document data.  Its
signals remain useful for state and HAZOP diagnostics, but the scan found no
provider release artifact.  The LH2 model workspace contains two NASA reference
tables, and the SLABx workspace contains validation CSVs;
the separate high-resolution comparison audit is still treated as component
comparison evidence.  It is not an end-to-end accident-release validation
packet.

## Promotion boundary

The inventory keeps the following gates closed:

1. A provider packet must contain an exact event, component, port, source
   digest, result digest, mass history, and termination record.
2. A qualification sidecar must use
   `prism.provider_qualification_evidence.v1` and bind to the exact packet.
3. Independent physical validation must identify the observation source and
   the model boundary.  A model prediction, synthetic release, or numerical
   convergence record cannot satisfy this gate by itself.
4. Frequency remains literature-based.  The scan never learns a failure rate
   from workbooks, sensors, or provider output.
5. Facility IR/F-N remains withheld until every declared case has qualified
   provider evidence, a closed release boundary, and independent validation.

Consequently, this intake result is evidence that the search boundary is
explicit and reproducible; it is not evidence that the IJHE strict QRA gates
are complete.  The authoritative completion audit remains
`results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json`.

The consequence-backend contract also requires an explicit scenario-family
match.  A case with a named accident family cannot fall back to a generic
release path.  If no contract path lists that family, the case is reported as
uncomputed and its IR/F-N contribution is withheld.

The same contract now requires the facility-level diagnostic fields for the
annual weather and population partition, conditional individual risk, and
conditional F-N result.  These fields prove that the aggregation interface
was exercised; their presence does not promote synthetic conditions or
operator-limited releases to a qualified facility QRA.

## Reproduction

Run from the `lh2-tno` package directory. The current four-root combined
recheck is stored at
`results/20261115/external_provider_workspace_roots_inventory_current.json`.

```powershell
python scripts/audit_provider_artifact_workspace_roots.py `
  --root prism_clean_lh2dt="C:\Users\lyul\Desktop\DocuData\_prism_clean_lh2dt_models_16f7a4b" `
  --output results/20261115/prism_clean_lh2dt_provider_artifact_inventory_current.json

python scripts/audit_provider_artifact_workspace_roots.py `
  --root external_lh2dt="C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016" `
  --output results/20261115/external_lh2dt_provider_artifact_inventory_current.json

python scripts/audit_provider_artifact_workspace_roots.py `
  --root slabx_validation="C:\Users\lyul\Desktop\DocuData\SLABx_LH2\.release-work\DynamicLH2PoolX-review" `
  --output results/20261115/slabx_validation_provider_artifact_inventory_current.json

python scripts/audit_provider_artifact_workspace_roots.py `
  --root inspection_center="C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터" `
  --output results/20261115/inspection_center_provider_artifact_inventory_current.json
```

The generated records are local evidence ledgers and are intentionally kept
separate from source code.  They should be regenerated when a new provider
packet or field observation bundle is delivered.

## NASA TN D-4171 component benchmark

The optional `lh2dt_nasa_d4171_component_benchmark` domain records a public
closed-tank self-pressurisation benchmark from NASA TN D-4171.  The benchmark
contains 21 observations and is evaluated with an unfitted
homogeneous-equilibrium state model.  In the reproduced screening run, the
model under-predicts the measured pressure rise overall (mean absolute
percentage error about 52%); the lower-heating subset is closer than the
uniform and upper-heating subsets.  These results are useful for identifying
model-form limits and for deciding which LH2 state variables need a better
thermal boundary model.

This benchmark is deliberately restricted to component evidence.  It does not
validate an equipment accident release, isolation response, inventory
depletion, SLABx-LH2 dispersion, ignition, frequency, IR/F-N, or facility QRA.
It also cannot establish site-specific tank accuracy without a documented
geometry and boundary-condition match.

Reproduce the source run from the external model workspace, then pass the
result to the optional evidence-matrix input:

```powershell
$env:PYTHONPATH = "C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016\src"
python C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016\examples\run_nasa_d4171_benchmark.py `
  --output-dir results/20261115/lh2dt_nasa_d4171_benchmark

python scripts/build_validation_evidence_matrix.py `
  --nasa-d4171-benchmark results/20261115/lh2dt_nasa_d4171_benchmark/nasa_tn_d4171_hem_results.json `
  --output results/20261115/validation_evidence_matrix_with_nasa_d4171.json `
  # provide the required pool/equipment/facility inputs as in the normal build
```
