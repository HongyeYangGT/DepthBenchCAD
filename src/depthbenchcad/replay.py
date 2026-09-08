"""Finite-reference-pool replay utilities for observed complete audit data.

The paper's replay experiments resample only real, frozen audit records.  This
module enforces that discipline: a pool is built from a balanced complete audit
set and every draw selects templates, generations, and states without
replacement.  It never synthesizes outcomes, timings, or missing records.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .schema import AuditRecord
from .variance import estimate_finite_variance_components, finite_population_variance


DEFAULT_REPLAY_SEED = 20270901


@dataclass(frozen=True)
class FinitePoolShape:
    templates: int
    generations_per_template: int
    states_per_program: int


@dataclass(frozen=True)
class ReplayDraw:
    estimate: float
    template_ids: tuple[str, ...]
    generation_keys: tuple[tuple[str, int], ...]
    state_keys: tuple[tuple[str, int, str], ...]


@dataclass(frozen=True)
class ReplayResult:
    target_risk: float
    estimates: tuple[float, ...]
    mse: float


class FiniteAuditPool:
    """A balanced, complete finite audit reference pool for one system."""

    def __init__(self, records: Iterable[AuditRecord]):
        observations = tuple(records)
        if not observations:
            raise ValueError("a finite replay pool cannot be empty")
        systems = {record.system_id for record in observations}
        if len(systems) != 1:
            raise ValueError("a finite replay pool represents one system at a time")

        by_template: dict[str, dict[int, tuple[AuditRecord, ...]]] = {}
        mutable: dict[str, dict[int, list[AuditRecord]]] = {}
        seen: set[tuple[str, int, str]] = set()
        for record in observations:
            if record.failed is None:
                raise ValueError("finite replay requires observed failed labels")
            key = (record.template_id, record.generation_id, record.state_id)
            if key in seen:
                raise ValueError(f"duplicate audit state in finite pool: {key}")
            seen.add(key)
            mutable.setdefault(record.template_id, {}).setdefault(record.generation_id, []).append(record)
        for template_id, generations in mutable.items():
            by_template[template_id] = {}
            for generation_id, states in generations.items():
                by_template[template_id][generation_id] = tuple(states)

        generation_counts = {len(generations) for generations in by_template.values()}
        state_counts = {
            len(states)
            for generations in by_template.values()
            for states in generations.values()
        }
        if len(generation_counts) != 1 or len(state_counts) != 1:
            raise ValueError("finite replay requires a balanced complete template/generation/state pool")
        self._records = observations
        self._by_template = by_template
        self.system_id = next(iter(systems))
        self.shape = FinitePoolShape(
            templates=len(by_template),
            generations_per_template=next(iter(generation_counts)),
            states_per_program=next(iter(state_counts)),
        )

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return self._records

    @property
    def target_risk(self) -> float:
        return mean(float(record.failed) for record in self._records)

    def _validate_sample_sizes(self, q: int, g: int, k: int) -> None:
        for value, name, upper in (
            (q, "q", self.shape.templates),
            (g, "g", self.shape.generations_per_template),
            (k, "k", self.shape.states_per_program),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
            if value > upper:
                raise ValueError(f"{name} exceeds the finite reference-pool size")

    def draw(self, q: int, g: int, k: int, *, seed: int = DEFAULT_REPLAY_SEED) -> ReplayDraw:
        """Draw one nested SRSWOR replay sample using a deterministic seed."""
        rng = random.Random(seed)
        return self.draw_with_rng(q, g, k, rng)

    def draw_with_rng(self, q: int, g: int, k: int, rng: random.Random) -> ReplayDraw:
        """Draw one replay sample from a caller-owned random generator."""
        self._validate_sample_sizes(q, g, k)
        template_ids = tuple(rng.sample(sorted(self._by_template), q))
        selected_records: list[AuditRecord] = []
        generation_keys: list[tuple[str, int]] = []
        state_keys: list[tuple[str, int, str]] = []
        for template_id in template_ids:
            generations = self._by_template[template_id]
            generation_ids = rng.sample(sorted(generations), g)
            for generation_id in generation_ids:
                generation_keys.append((template_id, generation_id))
                selected_states = rng.sample(list(generations[generation_id]), k)
                selected_records.extend(selected_states)
                state_keys.extend((template_id, generation_id, record.state_id) for record in selected_states)
        return ReplayDraw(
            estimate=mean(float(record.failed) for record in selected_records),
            template_ids=template_ids,
            generation_keys=tuple(generation_keys),
            state_keys=tuple(state_keys),
        )

    def replay(
        self,
        q: int,
        g: int,
        k: int,
        *,
        repeats: int = 2000,
        seed: int = DEFAULT_REPLAY_SEED,
    ) -> ReplayResult:
        """Replay nested finite-pool samples and report empirical model-level MSE."""
        if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
            raise ValueError("repeats must be a positive integer")
        self._validate_sample_sizes(q, g, k)
        rng = random.Random(seed)
        estimates = tuple(self.draw_with_rng(q, g, k, rng).estimate for _ in range(repeats))
        target = self.target_risk
        return ReplayResult(
            target_risk=target,
            estimates=estimates,
            mse=mean((estimate - target) ** 2 for estimate in estimates),
        )

    def program_mse(
        self,
        k: int,
        *,
        repeats: int = 2000,
        seed: int = DEFAULT_REPLAY_SEED,
    ) -> float:
        """Replay the paper's per-program state-subsampling MSE without replacement."""
        if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
            raise ValueError("repeats must be a positive integer")
        self._validate_sample_sizes(1, 1, k)
        rng = random.Random(seed)
        errors: list[float] = []
        for generations in self._by_template.values():
            for states in generations.values():
                target = mean(float(record.failed) for record in states)
                for _ in range(repeats):
                    estimate = mean(float(record.failed) for record in rng.sample(list(states), k))
                    errors.append((estimate - target) ** 2)
        return mean(errors)

    def design_variance(self, q: int, g: int, k: int) -> float:
        """Evaluate Equation (5) for this finite reference pool.

        This is a reference-pool quantity for replay validation, not a future
        task-distribution confidence interval.
        """
        self._validate_sample_sizes(q, g, k)
        components = estimate_finite_variance_components(self._records)
        return finite_population_variance(
            components,
            q,
            g,
            k,
            self.shape.states_per_program,
            self.shape.templates,
            self.shape.generations_per_template,
        )


def finite_pool_replay(
    records: Iterable[AuditRecord],
    q: int,
    g: int,
    k: int,
    *,
    repeats: int = 2000,
    seed: int = DEFAULT_REPLAY_SEED,
) -> ReplayResult:
    """Convenience wrapper for a replay over one observed finite audit pool."""
    return FiniteAuditPool(records).replay(q, g, k, repeats=repeats, seed=seed)
