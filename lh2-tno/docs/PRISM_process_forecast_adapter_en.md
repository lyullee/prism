# PRISM process-model forecast adapter

`lh2_tno.process_forecast.build_forecast_frames()` is the input boundary for
process-model predictions. It converts rows from a simulator or a spreadsheet
export into the `prism.hazop_state_frame.v1` frames consumed by the existing
forecast HAZOP scanner.

The adapter does four things:

1. requires an explicit facility, component, source and operating mode;
2. converts only the units declared in the mapping to SI (`MPa`, `kPa`, `bar`,
   `Pa`, Celsius, Kelvin, mass and flow units are supported);
3. preserves the source digest, row order and forecast time; and
4. marks every frame as `origin="model_prediction"`.

It does not infer an operating mode from a text label, create a release packet,
assign an accident frequency, or promote facility IR/F-N. Those decisions stay
with HAZOP selection, the qualified provider-release contract and the separate
facility gates.

## Excel command

Install the optional workbook dependency first:

```powershell
pip install -e ".[xlsx]"
```

Then provide a JSON mapping keyed by the PRISM tag. The repository includes an
example for the inspection-centre supply forecast workbook:

```powershell
python scripts/build_process_forecast_frames.py `
  --source "C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터\3. 액화수소 공급 시나리오 데이터\액화수소_공급_예측데이터_10회차.xlsx" `
  --sheet-index 0 `
  --mapping examples/inspection_center_supply_forecast_mapping.json `
  --facility-id inspection-centre-diagnostic `
  --component-id supply-train-01 `
  --operating-mode supply `
  --source-id inspection-centre-supply-forecast-10-run `
  --sample-period-s 1 `
  --max-rows 60 `
  --output results/20261115/inspection_center_supply_forecast_frames.json
```

`--max-rows` is optional and is useful for a bounded smoke run. If the sheet
contains an explicit timestamp column, pass `--time-column` and omit the
sample-period assumption. The command records the workbook SHA-256 and the
selected row count in the output.

## Passing frames to forecast HAZOP

Read `record["frames"]` and pass it to
`run_hazop_forecast_risk_scan()` together with one HAZOP table per component.
Each forecast time must contain every expected component. The scanner then
evaluates a quantitative callback only when a declared deviation is reached.
The callback remains responsible for the provider release, SLABx-LH2 and
facility gates. A missing or unqualified provider result remains withheld.

## Evidence boundary

The inspection-centre workbooks are process-operation or prediction data. They
are useful for reproducing state and mode handoff, but they are not accident
release experiments. A workbook row cannot close a release duration,
inventory/mass ledger, provider qualification, failure frequency, or physical
validation gate. The generated record therefore reports
`diagnostic_only=true`, `frequency_inference_performed=false`, and
`facility_qra_promotion=false`.
