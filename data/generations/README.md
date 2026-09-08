# DepthBenchCAD generation records

This directory contains the released generation-level records for DepthBenchCAD. There are 1,800 records for **DepthBenchCAD-A** and 960 for **DepthBenchCAD-B**. Each generation links one system/template/generation identity to its 16 frozen edit-state outcomes.

Canonical files:

- `depthbenchcad_A_generations.jsonl` — all DepthBenchCAD-A generations.
- `depthbenchcad_B_generations.jsonl` — all DepthBenchCAD-B generations.
- `depthbenchcad_all_generations.jsonl` — combined A+B generation pool.
- `depthbenchcad_A_S1_generations.jsonl` ... `depthbenchcad_A_S5_generations.jsonl` — system-specific A records.
- `depthbenchcad_B_S1_generations.jsonl` ... `depthbenchcad_B_S5_generations.jsonl` — system-specific B records.

The public release includes outcome summaries and reference-task identifiers. Candidate model source text is not included, so `candidate_program_available=false` throughout these manifests. `generation_summary.csv` provides aggregate counts and risks by internal environment ID, split, and system.
