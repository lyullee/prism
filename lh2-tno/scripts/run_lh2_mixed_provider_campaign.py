"""Execute a compiled mixed LH2 provider campaign through the full risk chain.

This runner is deliberately separate from campaign compilation.  Compilation
proves event-id and physical-opening attachment; this command performs fresh
physics through the pinned SLABx-LH2/SLABx/TNO backend and preserves every
failed, limited, or withheld case in the returned facility ledger.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402


def _load_backend(path: Path) -> BackendConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Recompute local source pins so a deliberately updated external package is
    # either captured in this run's provenance or rejected if its root is gone.
    for package in raw.get("packages", []):
        root = Path(package["root"])
        if not root.exists():
            raise FileNotFoundError(f"backend package root does not exist: {root}")
        package["sha256"] = tree_digest(root)
    return BackendConfig.model_validate_json(json.dumps(raw, ensure_ascii=False, allow_nan=False))


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    campaign = RiskCampaign.model_validate_json(args.campaign.read_text(encoding="utf-8"))
    backend_config = _load_backend(args.backend_config)
    result = ResearchPipeline(facility, IsolatedBackend(backend_config)).facility_risk(campaign)
    _save(args.output, result)
    statuses = Counter(case.get("status", "UNKNOWN") for case in result.get("cases", ()))
    uncomputed_statuses = Counter(case.get("status", "UNKNOWN") for case in result.get("uncomputed_cases", ()))
    print(json.dumps({
        "status": result.get("status"),
        "output": str(args.output),
        "facility_id": result.get("facility_id"),
        "case_statuses": dict(statuses),
        "uncomputed_statuses": dict(uncomputed_statuses),
        "known_contribution_annual_ir_low_high": result.get("known_contribution_annual_ir_low_high"),
        "total_facility_annual_ir_low_high": result.get("total_facility_annual_ir_low_high"),
        "total_facility_expected_death_fn_low_high": result.get("total_facility_expected_death_fn_low_high"),
        "timing": result.get("timing"),
        "physical_validation_claim": result.get("physical_validation_claim"),
        "complete_facility_qra_claim": result.get("complete_facility_qra_claim"),
        "backend_config_digest": backend_config.digest(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
