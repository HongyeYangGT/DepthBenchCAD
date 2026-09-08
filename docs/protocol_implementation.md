# Protocol Implementation Record

## Implementation Boundary

This repository treats the paper as the normative behavioral specification.
Quantities and procedures stated in the paper are implemented directly. Runtime
details required by the protocol but not numerically enumerated in the paper are
frozen here as explicit executable contracts.

The 120 released task definitions are the original BenchCAD tasks used in the
study. The repository adds the frozen edit-state population, split metadata,
judge contract, and statistical tooling needed to execute the published
benchmark protocol.

## Paper-to-Code Map

The model-level estimand is the failure probability for a randomly chosen task
template, independent generation, and one state from a finite frozen edit
population. `variance.superpopulation_variance` implements Equation (4), and
`variance.finite_population_variance` implements Equation (5).
`allocation.optimize_allocation` and `paper_analysis.choose_component_rule`
implement exhaustive integer budget allocation.

`catalog.py` packages the DepthBenchCAD task catalog derived from the BenchCAD source corpus. DepthBenchCAD-A
contains eight mechanical task families with nine variants each; DepthBenchCAD-B
contains six disjoint families with eight variants each. Calibration/test
membership is assigned deterministically within each family by the frozen split
function in `challenge.py`: three of nine variants per A family and two of eight
variants per B family enter calibration. The assignment is intentionally not a
simple variant-number prefix. Remaining variants form the 48- and 36-template
test pools.

Every task includes:

- an executable `build(params)` CadQuery reference program;
- a nominal full parameter vector and legal ranges;
- topology and semantic task constraints;
- exactly 16 complete parameter states, evenly divided among local, boundary,
  linked, and semantic edits;
- the paper's length, angle, and relative-volume tolerances.

The state constructor reads only the task specification. It never inspects a
candidate model program. Every state contains the full parameter vector, so its
execution is independent of mutable worker state.

## Execution Contract

Candidate programs define `build(params)` and return a CadQuery workplane or
shape. The runner first executes the nominal state in a fresh subprocess, then
executes each selected frozen state in another subprocess. It records volume,
surface area, solid/face/edge/vertex counts, bounding-box dimensions, center of
mass, circular-edge centers/radii, shape validity, a geometry signature,
wall-clock time, process diagnostics, and the exact failure stage.

`judge.py` implements the paper's Section 4.2 order. Numerical comparisons use
the paper's length, angle, and relative-volume tolerances. The PDF does not
specify the exact width of the tolerance gray zone, so the public executable
contract freezes a `0.90T..1.10T` band around threshold `T` and routes those
rows to manual review. Analysis refuses unresolved review rows.

Programs that fail initial build or nominal constraints contribute failures for
all frozen states, while conditional edit risk can be calculated from initially
valid programs.

## Statistical Protocol

`paper_analysis.py` completes the analysis layer above the primitive variance
and strategy modules. The one-command pipeline covers fixed depth, benefit
prediction, pooled and leave-one-system-out allocation, full system calibration,
edit-type stratification, oracle regret, random split and leave-one-family-out
stability, cross-environment transfer, expert validation, paired decisions, and
confidence-interval coverage. Exact contracts are frozen in
`docs/analysis_protocol.md`.

All finite-pool replays sample templates, generations within templates, and
states within programs without replacement using master seed `20270901` unless
a caller explicitly supplies another seed. Calibration/test membership is
attached to templates and never split at the generation or state level.

## Released data

`data/templates/depthbenchcad_tasks.json` is the task manifest used by the benchmark. `data/paper_results.json` stores the manuscript values as the numerical reference. `data/records/*.jsonl` contains the canonical state-level outcome records used by the analysis, and `data/generations/*.jsonl` contains the corresponding generation-level summaries. Provider-side candidate source text and telemetry are not part of the public package.
