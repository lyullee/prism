# External LH2 release-response normalization

PRISM now audits the handoff between an external equipment twin and the
release record that enters the consequence chain. A model run normally emits
two JSON records:

1. `provider_response.json` is the native model response, including the state
   snapshot digest and any provider metadata such as isolation or inventory.
2. `resolved_release.json` is the atmospheric boundary consumed by PRISM and
   SLABx-LH2. It owns the release clock, mass, port, position, and boundary
   fields used by the consequence request.

`audit_external_release_artifacts.py` pairs only a sibling
`provider_response.json` with each `resolved_release.json`. It compares the
event, component, and port identities; duration; available and released mass;
termination basis and provenance; and the provider source digest. If native
initial, final, and cumulative-out masses are present, it reports the
explicit accounting residual. If native isolation time and success are
present, it reports those values against the release clock.

The result is stored in the artifact row as
`provider_response_audit` with schema
`prism.external_release_response_normalization.v1`. A row can be
`NORMALIZED_PROVIDER_RESPONSE` while still being open for qualification. This
means that the two records agree on the fields they both carry; it does not
mean that the release boundary is closed.

The audit intentionally leaves these gaps visible:

- a response without a digest-bound `provider_result_digest` cannot establish
  exact result provenance;
- a nonzero residual or a missing mass ledger cannot be repaired by the
  intake;
- `synthetic_diagnostic_horizon` is not converted into a physical termination;
- a residual upstream inventory is not changed to zero;
- `model_prediction` remains diagnostic and cannot become field/actual
  evidence;
- no frequency, physical-validation claim, or facility IR/F-N result is
  created.

For the current seven external model exports, all seven response/release
pairs have matching identity, clock, mass, termination, and source-digest
fields. The normalized count is therefore 7/7. All seven remain
`model_prediction` rows without an exact qualification sidecar, so the strict
IJHE blockers are unchanged. The machine-readable report is
`results/20261115/external_native_contract_intake_current.json`.

To reproduce the intake:

```powershell
python scripts/audit_external_release_artifacts.py `
  --root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델\tmp_native_contract" `
  --output results/20261115/external_native_contract_intake_current.json
```

The normalized handoff is a useful integration check before sending a release
to the SLABx-LH2 route. It does not replace the exact qualification sidecar,
independent holdout validation, literature frequency binding, or the
facility-level release-boundary gate.
