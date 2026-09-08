# DepthBenchCAD evaluation records

This directory contains the record-level evaluation data released with DepthBenchCAD.

- `depthbenchcad_A_audits.jsonl`: 28,800 audit outcomes from **DepthBenchCAD-A**.
- `depthbenchcad_B_audits.jsonl`: 15,360 audit outcomes from **DepthBenchCAD-B**.
- `depthbenchcad_A_expert_annotations.jsonl`: 800 doubly annotated expert-validation items sampled from DepthBenchCAD-A.

Each audit row is keyed by system, template, generation, and frozen edit state. Internal environment IDs `A` and `B` map to DepthBenchCAD-A and DepthBenchCAD-B. The public package contains the outcome fields required by the paper analysis, including the automatic label, failure indicator, initial-validity flag, edit type, environment, and calibration/test split. Provider-side prompts, candidate source text, token usage, latency logs, and decoding metadata are outside this public release.

The checked-in records are the canonical inputs for `scripts/reproduce_tables.py`.
