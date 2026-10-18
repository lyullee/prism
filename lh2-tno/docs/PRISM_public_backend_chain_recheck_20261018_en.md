# Public-backend LH2 chain recheck (2026-10-18)

This record documents a fresh consequence-chain replay using the public PRISM
backend configuration. The replay deliberately excludes the legacy `tno`
source pin. The configuration contains the project-owned `prism_qra` tree and
explicitly hashed external provider/consequence roots (`slabx_lh2`,
`dynamiclh2poolx`, and `slabx`).

## Reproduction

```powershell
python scripts/build_backend_config.py `
  --output results/20261018/backend_config_public_chain.json `
  --interpreter "C:\path\to\.venv-transfer\Scripts\python.exe" `
  --package slabx_lh2="C:\path\to\slabx_lh2" `
  --package dynamiclh2poolx="C:\path\to\dynamiclh2poolx" `
  --package slabx="C:\path\to\slabx"

python scripts/check_backend_runtime.py `
  --backend-config results/20261018/backend_config_public_chain.json `
  --output results/20261018/backend_runtime_check_public_chain.json

python scripts/run_native_external_equipment_chain_recheck.py `
  --packet-root results/20261017/native_external_multi_equipment_recheck_20261017 `
  --output-dir results/20261018/native_external_multi_equipment_chain_recheck_public_backend `
  --backend-config results/20261018/backend_config_public_chain.json `
  --facility examples/native_external_valve_chain_facility_20261017.json `
  --context examples/compressible_plane_chain_context.json
```

The runtime preflight returned `BACKEND_RUNTIME_READY` with Python 3.12.14,
CoolProp 8.0.0, NumPy 2.5.3, and SciPy 1.18.1. It completed before any risk
calculation and made no physical-validation claim.

## Result

All seven declared outdoor equipment paths reached
`END_TO_END_DIAGNOSTIC_EXECUTED`:

| Equipment | Consequence path | Result |
| --- | --- | --- |
| Layered tank | ordinary LH2 consequence path | executed |
| Dynamic transfer pipe | ordinary LH2 consequence path | executed |
| Mapped pump | ordinary LH2 consequence path | executed |
| Ambient vaporizer | ordinary LH2 consequence path | executed |
| Reliquefier | ordinary LH2 consequence path | executed |
| Vent stack | ordinary LH2 consequence path | executed |
| Transfer valve | compressible-plane handoff | executed |

The runner reported `chain_count=7`, elapsed time of about 88.1 seconds, and
`provider_packet_promoted_count=0`. The saved machine-readable evidence is
`results/20261018/backend_runtime_check_public_chain.json` and
`results/20261018/native_external_multi_equipment_chain_recheck_public_backend/manifest.json`.

This is a reproducible release-to-consequence diagnostic result. It does not
assign or learn an initiating frequency, qualify an equipment provider,
validate the complete facility physics independently, or promote facility-wide
IR/F-N. The existing fail-closed IJHE facility gate therefore remains in
force. The next evidence needed for promotion is still the qualified,
case-complete provider packet set and independent full-scope facility
validation described in the IJHE audit.
