"""Evaluation metrics and cluster-aware confidence intervals."""

from __future__ import annotations

import random
from math import sqrt
from statistics import mean
from typing import Iterable

from .schema import AuditRecord
from .variance import _sample_variance, finite_population_variance


def risk(records: Iterable[AuditRecord]) -> float:
    values = [int(r.failed) for r in records if r.failed is not None]
    if not values:
        raise ValueError("empty records")
    return mean(values)


def group_risk(records: Iterable[AuditRecord]) -> dict[tuple[str, int], float]:
    groups: dict[tuple[str, int], list[int]] = {}
    for r in records:
        if r.failed is None:
            continue
        groups.setdefault((r.template_id, r.generation_id), []).append(int(r.failed))
    return {key: mean(values) for key, values in groups.items()}


def program_mse_against_full(records: Iterable[AuditRecord], k: int, seed: int = 20270901, repeats: int = 2000) -> float:
    """Monte Carlo MSE for state subsampling without replacement."""
    groups: dict[tuple[str, int], list[AuditRecord]] = {}
    for r in records:
        if r.failed is None:
            continue
        groups.setdefault((r.template_id, r.generation_id), []).append(r)
    if any(len(v) < k for v in groups.values()):
        raise ValueError("k exceeds a program's available state count")
    rng = random.Random(seed)
    errors: list[float] = []
    for group in groups.values():
        target = mean(int(r.failed) for r in group)
        for _ in range(repeats):
            sample = rng.sample(group, k)
            errors.append((mean(int(r.failed) for r in sample) - target) ** 2)
    return mean(errors)


def cluster_mean_variance(records: Iterable[AuditRecord]) -> tuple[float, int]:
    """Variance of template-cluster means with q-1 denominator."""
    by_template: dict[str, list[int]] = {}
    for r in records:
        if r.failed is None:
            continue
        by_template.setdefault(r.template_id, []).append(int(r.failed))
    means = [mean(values) for values in by_template.values()]
    if not means:
        raise ValueError("no observed records")
    return _sample_variance(means) / len(means), len(means)


def t_critical_95(df: int) -> float:
    # Accurate enough for benchmark reports without a scipy dependency.
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}
    if df in table:
        return table[df]
    if df <= 0:
        raise ValueError("degrees of freedom must be positive")
    return 1.96 + 0.5 / df


def cluster_confidence_interval(records: Iterable[AuditRecord], level: float = 0.95) -> tuple[float, float]:
    values = list(records)
    point = risk(values)
    variance, q = cluster_mean_variance(values)
    if q < 2:
        return point, point
    critical = t_critical_95(q - 1)
    half_width = critical * sqrt(max(0.0, variance))
    return max(0.0, point - half_width), min(1.0, point + half_width)
