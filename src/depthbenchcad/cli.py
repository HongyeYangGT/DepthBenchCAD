"""Command-line entry points for analysis and allocation."""

from __future__ import annotations

import argparse
import json
from .allocation import optimize_allocation
from .io import load_audits
from .metrics import cluster_confidence_interval, program_mse_against_full, risk
from .variance import estimate_variance_components


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="depthbenchcad")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="analyze a JSONL audit pool")
    analyze.add_argument("records")
    analyze.add_argument("--k", type=int, default=4)
    analyze.add_argument("--budget", type=float, default=1024)
    analyze.add_argument("--template-cost", type=float, default=2)
    analyze.add_argument("--generation-cost", type=float, default=1)
    analyze.add_argument("--edit-cost", type=float, default=1)
    allocate = sub.add_parser("allocate", help="search q/g/k under a budget")
    allocate.add_argument("--template-variance", type=float, required=True)
    allocate.add_argument("--generation-variance", type=float, required=True)
    allocate.add_argument("--edit-variance", type=float, required=True)
    allocate.add_argument("--budget", type=float, default=1024)
    allocate.add_argument("--generation-cost", type=float, default=1)
    args = parser.parse_args(argv)
    if args.command == "allocate":
        from .variance import VarianceComponents
        result = optimize_allocation(VarianceComponents(args.template_variance, args.generation_variance, args.edit_variance), args.budget, 2, args.generation_cost, 1, 72, 5, 16, 72, 5)
        print(json.dumps(result.__dict__, indent=2))
        return 0
    all_records = load_audits(args.records)
    pending_review = [record for record in all_records if record.failed is None and record.metadata.get("review_required")]
    if pending_review:
        raise SystemExit(
            f"{len(pending_review)} audit rows are in the automatic-judge tolerance gray zone; "
            "apply manual review labels before risk analysis"
        )
    records = [record for record in all_records if record.failed is not None]
    if not records:
        parser.error("audit file contains no observed labels (only infrastructure gaps)")
    components = estimate_variance_components(records)
    interval = cluster_confidence_interval(records)
    result = optimize_allocation(components, args.budget, args.template_cost, args.generation_cost, args.edit_cost, max(1, len({r.template_id for r in records})), max(1, len({r.generation_id for r in records})), 16)
    smallest = min(
        sum(1 for item in records if item.template_id == template and item.generation_id == generation)
        for template, generation in {(item.template_id, item.generation_id) for item in records}
    )
    output = {
        "risk": risk(records),
        "variance_components": components.__dict__,
        "cluster_ci95": interval,
        "allocation": result.__dict__,
        "program_mse": program_mse_against_full(records, min(args.k, smallest), repeats=200),
        "records": len(records),
        "infrastructure_gaps": len(all_records) - len(records),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
