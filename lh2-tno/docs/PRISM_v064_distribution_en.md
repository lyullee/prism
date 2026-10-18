# PRISM 0.6.4 distribution

Prepared on 2026-10-18 (Asia/Seoul).

## Release contents

This release bundles the project-authored PRISM QRA implementation, including
the standard `qra`, `risk`, `damage`, `fire`, and `ignition` modules. Standard
mode uses this bundled implementation without an unpublished backend folder.
`prism_cli` is the command entry point; older command/import aliases remain
available for existing integrations.

The `full` extra uses public PyPI distributions `slabx==1.0.7` and
`slabx-lh2==0.1.5`. This makes installation possible using only PyPI.
Historical research results retain their original source digests and model
versions. This distribution change does not requalify those results or open
the documented facility evidence gates.

## Install and run

Requires Python 3.12 or newer.

```powershell
python -m pip install "prism-risk[full]==0.6.4"
prism --describe-modes
prism --mode standard template --directory standard_inputs
prism --mode standard run --name demo --sections standard_inputs/sections.csv --components standard_inputs/components.csv --assemblies standard_inputs/assemblies.csv --ignition purple --blocking none --samples 0 --extent 100 --cell 25 --out standard_result.json
```

The generated tables are examples. Review their equipment, inventory, release,
weather, ignition, and population assumptions before analyzing a real facility.

For source verification:

```powershell
git clone https://github.com/lyullee/prism.git
cd prism/lh2-tno
python -m pip install -e ".[full,test,xlsx]"
python -m pytest -q
```

## Verification

- Separate Python environment with public PyPI dependencies: 1,577 tests passed.
- Both source distribution and wheel built successfully.
- Strict package metadata check, dependency check, and installed-wheel
  standard-mode calculation: passed.
- GitHub release: https://github.com/lyullee/prism/releases/tag/v0.6.4
- PyPI version: https://pypi.org/project/prism-risk/0.6.4/

Published version DOI: https://doi.org/10.5281/zenodo.23448414

New GitHub-managed series DOI: https://doi.org/10.5281/zenodo.23448413

GitHub CI: https://github.com/lyullee/prism/actions/runs/39107860644

PyPI publishing workflow: https://github.com/lyullee/prism/actions/runs/39107880124

The public PyPI wheel was downloaded, installed into a separate environment,
and used to generate templates and calculate a standard result with
`engine=bundled_prism_qra`. Both GitHub workflows completed successfully.

## Documentation

- [User manual](PRISM_USER_MANUAL_en.md)
- [Digital-twin interface guide](PRISM_INTERFACE_INTEGRATION_GUIDE_en.md)
- [Public source and execution boundary](PRISM_public_private_boundary_and_KGS_interpretation_20261018.md)

The previous archive series is https://doi.org/10.5281/zenodo.23241358.
Enabling GitHub automatic archiving created a new archive series. The previous
record is linked with `isNewVersionOf`; its older concept DOI remains available
for the historical releases. Use the v0.6.4 DOI above to cite this release.

## Published file checksums

- `prism_risk-0.6.4-py3-none-any.whl`: SHA-256 `ecdef4f75b1d7a55295b4ce99733c8ba484d366dd2f8cabe0edda197c4debbd6`
- `prism_risk-0.6.4.tar.gz`: SHA-256 `ab8da776ff1c4b698ff44bd5395a3a608da7afeac6751669a481a1b4b3442f23`
