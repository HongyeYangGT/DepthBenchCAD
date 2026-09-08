"""Higher-level protocols from Sections 3.5 and 4.4-4.6.

The functions here operate on observed records and never create labels or CAD
programs. They are useful for reproducing allocation tables after the original
model outputs have been restored.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean
from typing import Iterable, Mapping

from .allocation import Allocation, allocation_cost, optimize_allocation
from .schema import AuditRecord, EDIT_TYPES
from .variance import VarianceComponents, _sample_variance


def trimmed_mean(values: Iterable[float], trim_fraction: float = 0.10) -> float:
    """Two-sided trimmed mean used for wall-clock cost estimates."""
    items = sorted(float(v) for v in values)
    if not items:
        raise ValueError("cannot estimate a cost from no timings")
    if not 0 <= trim_fraction < 0.5:
        raise ValueError("trim_fraction must be in [0, 0.5)")
    cut = int(len(items) * trim_fraction)
    core = items[cut: len(items) - cut or None]
    return mean(core)


def cost_summary(values: Iterable[float]) -> dict[str, float]:
    items = [float(v) for v in values]
    if not items:
        raise ValueError("no timings")
    return {
        "trimmed_mean_10pct": trimmed_mean(items),
        "mean": mean(items),
        "median": sorted(items)[len(items) // 2],
        "n": float(len(items)),
    }


def fixed_depth(
    components: VarianceComponents,
    k: int,
    budget: float,
    c_template: float,
    c_generation: float,
    c_edit: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
) -> Allocation:
    """Paper baseline: fix k, optimize g, then use the largest feasible q."""
    if k < 1 or k > max_states:
        raise ValueError("k is outside the finite state population")
    best: Allocation | None = None
    for g in range(1, max_generations + 1):
        per_template = c_template + g * (c_generation + k * c_edit)
        q = min(max_templates, int(budget // per_template))
        if q < 1:
            continue
        from .variance import finite_population_variance
        candidate = Allocation(
            q=q,
            g=g,
            k=k,
            cost=allocation_cost(q, g, k, c_template, c_generation, c_edit),
            variance=finite_population_variance(components, q, g, k, max_states, max_templates, max_generations),
        )
        if best is None or (candidate.variance, -candidate.q) < (best.variance, -best.q):
            best = candidate
    if best is None:
        raise ValueError("budget does not buy one template at this audit depth")
    return best


def aggregate_components(values: Iterable[VarianceComponents]) -> VarianceComponents:
    """Cross-system variance component summary used by the deployable rule."""
    items = list(values)
    if not items:
        raise ValueError("at least one calibration system is required")
    return VarianceComponents(
        mean(v.template for v in items),
        mean(v.generation for v in items),
        mean(v.edit for v in items),
    )


def leave_one_out_components(
    all_components: Mapping[str, VarianceComponents], held_out: str
) -> VarianceComponents:
    remaining = [v for key, v in all_components.items() if key != held_out]
    return aggregate_components(remaining)


def shrink_components(
    pilot: VarianceComponents, global_components: VarianceComponents, weight: float
) -> VarianceComponents:
    """Shrink small-pilot estimates toward the frozen cross-system estimate."""
    if not 0 <= weight <= 1:
        raise ValueError("weight must be in [0, 1]")
    return VarianceComponents(
        weight * pilot.template + (1 - weight) * global_components.template,
        weight * pilot.generation + (1 - weight) * global_components.generation,
        weight * pilot.edit + (1 - weight) * global_components.edit,
    )


def stratified_state_indices(records: Iterable[AuditRecord], k: int, seed: int = 20270901) -> dict[tuple[str, int], list[int]]:
    """Select k states while retaining all four edit classes when possible."""
    by_program: dict[tuple[str, int], list[AuditRecord]] = {}
    for record in records:
        by_program.setdefault((record.template_id, record.generation_id), []).append(record)
    if any(len(v) < k for v in by_program.values()):
        raise ValueError("k exceeds available states")
    rng = random.Random(seed)
    selected: dict[tuple[str, int], list[int]] = {}
    for key, group in by_program.items():
        by_type = {kind: [i for i, item in enumerate(group) if item.edit_type == kind] for kind in EDIT_TYPES}
        chosen: list[int] = []
        for kind in EDIT_TYPES:
            if by_type[kind] and len(chosen) < k:
                chosen.append(rng.choice(by_type[kind]))
        remaining = [i for i in range(len(group)) if i not in chosen]
        chosen.extend(rng.sample(remaining, k - len(chosen)))
        selected[key] = chosen
    return selected


def cluster_bootstrap(records: Iterable[AuditRecord], repeats: int = 2000, seed: int = 20270901) -> list[float]:
    """Template-cluster bootstrap distribution of the mean risk."""
    items = list(records)
    clusters: dict[str, list[int]] = {}
    for record in items:
        clusters.setdefault(record.template_id, []).append(int(record.failed))
    if not clusters:
        raise ValueError("empty audit pool")
    rng = random.Random(seed)
    names = list(clusters)
    return [mean(mean(clusters[rng.choice(names)]) for _ in names) for _ in range(repeats)]


def paired_difference(records_a: Iterable[AuditRecord], records_b: Iterable[AuditRecord]) -> list[float]:
    """Matched A-B state differences for shared template/generation/state keys."""
    left = {(r.template_id, r.generation_id, r.state_id): int(r.failed) for r in records_a}
    right = {(r.template_id, r.generation_id, r.state_id): int(r.failed) for r in records_b}
    keys = sorted(left.keys() & right.keys())
    if not keys:
        raise ValueError("paired pools have no shared keys")
    return [left[key] - right[key] for key in keys]


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values for the ten-pair comparison."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    n = len(ordered)
    for rank, (key, value) in enumerate(ordered):
        adjusted_value = min(1.0, (n - rank) * value)
        running = max(running, adjusted_value)
        adjusted[key] = running
    return adjusted


@dataclass(frozen=True)
class WeightedConfusion:
    precision: float
    recall: float
    specificity: float
    accuracy: float


def inverse_probability_confusion(
    automatic: Iterable[bool], expert: Iterable[bool], inclusion_probabilities: Iterable[float]
) -> WeightedConfusion:
    """IPW precision/recall/specificity/accuracy for expert validation."""
    rows = list(zip(automatic, expert, inclusion_probabilities))
    if not rows or any(p <= 0 for _, _, p in rows):
        raise ValueError("labels and positive inclusion probabilities are required")
    weights = [1 / p for _, _, p in rows]
    tp = sum(w for (a, e, _), w in zip(rows, weights) if a and e)
    fp = sum(w for (a, e, _), w in zip(rows, weights) if a and not e)
    fn = sum(w for (a, e, _), w in zip(rows, weights) if not a and e)
    tn = sum(w for (a, e, _), w in zip(rows, weights) if not a and not e)
    return WeightedConfusion(
        precision=tp / (tp + fp) if tp + fp else 0.0,
        recall=tp / (tp + fn) if tp + fn else 0.0,
        specificity=tn / (tn + fp) if tn + fp else 0.0,
        accuracy=(tp + tn) / (tp + tn + fp + fn),
    )
