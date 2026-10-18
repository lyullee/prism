"""Create and verify a deterministic SHA256 manifest for a transfer folder."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import re


SENSITIVE_NAME = re.compile(r"(?i)(api.?token|password|secret|recovery.?codes?|복구.?코드|토큰)")
TEXT_EXTENSIONS = {".md", ".txt", ".py", ".toml", ".yaml", ".yml", ".json", ".csv", ".ini", ".ps1"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory(root: Path, manifest: Path) -> list[tuple[str, int, str]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"symbolic link/reparse target not allowed: {path}")
        if not path.is_file() or path.resolve() == manifest.resolve():
            continue
        relative = path.relative_to(root).as_posix()
        if SENSITIVE_NAME.search(relative):
            raise RuntimeError(f"sensitive filename in transfer bundle: {relative}")
        rows.append((relative, path.stat().st_size, digest(path)))
    return rows


def scan_absolute_paths(root: Path, output: Path, old_prefix: str) -> int:
    matches = []
    needle = old_prefix.lower()
    for path in sorted(root.rglob("*")):
        if (not path.is_file() or path == output or path.suffix.lower() not in TEXT_EXTENSIONS
                or path.stat().st_size > 5 * 1024 * 1024):
            continue
        try:
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
                if needle in line.lower():
                    matches.append(f"{path.relative_to(root).as_posix()}:{line_no}")
        except UnicodeError:
            continue
    output.write_text("\n".join(matches) + ("\n" if matches else ""), encoding="utf-8")
    return len(matches)


def write_manifest(root: Path, manifest: Path):
    rows = inventory(root, manifest)
    with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("relative_path", "size_bytes", "sha256"))
        writer.writerows(rows)
    return rows


def verify(root: Path, manifest: Path):
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        expected = {row["relative_path"]: (int(row["size_bytes"]), row["sha256"])
                    for row in csv.DictReader(stream)}
    actual = {path.relative_to(root).as_posix(): (path.stat().st_size, digest(path))
              for path in root.rglob("*") if path.is_file() and path.resolve() != manifest.resolve()}
    missing, extra = sorted(set(expected)-set(actual)), sorted(set(actual)-set(expected))
    changed = sorted(k for k in set(expected)&set(actual) if expected[k] != actual[k])
    if missing or extra or changed:
        raise RuntimeError(f"manifest mismatch missing={len(missing)} extra={len(extra)} changed={len(changed)}")
    return len(expected), sum(x[0] for x in expected.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scan-prefix")
    parser.add_argument("--scan-output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root, manifest = args.root.resolve(), args.manifest.resolve()
    if args.verify:
        count, total = verify(root, manifest)
        print(f"VERIFIED files={count} bytes={total}")
        return
    if args.scan_prefix:
        if args.scan_output is None:
            raise ValueError("--scan-output required with --scan-prefix")
        count = scan_absolute_paths(root, args.scan_output.resolve(), args.scan_prefix)
        print(f"absolute_path_references={count}")
    rows = write_manifest(root, manifest)
    print(f"MANIFEST files={len(rows)} bytes={sum(x[1] for x in rows)}")


if __name__ == "__main__":
    main()
