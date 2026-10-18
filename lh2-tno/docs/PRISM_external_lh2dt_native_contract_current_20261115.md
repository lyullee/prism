# External `lh2dt` native accident-contract audit (current recheck)

## Scope and result

PRISM rechecked the external LH2 digital-twin checkout currently used for the diagnostic handoff:

- external checkout: `C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016`
- Git HEAD: `7072374c59b726f4e938cd37e7695684ddc70b68`
- Python source digest: `3b186dff343bd787567033e13b62954a748bce0f12ba26b981d03bafe3d02d74`
- native accident exporters: **7/7** bound equipment classes
- PRISM diagnostic adapter contracts: **7/7**
- qualified provider packets promoted: **0**
- frequency inference promoted: **false**
- facility-QRA claim promoted: **false**

The audit confirms the accident-export code boundary for `LayeredTank`, `DynamicHEMPipe`,
`StrokeLimitedCommandedValve`, `VentStack`, `MappedPump`, `DynamicVaporizer`, and
`DynamicReliquefier`. It does not turn model-method presence into field evidence or a
qualified release packet. The worktree is dirty because benchmark files are present; the
recheck therefore remains diagnostic and is kept separate from the authoritative facility
campaign.

The machine-readable records are [`lh2dt_native_contract_audit_current.json`](../results/20261115/lh2dt_native_contract_audit_current.json),
[`lh2dt_native_contract_audit_7072374_recheck.json`](../results/20261115/lh2dt_native_contract_audit_7072374_recheck.json), and
[`external_lh2_model_root_review_current_7072374.json`](../results/20261115/external_lh2_model_root_review_current_7072374.json).
The previous `16f7a4b` audit is preserved as [`lh2dt_native_contract_audit_prior_16f7a4b.json`](../results/20261115/lh2dt_native_contract_audit_prior_16f7a4b.json).

## Reproduce

```powershell
python scripts/audit_lh2dt_native_contract.py `
  --binding examples/generic_lh2_model_binding.json `
  --external-root "C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016" `
  --output results/20261115/lh2dt_native_contract_audit_current.json

python scripts/review_external_lh2_model_root.py `
  --source-root "C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016" `
  --output results/20261115/external_lh2_model_root_review_current_7072374.json
```

## Promotion boundary

The latest source change was checked against the existing seven-equipment diagnostic
manifest. No provider qualification sidecar, independent physical-validation artifact,
site-specific population basis, or complete facility IR/F-N evidence was found. The
release-boundary audit therefore remains the controlling gate. SLABx-LH2 is unchanged and
continues as the frozen validated consequence component requested by the project.

Before any authoritative campaign rebinding, the external model must be fixed to a
reviewed release commit and each provider packet must carry exact event/component/port,
source/result digest, termination, isolation, and mass/inventory closure evidence.
