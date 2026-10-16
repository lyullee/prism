# Partial LH2 boundary evidence

The inspection-centre procedure documents are useful evidence for operating
limits, pressure monitoring, and valve/vent commands. They are not accident
release packets. PRISM now records this distinction with
`prism.partial_lh2_boundary_evidence.v1`.

Run the audit with:

```powershell
python scripts/audit_partial_lh2_boundary_evidence.py `
  --manifest examples/inspection_center_partial_boundary_evidence_manifest.json `
  --output results/20261117/inspection_center_partial_boundary_evidence.json
```

The audit records source SHA-256 values and verifies page anchors. A positive
anchor can support a procedure or alarm provenance row, but it cannot supply
the fields required to close an accident case:

- provider-owned release duration and stopping event;
- reviewed PSV set pressure and relief capacity;
- isolation or inventory-depletion evidence;
- initial/final inventory and mass residual; or
- an annual failure frequency and its exposure denominator.

The result therefore keeps provider-packet, frequency, physical-validation, and
facility IR/F-N promotion false. The procedure evidence can be attached to a
future provider response as supporting context, but it does not substitute for
that response.
