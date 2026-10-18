"""Resolve optional external provider checkouts without machine-specific paths."""
from __future__ import annotations

import os
from pathlib import Path


def required_external_path(variable: str, description: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise SystemExit(
            f"{description} is an external input. Set {variable} to its local checkout "
            "before running this provider-specific diagnostic."
        )
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"{variable} does not exist: {path}")
    return path
