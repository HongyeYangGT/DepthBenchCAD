"""Integer budget search described in Section 3.4."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable

from .variance import VarianceComponents, finite_population_variance


@dataclass(frozen=True)
class Allocation:
    q: int
    g: int
    k: int
    cost: float
    variance: float


def allocation_cost(q: int, g: int, k: int, c_template: float, c_generation: float, c_edit: float) -> float:
    for value, name in ((q, "q"), (g, "g"), (k, "k")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    for value, name in ((c_template, "c_template"), (c_generation, "c_generation"), (c_edit, "c_edit")):
        if not isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"{name} must be finite and non-negative")
    return q * c_template + q * g * (c_generation + k * c_edit)


def optimize_allocation(
    variance: VarianceComponents,
    budget: float,
    c_template: float,
    c_generation: float,
    c_edit: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    reference_templates: int | None = None,
    reference_generations: int | None = None,
    objective: Callable[[VarianceComponents, int, int, int, int, int], float] | None = None,
) -> Allocation:
    """Search feasible natural-number triples and return the minimum variance."""
    for value, name in ((max_templates, "max_templates"), (max_generations, "max_generations"), (max_states, "max_states")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if reference_templates is not None and (not isinstance(reference_templates, int) or isinstance(reference_templates, bool) or reference_templates < 1):
        raise ValueError("reference_templates must be a positive integer")
    if reference_generations is not None and (not isinstance(reference_generations, int) or isinstance(reference_generations, bool) or reference_generations < 1):
        raise ValueError("reference_generations must be a positive integer")
    Q = max_templates if reference_templates is None else reference_templates
    G = max_generations if reference_generations is None else reference_generations
    if Q < max_templates or G < max_generations:
        raise ValueError("reference pool must cover the search bounds")
    budget = float(budget)
    if not isfinite(budget) or budget < 0:
        raise ValueError("budget must be finite and non-negative")
    for value, name in ((c_template, "c_template"), (c_generation, "c_generation"), (c_edit, "c_edit")):
        if not isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"{name} must be finite and non-negative")
    objective = objective or finite_population_variance
    best: Allocation | None = None
    for g in range(1, max_generations + 1):
        for k in range(1, max_states + 1):
            per_template = c_template + g * (c_generation + k * c_edit)
            if per_template <= 0:
                raise ValueError("costs must not all be zero")
            q = min(max_templates, int(budget // per_template))
            if q < 1:
                continue
            cost = allocation_cost(q, g, k, c_template, c_generation, c_edit)
            score = objective(variance, q, g, k, max_states, Q, G)
            candidate = Allocation(q=q, g=g, k=k, cost=cost, variance=score)
            if best is None or (candidate.variance, -candidate.q, candidate.cost) < (best.variance, -best.q, best.cost):
                best = candidate
    if best is None:
        raise ValueError("budget does not buy one template, one generation and one state")
    return best
