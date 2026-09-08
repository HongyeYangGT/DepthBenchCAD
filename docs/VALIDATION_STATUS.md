# Validation status

This release freezes the complete DepthBenchCAD task corpus derived from the BenchCAD source tasks and the record-level analysis pipeline used by the paper.

## Verified in this package

- 120 CAD templates across 14 task families.
- 1,920 frozen counterfactual edit states (16 per template).
- 2,760 released generation records: 1,800 in DepthBenchCAD-A and 960 in DepthBenchCAD-B.
- 44,160 released state-level audit records: 28,800 in DepthBenchCAD-A and 15,360 in DepthBenchCAD-B.
- 800 doubly annotated expert-validation items.
- Calibration/test splits of 24/48 templates in DepthBenchCAD-A and 12/36 templates in DepthBenchCAD-B.
- Strict automatic judge with topology, circular/hole, dimensional, containment, symmetry, spacing, and semantic checks plus gray-zone review routing.
- No-op and duplicate edit-state guards.
- Three-level variance estimation, finite-population correction, fixed-depth comparison, cost-aware allocation, transfer, stability, expert-validation, paired-decision, and interval-coverage analyses.
- Generation records link one-to-one to the 16 frozen state outcomes for each system/template/generation identity.
- Reference programs remain executable under the declared CadQuery/OCCT environment.

## Public-data boundary

The public release contains benchmark tasks, reference programs, generation identities, audited outcomes, expert labels, and analysis code. Provider-side candidate source text, prompts, token usage, raw latency logs, and decoding metadata are not included. Validation therefore covers the released benchmark and outcome records, while external provider transcripts are outside the package.
