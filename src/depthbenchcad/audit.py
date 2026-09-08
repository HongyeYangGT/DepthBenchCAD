"""Frozen edit-state construction and lightweight automatic rule checks."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any

from .schema import EditState, Template


MASTER_SEED = 20270901


def _state(
    state_id: str,
    edit_type: str,
    parameters: dict[str, float],
    ranges: dict[str, tuple[float, float]],
    relation: dict[str, Any] | None = None,
) -> EditState:
    return EditState(
        state_id=state_id,
        edit_type=edit_type,
        parameters=parameters,
        units={key: "mm" for key in parameters},
        legal_ranges=ranges,
        expected_relations=relation or {},
        tolerance={"length_mm": 0.05, "relative_volume": 0.005, "angle_deg": 0.1},
    )


def freeze_sixteen_states(template: Template) -> tuple[EditState, ...]:
    """Freeze sixteen legal, unique, challenge-oriented interventions.

    Construction is candidate-independent.  Local states are substantial
    single-parameter edits; boundary states approach real engineering
    constraints; linked states require dependency closure; semantic states
    coordinate multiple design variables.  Task constraints are never relaxed
    to make a reference or model pass.
    """
    from .challenge import (
        make_boundary_states,
        make_linked_states,
        make_local_states,
        make_semantic_states,
        normalized_distance,
    )

    base = dict(template.parameters)
    ranges = dict(template.parameter_ranges)
    linked = tuple(str(k) for k in template.constraints.get("linked_parameters", ()) if k in base)
    if len(linked) < 2:
        raise ValueError(f"{template.template_id}: linked edit requires at least two parameters")

    local_rows = make_local_states(template.task_family, base, ranges)
    boundary_rows = make_boundary_states(template.task_family, base, ranges, [row[0] for row in local_rows])
    groups = [
        ("local", local_rows),
        ("boundary", boundary_rows),
        ("linked", make_linked_states(template.task_family, base, ranges, linked)),
        ("semantic", make_semantic_states(
            template.task_family,
            base,
            ranges,
            template.constraints.get("semantic_contract", []),
        )),
    ]

    states: list[EditState] = []
    for edit_type, rows in groups:
        if len(rows) != 4:
            raise RuntimeError(f"{template.template_id}:{edit_type} must contain exactly four states")
        for idx, (parameters, relation) in enumerate(rows, 1):
            changed = list(relation.get("changed_parameters", []))
            if not changed:
                raise RuntimeError(f"{template.template_id}:{edit_type}-{idx} is a no-op")
            if normalized_distance(parameters, base, ranges) < 0.10:
                raise RuntimeError(f"{template.template_id}:{edit_type}-{idx} is below the challenge floor")
            expected = {
                "kind": edit_type,
                "must_respond": True,
                "metric_responses": [{"metric": "geometry_signature", "direction": "change"}],
                **relation,
            }
            states.append(_state(
                f"{template.template_id}-{edit_type}-{idx}",
                edit_type,
                parameters,
                ranges,
                expected,
            ))

    vectors = [tuple((k, s.parameters[k]) for k in sorted(s.parameters)) for s in states]
    if len(set(vectors)) != 16:
        raise RuntimeError(f"{template.template_id}: frozen states must be sixteen unique parameter vectors")
    return tuple(states)


def with_frozen_states(template: Template) -> Template:
    return replace(template, states=freeze_sixteen_states(template))


def sample_frozen_states(
    template: Template, k: int, *, seed: int = MASTER_SEED
) -> tuple[EditState, ...]:
    """Select a deterministic without-replacement audit subset.

    The paper's default design is simple random sampling from the frozen
    finite edit population.  A seeded local RNG makes a manifest replayable
    while keeping the selected states independent of candidate program code.
    """
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= len(template.states):
        raise ValueError(f"k must be an integer in [1, {len(template.states)}]")
    rng = random.Random(f"{seed}:{template.template_id}")
    return tuple(rng.sample(list(template.states), k))


def validate_parameters(state: EditState) -> tuple[bool, str | None]:
    for key, value in state.parameters.items():
        if key in state.legal_ranges:
            lo, hi = state.legal_ranges[key]
            if not lo <= value <= hi:
                return False, f"parameter_out_of_range:{key}"
    return True, None
