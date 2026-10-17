# Inspection-centre source suitability boundary (15 November 2026)

This note records what the liquid-hydrogen inspection-centre files can and
cannot do in the generic outdoor LH2 PRISM workflow. The source inventory is
[`inspection_center_source_inventory_suitability.json`](../results/20261115/inspection_center_source_inventory_suitability.json).

## Evidence found

The source audit covers 17 workbooks and 78 sheets. It finds timestamp or
sequence columns, pressure signals, temperature signals, and differential
pressure signals. The audit also finds 522 numeric signal columns whose unit
basis is still missing or unconfirmed. The files therefore contain useful
process-state evidence, but their engineering meaning is not yet complete
enough for an unrestricted safety calculation.

The separate reconstructed-state path uses three explicitly labelled source
families and explicit receiving, standby, and supply modes. That path can
exercise the state-to-mode-to-HAZOP diagnostic gate. It is recorded as
reconstructed evidence and remains separate from a claim of independent
historian measurements.

The vent procedure CSV is also screened into
[`inspection_center_operation_sequence_evidence.json`](../results/20261115/inspection_center_operation_sequence_evidence.json).
It preserves the source-row digest and explicit 6.5 bar vent-operation and
6.0 bar close-operation labels. These are operational HAZOP provenance
anchors and owner-review candidates; they are not a qualified relief-device
setpoint or a release termination record.

## What the data may be used for

- Screen timestamped process-state patterns.
- Build an explicitly labelled state snapshot after the source and tag
  identity are reviewed.
- Pass an explicit operating mode to the HAZOP diagnostic table.
- Exercise the fail-closed provider and consequence interfaces using a
  separately identified diagnostic packet.

## What the data does not provide

The workbooks are normal-operation and training/recovery time-series evidence.
They do not, by themselves, provide an initiating failure or aperture, a
mass-flow time history, release duration and termination, isolation and
inventory depletion, or an independent accident-release validation case.
They also do not provide a counted failure population and exposure denominator
from which an annual failure frequency can be learned.

Consequently the source inventory does **not** promote a provider release
packet, apply a sensor-learned frequency, or authorize facility IR/F-N. The
existing PRISM flow still uses an explicitly selected literature frequency for
diagnostic scenarios; the inspection-centre signals do not change that
frequency.

The sequence sidecar follows the same boundary. It explicitly reports that
relief capacity or mass-flow history, a physical discharge-complete event, and
initial/final inventory with residual mass are missing. Those fields remain
open in the pressure-relief G1 request.

## Required evidence to close the boundary

The following items must be supplied and reviewed independently before the
source can support a qualified facility case:

1. A source-owner-approved tag and unit map, including pressure basis.
2. Equipment identity and geometry mapping for every state tag.
3. Calibration, quality, missing-data, and timestamp provenance records.
4. An accident or controlled-release record with aperture, mass flow, phase,
   duration, isolation, and inventory depletion.
5. An independent physical-validation comparison for the relevant source-term
   and dispersion path.

Until those items exist, a missing boundary remains visible as a withheld gate;
the model must not infer it from pressure or temperature alone.

## Reproduction

Run from the `lh2-tno` package directory:

```powershell
python scripts/build_inspection_center_source_inventory.py `
  --timeseries-audit results/20261106/external_support_center_timeseries_audit.json `
  --reviewed-unit-evidence results/20261014/support_center_reviewed_signal_unit_evidence.json `
  --reconstructed-state-evidence examples/inspection_center_reconstructed_state_evidence.json `
  --output results/20261115/inspection_center_source_inventory_suitability.json
```

The output is a suitability boundary record, not a QRA result. It is consumed
alongside the current IJHE objective audit and the 57-check completion audit
(52 PASS and 5 BLOCKED).

The sequence-only screen is reproducible with:

```powershell
python scripts/build_inspection_center_sequence_evidence.py `
  --source "C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터\2. 액화수소 저장(벤트) 시나리오 데이터\액화수소저장벤트_운전시퀀스.csv" `
  --scenario "액화수소 저장(벤트)" `
  --output results/20261115/inspection_center_operation_sequence_evidence.json
```
