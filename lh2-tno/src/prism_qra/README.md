# Bundled PRISM QRA

This directory contains the project-authored QRA implementation used by PRISM's
`standard` mode. The equations and frequency/consequence references are cited
in the source modules (including the Purple Book and hydrogen literature).
No book text or external proprietary source code is included.

The engine is exposed under the MIT license in this repository. Third-party
runtime packages remain under their own licenses.

Run from the PRISM repository root:

```powershell
python -m pip install -e ".[full]"  # installs public PyPI SLABx and SLABx-LH2 packages
prism --mode standard template --directory standard_inputs
prism --mode standard run --name my-facility `
  --sections standard_inputs/sections.csv `
  --components standard_inputs/components.csv `
  --assemblies standard_inputs/assemblies.csv `
  --ignition purple --blocking none --samples 0 `
  --extent 100 --cell 10 --out standard_result.json
```
