# Automatic Judge: Section 4.2 Implementation

This module is the executable implementation of the automatic judge described in Section 4.2 of the paper. Candidate source code is never inspected. The judge consumes only the frozen task/state specification and geometry probes produced by the isolated CadQuery worker.

## Ordered decision path

1. Build completes within the edit timeout.
2. The output is valid, has positive volume, and satisfies the prescribed connected-component rule.
3. Topology rules are checked, including face/edge lower bounds and task-specific circular/hole features.
4. The edited parameter must produce the specified geometric response. Scale edits use direction and minimum magnitude; positional/relational linked edits use structural geometry change.
5. Dimensions, spacing, symmetry, and containment are checked from bounding boxes, circular-feature centers/radii, and mass-center probes.
6. The task-family semantic contract is evaluated with explicit geometry relations (for example concentric bores, symmetric hole patterns, hollow shells, connected webs, evenly centered arrays, and hinge pin/knuckle relations).

The first failing stage is retained as `failure_stage`. Full check traces are stored in `metadata.judge_checks`.

## Tolerances and gray zone

The paper-specified tolerances are used directly:

- length: `max(0.05 mm, 0.001 * Lref)`;
- angle: `0.1 deg`;
- relative volume: `0.5%`;
- topology counts and connected components: exact.

The paper states that tolerance-borderline cases receive manual review but does not specify a numerical gray-band width. The implementation freezes that missing implementation detail as `0.90T..1.10T` around threshold `T`. A gray-zone row is emitted with `failed=null`, `automatic_label=false`, and `metadata.review_required=true`. Risk analysis stops until those rows have manual labels.

Manual labels can be applied with `scripts/apply_review_labels.py`.

## Nominal-state rule

A successful Python/CadQuery build is not sufficient for initial validity. The nominal shape is passed through the same entity, topology, dimensional, and semantic checks. If it fails a nominal contract, the program is initially invalid and all sixteen counterfactual states count as failures in the primary analysis, matching Section 4.2.

## Reference-program requirements enforced by the judge

Completing the judge exposed inconsistencies in the released reference corpus. The corresponding reference-only implementation contracts were repaired without changing the paper's statistical protocol: several placeholder topology minima were corrected, tangential unions were changed to real overlaps where they produced invalid/multi-solid reference shapes, `drawer_handle.span` now controls geometry, its legal range is conditioned on mount geometry, bearing-housing nominal geometry is feasible, and linked positional edits use structural response rather than an artificial volume-direction requirement.
