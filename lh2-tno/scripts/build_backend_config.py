"""Build a portable, explicitly pinned PRISM backend configuration.

The old diagnostic manifests used a legacy ``tno`` source pin.  Public PRISM
uses the project-owned ``prism_qra`` source instead; external provider roots
are supplied explicitly with repeated ``--package name=path`` arguments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import tree_digest


def _package(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("package must use name=path")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"package root does not exist: {path}")
    return name.strip(), path


def build_config(
    *,
    package_specs: list[tuple[str, Path]],
    interpreter: str,
    timeout_s: float,
    required_versions: dict[str, str],
) -> dict[str, object]:
    names = [name for name, _ in package_specs]
    if "prism_qra" not in names:
        package_specs.insert(0, ("prism_qra", ROOT / "src" / "prism_qra"))
    if len({name for name, _ in package_specs}) != len(package_specs):
        raise ValueError("package names must be unique")
    packages = []
    for name, path in package_specs:
        if not path.is_dir():
            raise ValueError(f"package root does not exist: {path}")
        packages.append({"name": name, "root": str(path), "sha256": tree_digest(path)})
    return {
        "interpreter": interpreter,
        "packages": packages,
        "timeout_s": timeout_s,
        "required_versions": required_versions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interpreter", default=sys.executable)
    parser.add_argument("--package", action="append", type=_package, default=[])
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--require-version",
        action="append",
        default=["CoolProp=8.0.0", "numpy=2.5.3", "scipy=1.18.1"],
        help="dependency pin as distribution=version; repeatable",
    )
    args = parser.parse_args()
    required: dict[str, str] = {}
    for item in args.require_version:
        name, separator, version = item.partition("=")
        if not separator or not name or not version:
            parser.error("--require-version must use distribution=version")
        required[name] = version
    config = build_config(
        package_specs=list(args.package),
        interpreter=args.interpreter,
        timeout_s=args.timeout_s,
        required_versions=required,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BACKEND_CONFIG_WRITTEN", "output": str(args.output), "package_count": len(config["packages"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
