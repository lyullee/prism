"""Backward-compatible import alias for the PRISM command line interface."""
from prism_cli import *  # noqa: F401,F403

if __name__ == "__main__":
    raise SystemExit(main())
