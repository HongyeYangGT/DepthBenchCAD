"""Run real model programs against frozen template states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from depthbenchcad.audit import sample_frozen_states
from depthbenchcad.executor import audit_generation
from depthbenchcad.generator import execute_generation, validate_generation_input
from depthbenchcad.io import load_templates, write_jsonl
from depthbenchcad.schema import GenerationRecord


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", required=True)
    parser.add_argument("--generations", required=True, help="JSONL model output manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--states", type=int, default=16)
    args = parser.parse_args()
    if args.states < 1:
        parser.error("--states must be a positive integer")
    templates = {t.template_id: t for t in load_templates(args.templates)}
    rows = validate_generation_input(args.generations)
    generations: list[GenerationRecord] = []
    audits = []
    manifest_dir = Path(args.generations).resolve().parent
    for row in rows:
        if row["template_id"] not in templates:
            raise ValueError(f"unknown template_id: {row['template_id']}")
        template = templates[row["template_id"]]
        if args.states > len(template.states):
            raise ValueError(
                f"--states={args.states} exceeds {row['template_id']} state population {len(template.states)}"
            )
        generation = execute_generation(template, row, manifest_dir=manifest_dir)
        generations.append(generation)
        for state in sample_frozen_states(template, args.states):
            audits.append(audit_generation(template, generation, state))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out, audits)
    write_jsonl(out.with_name(out.stem + "_generations.jsonl"), generations)
    print(json.dumps({"generations": len(generations), "audits": len(audits), "output": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
