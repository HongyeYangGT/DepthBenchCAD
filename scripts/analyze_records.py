"""Produce a JSON report from a real audit JSONL file."""

from __future__ import annotations

import argparse
import json

from depthbenchcad.allocation import optimize_allocation
from depthbenchcad.io import load_audits
from depthbenchcad.metrics import cluster_confidence_interval, program_mse_against_full, risk
from depthbenchcad.variance import estimate_variance_components


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("records")
    p.add_argument("--budget", type=float, default=1024)
    p.add_argument("--template-cost", type=float, default=2)
    p.add_argument("--generation-cost", type=float, default=1)
    p.add_argument("--edit-cost", type=float, default=1)
    p.add_argument("--out")
    args = p.parse_args()
    all_records = load_audits(args.records)
    pending_review = [record for record in all_records if record.failed is None and record.metadata.get("review_required")]
    if pending_review:
        raise SystemExit(
            f"{len(pending_review)} audit rows are in the automatic-judge tolerance gray zone; "
            "apply manual review labels before risk analysis"
        )
    records = [record for record in all_records if record.failed is not None]
    infrastructure_gaps = len(all_records) - len(records)
    if not records:
        raise SystemExit("no observed audit labels; inspect infrastructure failures in the JSONL log")
    v = estimate_variance_components(records)
    templates = len({r.template_id for r in records})
    pairs = {(r.template_id, r.generation_id) for r in records}
    generations = max(1, len(pairs) // max(templates, 1))
    allocation = optimize_allocation(v, args.budget, args.template_cost, args.generation_cost, args.edit_cost, templates, generations, 16)
    smallest = min(sum(1 for x in records if x.template_id == t and x.generation_id == g) for t, g in pairs)
    report = {
        "risk": risk(records),
        "variance_components": v.__dict__,
        "cluster_ci95": cluster_confidence_interval(records),
        "allocation": allocation.__dict__,
        "program_mse_k4": program_mse_against_full(records, min(4, smallest), repeats=200),
        "records": len(records),
        "infrastructure_gaps": infrastructure_gaps,
    }
    rendered = json.dumps(report, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
