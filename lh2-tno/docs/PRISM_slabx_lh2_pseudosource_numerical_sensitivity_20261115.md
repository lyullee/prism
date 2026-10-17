# SLABx-LH2 pseudo-source numerical sensitivity

PRISM now records a separate high-resolution convergence check for the
published FFI Test 6 cold hydrogen-air pseudo-source ledger. The check uses
the declared source state (`0.8 kg/s` hydrogen, `0.37` hydrogen mass fraction,
`2.4 kg/m³` source density, `70 m/s`, `120 s`, and `25 °C`) and repeats the
same SLABx calculation at 640, 1280, 2560, and 5120 field steps.

The relative change between the last two resolutions is below 0.002% for all
four monitored quantities:

- hydrogen volume fraction at 30 m;
- centreline height at 30 m;
- cloud depth at 30 m; and
- temperature at 30 m.

The machine-readable record is
[`provenance.json`](../results/20261115/slabx_lh2_pseudosource_numerical_sensitivity_high_resolution/provenance.json),
with the raw refinement rows in
[`refinement.csv`](../results/20261115/slabx_lh2_pseudosource_numerical_sensitivity_high_resolution/refinement.csv).

This is numerical sensitivity evidence for the separately declared
pseudo-source. It does not close the actual FFI Test 6 source gate, whose
`0.8317 kg/s` source remains unresolved at the tested resolution. It also does
not establish independent physical validation, equipment-release validation,
frequency inference, or facility QRA. The status ledger and IJHE verifier keep
those claims false and require the actual source record to be resolved before
any promotion.
