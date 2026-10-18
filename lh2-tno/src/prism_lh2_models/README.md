# PRISM LH2 source and near-field interfaces

These nine modules were already used by historical PRISM calculations from a
local MIT-licensed integration source. They were absent from the public
SLABx-LH2 repository and wheels. PRISM now distributes them under the separate
`prism_lh2_models` namespace, with their original MIT license and attribution.

The Python source is copied without changes to equations, coefficients,
defaults, or numerical algorithms. Relative imports continue to resolve within
this package. `SOURCE_PROVENANCE.json` stores portable UTF-8/LF source hashes.

This package contains source discharge, droplets, cryogenic exchange, jet/cloud
transition, and conservative handoff interfaces. The validated SLABx-LH2
dispersion component is installed separately; its code and validation status
are not changed by this packaging work. A source/transition module being
available does not establish independent validation for a facility case.

Use the installed-package configurator from a source checkout:

```powershell
python -m pip install -e ".[full]"
python -m lh2_tno.public_backend --require-operation integrated_source --require-operation consequence_chain --output build/public_backend.json
```

Each model root is pinned explicitly. Existing manifests naming an external
`slabx_lh2` integration tree continue to select that tree. Configurations naming
`prism_lh2_models` select this package; a failure does not switch models.

Pool and equipment operations still require their own explicitly installed
providers, source pins, and case-specific evidence.
