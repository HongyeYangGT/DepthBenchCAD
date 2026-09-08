# Analysis protocol

This document freezes the engineering interpretation used by
`scripts/reproduce_tables.py`. The goal is to make every reported analysis a
function of record-level inputs, with calibration/test separation enforced in
code.

## 1. Three evidence levels

For one system, records are indexed as template `T`, independent generation
`I|T`, and frozen edit state `E`. `estimate_variance_components` estimates the
three components from complete calibration records. Formal allocation is chosen
from these calibration components using the superpopulation expression in
Equation (4). Held-out finite-pool error is then evaluated with Equation (5).
The held-out pool never participates in selecting `q`, `g`, or `k`.

## 2. Fixed audit depth and benefit prediction

For every frozen depth `k ∈ {1,4,8,9,10,12,16}`, calibration data select the
best generation count `g`; the budget equation buys the largest feasible
number of templates `q`. Program-level MSE is estimated by within-program
state subsampling. Model-level `J=C0×MSE` is computed from the held-out finite
pool.

The two pre-registered transitions are `4→8` and `8→16`. Predicted
`ΔJ = J_deep - J_shallow` uses calibration components. Observed `ΔJ` uses the
held-out finite pool. Recommendation loss is the held-out `J` of the
calibration-recommended depth minus the smaller held-out `J` of the two choices.

## 3. Pooled, leave-one-system-out, and system calibration

A shared rule is selected by exhaustively searching common `(g,k)` values. For
each candidate pair, every calibration system maps the shared pair through its
own measured cost to obtain `q_s`; the objective is the mean predicted variance
across systems. This directly implements the paper's idea that `g` and `k` are
shared while `q_s` remains system-cost dependent.

Leave-one-system-out repeats the same search after removing the target system's
calibration components. Full system calibration selects `(g,k)` from that
system's calibration records only.

## 4. Edit-type stratification

The four frozen classes are treated as finite strata of size four. Each class
receives at least one audit. The variance contribution is
`Σ_h W_h²(1/k_h - 1/M_h)σ²_Eh/(qg)`, with equal class weights by default.
Integer search jointly chooses `q`, `g`, and each `k_h` under the same cost
budget.

## 5. Oracle regret and robustness

An oracle is an analysis-only held-out search over feasible allocations. It is
never used to choose the reported calibration rule. Relative regret is
`J_selected/J_oracle`; a run is inside the 5% robust region when regret is at
most `1.05`.

Random-split stability performs 40 independent family-stratified splits in
DepthBenchCAD-A, always selecting three templates per family for calibration and
using the remaining six for held-out evaluation. This yields 200
`system × split` outcomes across five systems.

Leave-one-family-out uses seven complete families for calibration and evaluates
on the omitted family. It therefore measures sensitivity to task-family
coverage rather than ordinary random-split noise.

## 6. Cross-environment transfer

The environment-A pooled `(g,k)` rule is frozen using A calibration data and A
formal-pool bounds. The same pair is then mapped through environment-B measured
costs to obtain B-specific `q_s`. A locally recalibrated B pooled rule,
leave-one-system-out B rules, system-level B rules, and the fixed-depth grid are
reported alongside it.

## 7. Expert validation

Expert sampling strata are `system × edit type × automatic label`. Within every
non-empty stratum, the released protocol requests 20 records or the entire
stratum when fewer are available. Reference risks and confusion metrics use
inverse sampling-probability weights `N_h/n_h`. Two independent expert labels
are retained separately, and Cohen's κ is computed before consensus labels are
used for the weighted reference analysis.

## 8. Paired model decisions

Every model pair is aligned on identical template, generation, and state keys.
The calibration quantity is `Z=Y_A-Y_B`. Fixed-depth, paired-system, and
paired-stratified allocations are chosen from calibration `Z` records and
replayed on the held-out paired finite pool. Correct-decision and tie rates are
reported separately for budgets 512, 1024, and 2048.

## 9. Interval coverage

The interval experiment freezes `q=16`, `g=3`, `k=8`. Each replay samples all
three levels without replacement. The three-level interval estimates all three
variance components and uses a `q-1` t critical value. The comparison interval
treats generation programs as independent outer units and uses the corresponding
program-level variance and degrees of freedom. Both intervals cover the same
full finite-pool mean risk.

## 10. Released record pool

The canonical analysis inputs are `data/records/depthbenchcad_A_audits.jsonl`, `data/records/depthbenchcad_B_audits.jsonl`, and `data/records/depthbenchcad_A_expert_annotations.jsonl`. The task manifest, frozen edit states, legality ranges, judge contract, and cost model are shared by both the released records and fresh model runs.

`data/paper_results.json` stores the manuscript values. `scripts/reproduce_tables.py` recomputes the complete analysis from record-level inputs, while `scripts/validate_paper_results.py` checks the main numerical and mechanism-level invariants with the frozen tolerances used by the release.
