"""Create the distributable DepthBenchCAD release archive."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

INCLUDED_PATHS = (
    "README.md",
    "LICENSE",
    "requirements.txt",
    ".gitignore",
    "pyproject.toml",
    "configs",
    "docs",
    "examples",
    "scripts",
    "src",
    "tests",
    "data/paper_results.json",
    "data/templates",
    "data/programs",
    "data/generations",
    "data/records",
    "data/runs/raw",
    "results/paper_reference",
    "results/reproduced",
)


def archive_members(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in INCLUDED_PATHS:
        candidate = root / relative
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(path for path in candidate.rglob("*") if path.is_file())
    return sorted(
        path for path in files
        if "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "DepthBenchCAD_release.zip")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    members = archive_members(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.write(path, path.relative_to(root).as_posix())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"archive={output}")
    print(f"files={len(members)}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
