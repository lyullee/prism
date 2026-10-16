"""Generic entry point for a native external gas facility-frequency diagnostic.

The implementation is shared with the historical DynamicHEMPipe runner.  The
packet contract is provider-neutral: any strict gas packet with an attached
``prism.compressible_plane_handoff.v1`` can be bound to one exact literature
opening and evaluated with explicit unmatched bins.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_native_dynamic_pipe_gas_facility_frequency_case import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

