"""Materialize the complete frozen CAD task corpus for DepthBenchCAD.

The canonical task definitions live in :mod:`depthbenchcad.catalog`. They
implement the paper's two environments as fourteen distinct parametric CAD
families: 72 templates in DepthBenchCAD-A and 48 templates in DepthBenchCAD-B.
Each template contains a program contract and sixteen frozen legal edit states.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from depthbenchcad.catalog import catalog_summary, write_catalog
from depthbenchcad.io import load_templates


EXPECTED = {
    "A": {"templates": 72, "families": 8, "states": 72 * 16},
    "B": {"templates": 48, "families": 6, "states": 48 * 16},
    "both": {"templates": 120, "families": 14, "states": 120 * 16},
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the 120-task DepthBenchCAD corpus and frozen edit-state manifest"
    )
    parser.add_argument("--environment", choices=("A", "B", "both"), default="both")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = write_catalog(root, args.environment)
    summary = catalog_summary(load_templates(output))
    if summary != EXPECTED[args.environment]:
        raise RuntimeError(
            f"catalog cardinality mismatch: expected {EXPECTED[args.environment]}, got {summary}"
        )
    print(
        f"wrote {summary['templates']} templates, {summary['families']} families, "
        f"and {summary['states']} frozen edit states to {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
