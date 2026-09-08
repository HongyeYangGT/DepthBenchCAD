# DepthBenchCAD

**DepthBenchCAD: When Does More Auditing Yield More Reliable Conclusions?**

This repository is the executable release of **DepthBenchCAD**, the three-level counterfactual audit benchmark introduced in the paper *DepthBenchCAD: When Does More Auditing Yield More Reliable Conclusions?* DepthBenchCAD studies how evaluation evidence should be allocated across task templates, independent model generations, and within-program counterfactual edit states under a fixed evaluation budget.

DepthBenchCAD is constructed from the BenchCAD task corpus. The released benchmark contains two disjoint evaluation environments: **DepthBenchCAD-A** contains 72 templates from eight task families (24 calibration, 48 test), and **DepthBenchCAD-B** contains 48 templates from six non-overlapping task families (12 calibration, 36 test). Every template includes a standalone CadQuery reference program, legal parameter ranges, task constraints, and 16 frozen edit states: four local, four boundary, four linked, and four semantic.

The release contains 2,760 generation-level records and 44,160 state-level audit records, plus 800 doubly annotated expert-validation items. The public package contains the identifiers and outcome fields required for benchmark analysis. Provider-side prompts, candidate source text, token usage, raw latency logs, and decoding metadata are not included.

## Benchmark structure

| Environment | Templates | Task families | Calibration / test | Generations per template | States per program | Systems | Audit records |
|---|---:|---:|---:|---:|---:|---:|---:|
| DepthBenchCAD-A | 72 | 8 | 24 / 48 | 5 | 16 | 5 | 28,800 |
| DepthBenchCAD-B | 48 | 6 | 12 / 36 | 4 | 16 | 5 | 15,360 |

The implementation retains the short internal environment IDs `A` and `B` in record fields for compactness; they map exactly to DepthBenchCAD-A and DepthBenchCAD-B.

## Quick start

Python 3.10+ is required. The CAD worker is designed for CadQuery 2.5.x / OCCT 7.8.x.

```powershell
python -m pip install -r requirements.txt
python scripts/validate_release.py
pytest -q
```

Materialize or validate the DepthBenchCAD task corpus:

```powershell
python scripts/prepare_depthbenchcad_tasks.py
```

Audit a new model generation manifest against the frozen states:

```powershell
python scripts/run_audit.py `
  --templates data/templates/depthbenchcad_tasks.json `
  --generations data/runs/generations.jsonl `
  --output data/runs/audits.jsonl

python scripts/analyze_records.py data/runs/audits.jsonl --out data/runs/report.json
```

Each submitted generation row identifies a system, template, and generation and supplies either candidate source text or a path to a CadQuery program. The worker executes the nominal program and all requested frozen edit states, then records build status, geometry probes, judge stage, and audit outcome. An initially invalid program contributes failures for all 16 states in the primary risk estimate, following the paper protocol.

## Released data

### Task definitions

`data/templates/depthbenchcad_tasks.json` contains the 120 DepthBenchCAD task definitions and all 1,920 frozen edit states. `data/programs/` contains the corresponding reference CadQuery programs. The task source is BenchCAD; DepthBenchCAD adds the frozen environment split, counterfactual state population, execution/judging contract, cost protocol, and audit-record hierarchy used in the paper.

### Generation records

`data/generations/` contains 1,800 DepthBenchCAD-A generations and 960 DepthBenchCAD-B generations. Each row links a system/template/generation identity to its 16 audited states and records the aggregate failure count and edit-type breakdown.

The public generation manifests intentionally omit candidate source code; therefore `candidate_program_available=false` in these released records. This does not affect the record-level statistical analyses, which operate on the audited outcomes.

### Audit records

- `data/records/depthbenchcad_A_audits.jsonl`: 28,800 DepthBenchCAD-A audit outcomes.
- `data/records/depthbenchcad_B_audits.jsonl`: 15,360 DepthBenchCAD-B audit outcomes.
- `data/records/depthbenchcad_A_expert_annotations.jsonl`: 800 expert-validation items sampled from DepthBenchCAD-A.

These files are the canonical inputs for the paper-analysis pipeline.

## Reproduce the paper analysis

```powershell
python scripts/reproduce_tables.py `
  --records-a data/records/depthbenchcad_A_audits.jsonl `
  --records-b data/records/depthbenchcad_B_audits.jsonl `
  --expert data/records/depthbenchcad_A_expert_annotations.jsonl `
  --out-dir results/reproduced

