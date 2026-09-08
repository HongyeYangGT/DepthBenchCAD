# Released data

The repository exposes one canonical experimental data path.

## Generations

`data/generations/` contains 2,760 generation-level records. DepthBenchCAD-A contributes 1,800 records (72 templates × 5 systems × 5 generations); DepthBenchCAD-B contributes 960 records (48 templates × 5 systems × 4 generations). Each generation summarizes exactly 16 frozen audit states.

Candidate model source text is not included in the public package. Generation manifests therefore retain identifiers and outcome summaries while setting `candidate_program_available=false`.

## Audit outcomes

`data/records/depthbenchcad_A_audits.jsonl` and `data/records/depthbenchcad_B_audits.jsonl` contain the 44,160 state-level outcomes used by the analysis pipeline. Keys are unique over `(system_id, template_id, generation_id, state_id)`.

## Expert validation

`data/records/depthbenchcad_A_expert_annotations.jsonl` contains 800 doubly annotated items used for the expert-reference analysis.

## Paper results

`data/paper_results.json` contains a machine-readable transcription of the manuscript tables. `scripts/reproduce_tables.py` recomputes the analysis from the released records, and `scripts/validate_paper_results.py` checks the paper-level invariants.
