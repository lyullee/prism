# PRISM 0.6.5 distribution

PRISM 0.6.5 is the public follow-up release to 0.6.4. It removes
machine-specific source paths from the runtime frequency catalogue and public
example records, and keeps the LH2 source-to-risk interfaces reproducible from
the repository and declared public Python dependencies.

Install the release with:

```powershell
python -m pip install "prism-risk[full]==0.6.5"
```

The release includes the project-authored PRISM QRA implementation and the
MIT-licensed LH2 source/transition interfaces under `prism_lh2_models`. The
SLABx-LH2 dispersion component remains a separately versioned public
dependency. No private local checkout is required for the packaged standard
or public LH2 diagnostic paths.

The release does not silently turn missing provider histories into zero risk.
Unsupported inventory, isolation, population, or facility-wide validation
cases remain explicit withheld/uncomputed results. The published artifacts are
research software and do not by themselves constitute regulatory certification
or a complete facility QRA.

Release links:

- GitHub: https://github.com/lyullee/prism/releases/tag/v0.6.5
- PyPI: https://pypi.org/project/prism-risk/0.6.5/
- Version DOI: https://doi.org/10.5281/zenodo.23448717
- Concept DOI: https://doi.org/10.5281/zenodo.23448413