python scripts/validate_paper_results.py --results results/reproduced
```

The analysis recomputes:

- three-level variance components and finite-population design error;
- fixed-depth comparisons over the frozen audit-depth grid;
- `k=4→8` and `k=8→16` benefit-direction prediction;
- pooled, leave-one-system-out, full-system, and edit-stratified allocation;
- shared/system oracle regret and 5% robust coverage;
- repeated family-stratified splits and leave-one-family-out transfer;
- DepthBenchCAD-A to DepthBenchCAD-B transfer;
- inverse-probability expert validation and Cohen's κ;
- paired model-decision replay at budgets 512/1024/2048;
- three-level versus program-independent 95% interval coverage.

`results/reproduced/` contains a lightweight validation snapshot produced with `--replay-scale 0.02`. Running without that flag uses the full frozen replay protocol (`1.0`). `data/paper_results.json` is the machine-readable transcription of the numerical results reported in the manuscript.

## Evaluation protocol

`configs/paper_protocol.json` records the DepthBenchCAD protocol: master seed `20270901`, budgets `512/1024/2048`, template/edit costs, system-specific generation costs, timeouts, retry policy, environment splits, fixed audit depths, transition comparisons, interval experiment, and expert-validation sampling design.

The automatic judge follows the Section 4.2 order:

1. build completion;
2. valid entities and connected components;
3. topology and circular/hole features;
4. edited-parameter response;
5. dimensions, spacing, symmetry, and containment;
6. high-level semantic contract.

Length tolerance is `max(0.05 mm, 0.001*Lref)`, angle tolerance is `0.1 deg`, and relative-volume tolerance is `0.5%`. Exact topology counts receive no floating-point tolerance. Numerical cases inside the configured gray band are routed to manual review rather than silently assigned a label.

Apply manual review labels with:

```powershell
python scripts/apply_review_labels.py `
  --audits data/runs/audits.jsonl `
  --reviews data/runs/reviews.jsonl `
  --output data/runs/audits_resolved.jsonl
```

## Repository map

- `src/depthbenchcad/catalog.py` — DepthBenchCAD task catalog derived from the BenchCAD source corpus.
- `src/depthbenchcad/audit.py` — frozen edit-state construction.
- `src/depthbenchcad/executor.py` — isolated CadQuery execution and geometry probes.
- `src/depthbenchcad/judge.py` — ordered automatic judge and gray-zone routing.
- `src/depthbenchcad/variance.py` — three-level variance equations and finite-population correction.
- `src/depthbenchcad/allocation.py` — exhaustive feasible `(q, g, k)` search.
- `src/depthbenchcad/replay.py` — nested finite-pool replay and program-level MSE.
- `src/depthbenchcad/strategies.py` — pooled, leave-one-system-out, system, stratified, and paired allocation primitives.
- `src/depthbenchcad/paper_analysis.py` — Sections 4.3–5.3 analysis layer.
- `examples/` — minimal one-generation execution example.
- `scripts/run_audit.py` — execute new candidate programs against the frozen benchmark.
- `scripts/reproduce_tables.py` — reproduce the paper analysis from released records.
- `scripts/validate_release.py` — validate corpus and record cardinalities/linkage.
- `scripts/validate_paper_results.py` — validate the reproduced paper-level invariants.
- `docs/` — judge, protocol, analysis, and validation documentation.

## Validation

Run the complete release checks from the repository root:

```powershell
$env:PYTHONPATH = "src"
pytest -q
python -m compileall -q src tests scripts data/programs
python scripts/validate_release.py
python scripts/validate_paper_results.py --results results/reproduced
```

The validation suite checks task cardinalities, state composition, generation-to-state linkage, expert sample size, allocation feasibility, finite-pool sampling, clustered intervals, stratification, paired comparisons, benefit prediction, regret summaries, and expert agreement.

## Public-data boundary

The repository releases the DepthBenchCAD tasks, reference programs, generation identities, state-level outcomes, expert-validation labels, judge, and complete analysis code. Provider-side candidate source text and provider telemetry are outside the public package. Accordingly, the release supports end-to-end verification of the benchmark and reported statistical analysis from the published outcome records, while it does not independently authenticate external provider transcripts that are not included here.

## License

Code and repository materials are released under the MIT License. See `LICENSE`.
