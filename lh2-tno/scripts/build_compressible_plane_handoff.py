"""Build an optional source-state-bound compressible-plane handoff.

The upstream equipment provider must have exported ``provider_source_state``
for every interval.  This command does not estimate a missing source pressure
from the atmospheric packet and does not qualify a provider or a physical
near-field model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.compressible_source_adapter import (  # noqa: E402
    CompressibleSourceAdapterError,
    build_compressible_plane_handoff,
)
from lh2_tno.contracts import canonical_digest  # noqa: E402


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--provider-response", type=Path, required=True)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-handoff", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    parser.add_argument(
        "--algorithm",
        choices=("birch_momentum_energy", "birch_momentum_isentropic"),
        default="birch_momentum_energy",
    )
    parser.add_argument("--evidence-status", default="synthetic_diagnostic")
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
        response = json.loads(args.provider_response.read_text(encoding="utf-8"))
        sys.path.insert(0, str(args.lh2dt_root.resolve() / "src"))
        from lh2dt.properties import HydrogenProperties

        source_digest = canonical_digest({
            "adapter_source_digest": _tree_digest(ROOT),
            "lh2dt_source_digest": _tree_digest(args.lh2dt_root.resolve()),
        })
        result = build_compressible_plane_handoff(
            packet,
            response,
            properties=HydrogenProperties("Hydrogen"),
            algorithm=args.algorithm,
            adapter_source_digest=source_digest,
            evidence_status=args.evidence_status,
        )
        args.output_handoff.parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.parent.mkdir(parents=True, exist_ok=True)
        args.output_handoff.write_text(
            json.dumps(result.export, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        args.output_audit.write_text(
            json.dumps(result.audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result.audit, ensure_ascii=False))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ImportError,
            TypeError, ValueError, KeyError, CompressibleSourceAdapterError) as error:
        audit = {
            "status": "COMPRESSIBLE_PLANE_HANDOFF_SOURCE_STATE_BLOCKED",
            "error": f"{type(error).__name__}: {error}",
            "provider_packet_qualified": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        }
        args.output_audit.parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(audit, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
