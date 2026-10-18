"""Build explicit source pins from this interpreter's installed public models.

Discovery records source locations and hashes; it does not download models,
substitute a missing model, or qualify facility evidence. The PRISM QRA root
always comes from the same distribution as this adapter.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

from .backend import BackendConfig, PackagePin, tree_digest


PUBLIC_PACKAGES = ("prism_qra", "prism_lh2_models", "slabx", "slabx_lh2", "dynamiclh2poolx", "lh2dt")
DEFAULT_PACKAGES = ("prism_qra", "prism_lh2_models", "slabx", "slabx_lh2")
OPERATION_MODULES = {
    "thermal_damage": {"prism_qra": ("risk.py",)},
    "facility_risk_aggregate": {"prism_qra": ("risk.py",)},
    "integrated_source": {"source_interfaces": ("integrated_lh2_source.py",)},
    "declared_pool": {"dynamiclh2poolx": ("__init__.py",)},
    "consequence_chain": {
        "prism_qra": ("fire.py", "risk.py", "damage.py", "ignition.py"),
        "slabx": ("core/plume.py", "core/source.py", "submodels/atmosphere.py",
                  "thermo/base.py", "thermo/coolprop.py"),
        "source_interfaces": ("lh2_jet_cloud_transition.py", "freejet_handoff.py"),
        "slabx_lh2": ("water_ice.py",),
    },
}


def installed_backend_config(
    packages: tuple[str, ...] = DEFAULT_PACKAGES, *, timeout_s: float = 120.0,
    require_operations: tuple[str, ...] = (),
) -> BackendConfig:
    """Pin exactly the requested installed packages without a local source map.

    Use ``packages=("prism_qra",)`` for harm/IR/F-N arithmetic. Full source,
    dispersion, pool and equipment operations need their respective packages
    explicitly listed and installed in this interpreter.
    """
    if not packages or len(set(packages)) != len(packages):
        raise ValueError("nonempty unique public package names required")
    unknown = set(packages) - set(PUBLIC_PACKAGES)
    if unknown:
        raise ValueError(f"unsupported public package names: {', '.join(sorted(unknown))}")
    pins = []
    for name in packages:
        if name in {"prism_qra", "prism_lh2_models"}:
            root = Path(__file__).resolve().parents[1] / name
            required = "qra.py" if name == "prism_qra" else "integrated_lh2_source.py"
            if not (root / required).is_file():
                raise ValueError(f"bundled {name} is missing from this distribution")
        else:
            spec = importlib.util.find_spec(name)
            if spec is None or not spec.origin or not spec.submodule_search_locations:
                raise ValueError(
                    f"requested public model is not installed: {name}; "
                    "install the reviewed model in this interpreter before configuring it"
                )
            root = Path(spec.origin).resolve().parent
        pins.append(PackagePin(name=name, root=str(root), sha256=tree_digest(root)))
    versions = {}
    for name in ("pydantic", "numpy", "scipy", "CoolProp"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    config = BackendConfig(
        interpreter=sys.executable, packages=tuple(pins),
        timeout_s=timeout_s, required_versions=versions,
    )
    unknown = set(require_operations) - set(OPERATION_MODULES)
    if unknown:
        raise ValueError(f"unsupported operation checks: {', '.join(sorted(unknown))}")
    capabilities = backend_interface_audit(config)
    for operation in require_operations:
        if capabilities[operation]["missing_interfaces"]:
            raise ValueError(
                f"{operation} requires unavailable interfaces: "
                + ', '.join(capabilities[operation]["missing_interfaces"])
            )
    return config


def backend_interface_audit(config: BackendConfig) -> dict:
    """Report missing interface files without claiming physics qualification."""
    roots = {pin.name: Path(pin.root) for pin in config.packages}
    if "tno" in roots and "prism_qra" not in roots:
        roots["prism_qra"] = roots["tno"]
    if "prism_lh2_models" in roots:
        roots["source_interfaces"] = roots["prism_lh2_models"]
    elif "slabx_lh2" in roots:
        roots["source_interfaces"] = roots["slabx_lh2"]
    report = {}
    for operation, packages in OPERATION_MODULES.items():
        missing = [
            f"{name}/{module}" for name, modules in packages.items() for module in modules
            if name not in roots or not (roots[name] / module).is_file()
        ]
        report[operation] = {
            "interface_files_present": not missing, "missing_interfaces": missing,
            "physical_validation_claim": False,
        }
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", nargs="+", choices=PUBLIC_PACKAGES, default=DEFAULT_PACKAGES)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--require-operation", action="append", choices=OPERATION_MODULES, default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = installed_backend_config(
            tuple(args.packages), timeout_s=args.timeout_s,
            require_operations=tuple(args.require_operation),
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "SOURCE_PINNED", "output": str(args.output.resolve()),
        "packages": [p.name for p in config.packages], "backend_config_digest": config.digest(),
        "interface_audit": backend_interface_audit(config),
        "physical_validation_claim": False, "facility_qra_promotion": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
