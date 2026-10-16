# Current external release-artifact intake (2026-10-16)

The external LH2 equipment-model roots were re-scanned after the realtime
HAZOP bridge was added. The scan is an evidence inventory, not a qualification
step. It looked for release-shaped JSON artifacts in the public `lh2dt_models`
workspace and the local tank/vent workspace, then checked whether a separate
`prism.provider_qualification_evidence.v1` sidecar was supplied.

The reproducible command was:

```powershell
python scripts/audit_external_release_artifacts.py `
  --root "C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016" `
  --root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템" `
  --output results/20261016/external_release_artifact_intake_current.json
```

The current record reports:

| Item | Count/status |
|---|---:|
| Release artifact files | 7 |
| Release rows | 7 |
| `actual` input origin rows | 0 |
| `model_prediction` or synthetic rows | 7 |
| Qualification sidecar files | 0 |
| Qualified sidecar rows | 0 |
| Overall status | `EXTERNAL_RELEASE_ARTIFACTS_REQUIRE_QUALIFICATION` |

This confirms that the existing external model outputs can be used for the
diagnostic provider path, but they cannot close the IJHE facility-QRA gate.
PRISM therefore keeps `provider_qualification_claim=false`,
`independent_physical_validation_claim=false`, and `facility_qra_claim=false`.
No frequency is inferred from these artifacts. A future promotion must attach
an exact event/component/port-matched qualification sidecar and an independent
validation reference to the same source and result digests.

The machine-readable record is
`results/20261016/external_release_artifact_intake_current.json`.
