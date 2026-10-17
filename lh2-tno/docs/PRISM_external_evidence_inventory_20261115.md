# PRISM external evidence inventory (2026-11-15)

This note records the latest non-promoting scan of the external workspaces that
can supply LH2 equipment, SLABx-LH2, or inspection-centre evidence.  The scan is
an intake check.  It does not convert a JSON file into a qualified release
packet, infer a frequency, or open the facility IR/F-N result.

## What was scanned

| Workspace | Scan result | JSON artifacts | Provider responses | Qualification records | Physical-validation claims | Complete facility-QRA claims |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `_external_lh2dt_models_20261016` | `EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY` | 1 | 0 | 0 | 0 | 0 |
| `SLABx_LH2/.release-work/DynamicLH2PoolX-review` | `EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY` | 40 | 0 | 0 | 0 | 0 |
| `액화수소검사지원센터 데이터` | `NO_EXTERNAL_JSON_ARTIFACTS` | 0 | 0 | 0 | 0 | 0 |

The inspection-centre workspace is primarily workbook and document data.  Its
signals remain useful for state and HAZOP diagnostics, but the scan found no
provider release artifact.  The SLABx workspace contains validation material;
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

## Reproduction

Run from the `lh2-tno` package directory:

```powershell
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
