# DepthBenchCAD

[简体中文](README_zh-CN.md) | [English](README.md)


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
