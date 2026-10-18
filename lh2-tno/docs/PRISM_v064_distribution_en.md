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
- Strict package metadata check and installed-wheel standard-mode smoke test
  are required before publication.
- GitHub release: https://github.com/lyullee/prism/releases/tag/v0.6.4
- PyPI version: https://pypi.org/project/prism-risk/0.6.4/

Publication evidence and the version DOI are recorded below once confirmed.

## Documentation

- [User manual](PRISM_USER_MANUAL_en.md)
- [Digital-twin interface guide](PRISM_INTERFACE_INTEGRATION_GUIDE_en.md)
- [Public source and execution boundary](PRISM_public_private_boundary_and_KGS_interpretation_20261018.md)

The previous archive series is https://doi.org/10.5281/zenodo.23241358.
The v0.6.4 GitHub-triggered archive must be cited using its confirmed version
DOI after publication; a reserved or unresolvable identifier is not a published
version DOI.
