"""End-to-end analyses corresponding to Sections 4.3--5.3 of the paper.

The functions in this module consume complete observed audit pools.  They never
manufacture missing outcomes. They operate directly on released audit records or fresh audit outputs.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import combinations, product
from statistics import mean, median
from typing import Iterable, Mapping, Sequence

from .allocation import Allocation
from .metrics import risk, t_critical_95
from .schema import AuditRecord, EDIT_TYPES
from .strategies import (
    CostModel,
    StratifiedAllocation,
    StratifiedVarianceComponents,
    allocation_for_rule,
    estimate_stratified_variance_components,
    optimize_stratified_allocation,
    paired_cost_model,
    paired_observations,
    paired_variance_components,
    select_pilot_shrinkage_weight,
)
from .variance import (
    VarianceComponents,
    estimate_finite_variance_components,
    estimate_variance_components,
    finite_population_variance,
    superpopulation_variance,
)


@dataclass(frozen=True)
class PoolShape:
    templates: int
    generations: int
    states: int


@dataclass(frozen=True)
class SharedRule:
    g: int
    k: int
    mean_predicted_variance: float


@dataclass(frozen=True)
class BenefitComparison:
    shallow_k: int
    deep_k: int
    predicted_delta_j: float
    observed_delta_j: float
    predicted_deeper_is_better: bool
    observed_deeper_is_better: bool
    recommendation_loss: float


@dataclass(frozen=True)
class CoverageResult:
    covered: int
    total: int
    coverage: float
    mean_width: float


@dataclass(frozen=True)
class DecisionResult:
    correct: int
    ties: int
    total: int

    @property
    def correct_rate(self) -> float:
        return self.correct / self.total if self.total else float("nan")

    @property
    def tie_rate(self) -> float:
        return self.ties / self.total if self.total else float("nan")


def _sample_variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = mean(values)
    return sum((value - center) ** 2 for value in values) / (len(values) - 1)


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("cannot take percentile of empty values")
    if not 0 <= p <= 1:
        raise ValueError("p must be in [0,1]")
    ordered = sorted(float(x) for x in values)
    if len(ordered) == 1:
        return ordered[0]
    position = p * (len(ordered) - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    fraction = position - lo
    return ordered[lo] * (1 - fraction) + ordered[hi] * fraction


def _observed(records: Iterable[AuditRecord]) -> list[AuditRecord]:
    values = list(records)
    pending = [r for r in values if r.failed is None]
    if pending:
        raise ValueError(f"analysis requires resolved labels; found {len(pending)} unresolved rows")
    if not values:
        raise ValueError("analysis requires non-empty records")
    return values


def records_by_system(records: Iterable[AuditRecord]) -> dict[str, list[AuditRecord]]:
    grouped: dict[str, list[AuditRecord]] = {}
    for record in _observed(records):
        grouped.setdefault(record.system_id, []).append(record)
    return grouped


def filter_templates(records: Iterable[AuditRecord], template_ids: set[str]) -> list[AuditRecord]:
    return [record for record in records if record.template_id in template_ids]


def infer_pool_shape(records: Iterable[AuditRecord]) -> PoolShape:
    values = _observed(records)
    templates = sorted({r.template_id for r in values})
    by_template: dict[str, set[int]] = {t: set() for t in templates}
    by_program: dict[tuple[str, int], set[str]] = {}
    for record in values:
        by_template[record.template_id].add(record.generation_id)
        by_program.setdefault((record.template_id, record.generation_id), set()).add(record.state_id)
    generation_counts = {len(v) for v in by_template.values()}
    state_counts = {len(v) for v in by_program.values()}
    if len(generation_counts) != 1 or len(state_counts) != 1:
        raise ValueError("analysis requires a balanced complete finite audit pool")
    return PoolShape(len(templates), next(iter(generation_counts)), next(iter(state_counts)))


def choose_component_rule(
    components: VarianceComponents,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    *,
    allowed_k: Iterable[int] | None = None,
) -> Allocation:
    """Choose q/g/k from calibration components for a future formal evaluation.

    Selection uses Equation (4) because calibration estimates the uncertainty
    structure; the formal test pool is used only later for Equation (5) replay
    validation.  ``q`` is capped by the formal pool size and is always the
    largest value affordable for the candidate g/k pair.
    """
    k_values = tuple(allowed_k) if allowed_k is not None else tuple(range(1, max_states + 1))
    candidates: list[Allocation] = []
    for g in range(1, max_generations + 1):
        for k in k_values:
            if k < 1 or k > max_states:
                continue
            try:
                candidates.append(
                    allocation_for_rule(
                        components,
                        cost,
                        budget,
                        max_templates,
                        max_generations,
                        max_states,
                        g,
                        k,
                        finite_reference=False,
                    )
                )
            except ValueError as exc:
                if "budget does not buy" not in str(exc):
                    raise
    if not candidates:
        raise ValueError("no feasible formal allocation")
    return min(candidates, key=lambda x: (x.variance, -x.q, x.cost, x.g, x.k))


def choose_fixed_depth(
    components: VarianceComponents,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    k: int,
) -> Allocation:
    return choose_component_rule(
        components,
        cost,
        budget,
        max_templates,
        max_generations,
        max_states,
        allowed_k=(k,),
    )


def observed_design_j(records: Iterable[AuditRecord], allocation: Allocation, budget: float) -> float:
    values = _observed(records)
    shape = infer_pool_shape(values)
    if allocation.q > shape.templates or allocation.g > shape.generations or allocation.k > shape.states:
        raise ValueError("allocation exceeds observed finite test pool")
    components = estimate_finite_variance_components(values)
    return float(budget) * finite_population_variance(
        components,
        allocation.q,
        allocation.g,
        allocation.k,
        shape.states,
        shape.templates,
        shape.generations,
    )


def predicted_j(components: VarianceComponents, allocation: Allocation, budget: float, states: int) -> float:
    return float(budget) * superpopulation_variance(components, allocation.q, allocation.g, allocation.k, states)


def fixed_depth_report(
    calibration_records: Mapping[str, Sequence[AuditRecord]],
    test_records: Mapping[str, Sequence[AuditRecord]],
    costs: Mapping[str, CostModel],
    budget: float,
    depths: Sequence[int],
    *,
    program_mse_repeats: int = 0,
    seed: int = 20270901,
) -> dict[str, dict[int, dict[str, float | int]]]:
    from .replay import FiniteAuditPool

    output: dict[str, dict[int, dict[str, float | int]]] = {}
    for system in sorted(test_records):
        cal = _observed(calibration_records[system])
        test = _observed(test_records[system])
        shape = infer_pool_shape(test)
        components = estimate_variance_components(cal)
        pool = FiniteAuditPool(test)
        output[system] = {}
        for k in depths:
            allocation = choose_fixed_depth(
                components, costs[system], budget, shape.templates, shape.generations, shape.states, k
            )
            if program_mse_repeats:
                program_mse = pool.program_mse(k, repeats=program_mse_repeats, seed=seed + k)
            else:
                # Exact design MSE, averaged over the finite program population.
                groups: dict[tuple[str, int], list[float]] = {}
                for r in test:
                    groups.setdefault((r.template_id, r.generation_id), []).append(float(r.failed))
                program_mse = mean(
                    _sample_variance(v) * (1 / k - 1 / len(v)) if k < len(v) else 0.0
                    for v in groups.values()
                )
            output[system][int(k)] = {
                "q": allocation.q,
                "g": allocation.g,
                "k": allocation.k,
                "predicted_J": predicted_j(components, allocation, budget, shape.states),
                "J": observed_design_j(test, allocation, budget),
                "program_MSE": program_mse,
                "cost": allocation.cost,
                "unused_budget": float(budget) - allocation.cost,
            }
    return output


def benefit_direction_report(
    fixed_report: Mapping[str, Mapping[int, Mapping[str, float | int]]],
    transitions: Sequence[tuple[int, int]],
) -> dict[str, object]:
    per_system: dict[str, dict[str, dict[str, object]]] = {}
    correct = 0
    total = 0
    wrong_losses: list[float] = []
    for system, by_k in fixed_report.items():
        per_system[system] = {}
        for shallow, deep in transitions:
            a = by_k[shallow]
            b = by_k[deep]
            pred_delta = float(b["predicted_J"]) - float(a["predicted_J"])
            obs_delta = float(b["J"]) - float(a["J"])
            pred_better = pred_delta < 0
            obs_better = obs_delta < 0
            is_correct = pred_better == obs_better
            recommended_j = float(b["J"]) if pred_better else float(a["J"])
            best_j = min(float(a["J"]), float(b["J"]))
            loss = recommended_j - best_j
            total += 1
            correct += int(is_correct)
            if not is_correct:
                wrong_losses.append(loss)
            per_system[system][f"k{shallow}_to_k{deep}"] = {
                "predicted_delta_J": pred_delta,
                "observed_delta_J": obs_delta,
                "direction_correct": is_correct,
                "recommendation_loss": loss,
            }
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else float("nan"),
        "mean_wrong_recommendation_loss": mean(wrong_losses) if wrong_losses else 0.0,
        "comparisons": per_system,
    }


def choose_shared_rule(
    calibration_components: Mapping[str, VarianceComponents],
    costs: Mapping[str, CostModel],
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    *,
    allowed_k: Iterable[int] | None = None,
) -> SharedRule:
    systems = sorted(calibration_components)
    if set(systems) != set(costs):
        raise ValueError("calibration components and costs must name the same systems")
    k_values = tuple(allowed_k) if allowed_k is not None else tuple(range(1, max_states + 1))
    scored: list[tuple[float, int, int]] = []
    for g, k in product(range(1, max_generations + 1), k_values):
        variances: list[float] = []
        feasible = True
        for system in systems:
            try:
                alloc = allocation_for_rule(
                    calibration_components[system], costs[system], budget,
                    max_templates, max_generations, max_states, g, k,
                    finite_reference=False,
                )
            except ValueError:
                feasible = False
                break
            variances.append(alloc.variance)
        if feasible:
            scored.append((mean(variances), g, k))
    if not scored:
        raise ValueError("no shared rule is feasible for every system")
    score, g, k = min(scored, key=lambda item: (item[0], item[1], item[2]))
    return SharedRule(g=g, k=k, mean_predicted_variance=score)


def apply_shared_rule(
    rule: SharedRule,
    evaluation_components: Mapping[str, VarianceComponents],
    costs: Mapping[str, CostModel],
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    *,
    finite_reference: bool = False,
) -> dict[str, Allocation]:
    return {
        system: allocation_for_rule(
            evaluation_components[system], costs[system], budget,
            max_templates, max_generations, max_states, rule.g, rule.k,
            finite_reference=finite_reference,
        )
        for system in sorted(evaluation_components)
    }


def pooled_and_loso_report(
    calibration_records: Mapping[str, Sequence[AuditRecord]],
    test_records: Mapping[str, Sequence[AuditRecord]],
    costs: Mapping[str, CostModel],
    budget: float,
) -> dict[str, object]:
    systems = sorted(test_records)
    test_shape = infer_pool_shape(test_records[systems[0]])
    cal_components = {s: estimate_variance_components(calibration_records[s]) for s in systems}
    test_components = {s: estimate_finite_variance_components(test_records[s]) for s in systems}

    pooled = choose_shared_rule(
        cal_components, costs, budget, test_shape.templates, test_shape.generations, test_shape.states
    )
    pooled_allocs = apply_shared_rule(
        pooled, test_components, costs, budget,
        test_shape.templates, test_shape.generations, test_shape.states,
        finite_reference=True,
    )

    loso: dict[str, dict[str, float | int]] = {}
    for held_out in systems:
        remaining_components = {s: cal_components[s] for s in systems if s != held_out}
        remaining_costs = {s: costs[s] for s in systems if s != held_out}
        rule = choose_shared_rule(
            remaining_components, remaining_costs, budget,
            test_shape.templates, test_shape.generations, test_shape.states,
        )
        alloc = allocation_for_rule(
            test_components[held_out], costs[held_out], budget,
            test_shape.templates, test_shape.generations, test_shape.states,
            rule.g, rule.k, finite_reference=True,
        )
        loso[held_out] = {"q": alloc.q, "g": alloc.g, "k": alloc.k, "J": budget * alloc.variance}

    return {
        "pooled_rule": {"g": pooled.g, "k": pooled.k},
        "pooled": {
            s: {"q": a.q, "g": a.g, "k": a.k, "J": budget * a.variance}
            for s, a in pooled_allocs.items()
        },
        "leave_one_system_out": loso,
    }


def system_calibration_report(
    calibration_records: Mapping[str, Sequence[AuditRecord]],
    test_records: Mapping[str, Sequence[AuditRecord]],
    costs: Mapping[str, CostModel],
    budget: float,
) -> dict[str, dict[str, float | int]]:
    output: dict[str, dict[str, float | int]] = {}
    for system in sorted(test_records):
        shape = infer_pool_shape(test_records[system])
        alloc = choose_component_rule(
            estimate_variance_components(calibration_records[system]), costs[system], budget,
            shape.templates, shape.generations, shape.states,
        )
        output[system] = {
            "q": alloc.q, "g": alloc.g, "k": alloc.k,
            "predicted_J": budget * alloc.variance,
            "J": observed_design_j(test_records[system], alloc, budget),
        }
    return output


def _estimate_finite_stratified_components(records: Sequence[AuditRecord]) -> StratifiedVarianceComponents:
    """Direct finite-pool four-stratum components for a complete audit pool."""
    programs: dict[tuple[str, int], dict[str, list[float]]] = {}
    for record in _observed(records):
        programs.setdefault((record.template_id, record.generation_id), {kind: [] for kind in EDIT_TYPES})[record.edit_type].append(float(record.failed))
    template_program_means: dict[str, list[float]] = {}
    edit_vars: dict[str, list[float]] = {kind: [] for kind in EDIT_TYPES}
    for (template_id, _), strata in programs.items():
        if any(not strata[kind] for kind in EDIT_TYPES):
            raise ValueError("finite stratified pool must contain every edit type in every program")
        program_mean = mean(mean(strata[kind]) for kind in EDIT_TYPES)
        template_program_means.setdefault(template_id, []).append(program_mean)
        for kind in EDIT_TYPES:
            edit_vars[kind].append(_sample_variance(strata[kind]))
    return StratifiedVarianceComponents(
        template=_sample_variance([mean(values) for values in template_program_means.values()]),
        generation=mean(_sample_variance(values) for values in template_program_means.values()),
        edit={kind: mean(values) for kind, values in edit_vars.items()},
    )


def stratified_system_report(
    calibration_records: Mapping[str, Sequence[AuditRecord]],
    test_records: Mapping[str, Sequence[AuditRecord]],
    costs: Mapping[str, CostModel],
    budget: float,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for system in sorted(test_records):
        shape = infer_pool_shape(test_records[system])
        cal = estimate_stratified_variance_components(calibration_records[system])
        m_by_type = {kind: shape.states // len(EDIT_TYPES) for kind in EDIT_TYPES}
        alloc = optimize_stratified_allocation(
            cal, costs[system], budget, shape.templates, shape.generations, m_by_type,
            finite_reference=False,
        )
        test_components = _estimate_finite_stratified_components(test_records[system])
        test_var = _stratified_test_variance(test_components, alloc, shape, m_by_type)
        output[system] = {
            "q": alloc.q, "g": alloc.g, "k": alloc.k,
            "k_by_type": dict(alloc.k_by_type),
            "predicted_J": budget * alloc.variance,
            "J": budget * test_var,
        }
    return output


def _stratified_test_variance(
    components: StratifiedVarianceComponents,
    allocation: StratifiedAllocation,
    shape: PoolShape,
    m_by_type: Mapping[str, int],
) -> float:
    from .strategies import stratified_variance
    return stratified_variance(
        components, allocation.q, allocation.g, allocation.k_by_type, m_by_type,
        reference_templates=shape.templates, reference_generations=shape.generations,
    )


def shared_oracle_rule(
    test_records: Mapping[str, Sequence[AuditRecord]],
    costs: Mapping[str, CostModel],
    budget: float,
) -> tuple[SharedRule, dict[str, float]]:
    systems = sorted(test_records)
    shape = infer_pool_shape(test_records[systems[0]])
    components = {s: estimate_finite_variance_components(test_records[s]) for s in systems}
    scored: list[tuple[float, int, int, dict[str, float]]] = []
    for g, k in product(range(1, shape.generations + 1), range(1, shape.states + 1)):
        js: dict[str, float] = {}
        feasible = True
        for system in systems:
            try:
                a = allocation_for_rule(
                    components[system], costs[system], budget,
                    shape.templates, shape.generations, shape.states,
                    g, k, finite_reference=True,
                )
            except ValueError:
                feasible = False
                break
            js[system] = budget * a.variance
        if feasible:
            scored.append((mean(js.values()), g, k, js))
    if not scored:
        raise ValueError("no oracle rule feasible")
    score, g, k, js = min(scored, key=lambda x: (x[0], x[1], x[2]))
    return SharedRule(g, k, score / budget), js


def system_oracle_j(records: Sequence[AuditRecord], cost: CostModel, budget: float) -> tuple[Allocation, float]:
    shape = infer_pool_shape(records)
    components = estimate_finite_variance_components(records)
    candidates: list[Allocation] = []
    for g, k in product(range(1, shape.generations + 1), range(1, shape.states + 1)):
        try:
            candidates.append(
                allocation_for_rule(
                    components, cost, budget, shape.templates, shape.generations, shape.states,
                    g, k, finite_reference=True,
                )
            )
        except ValueError:
            pass
    best = min(candidates, key=lambda x: (x.variance, x.g, x.k))
    return best, budget * best.variance


def regret_summary(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("regret summary requires values")
    return {
        "robust_coverage_5pct": mean(1.0 if x <= 1.05 + 1e-12 else 0.0 for x in values),
        "median_regret": median(values),
        "mean_regret": mean(values),
        "p90_regret": _percentile(values, 0.90),
    }


def random_template_split_stability(
    full_records: Mapping[str, Sequence[AuditRecord]],
    template_family: Mapping[str, str],
    costs: Mapping[str, CostModel],
    budget: float,
    *,
    calibration_per_family: int,
    repeats: int = 40,
    seed: int = 20270901,
) -> dict[str, dict[str, float]]:
    systems = sorted(full_records)
    families: dict[str, list[str]] = {}
    for template_id, family in template_family.items():
        families.setdefault(family, []).append(template_id)
    if any(len(ids) <= calibration_per_family for ids in families.values()):
        raise ValueError("each family needs calibration and test templates")
    rng = random.Random(seed)
    regrets = {s: [] for s in systems}
    for _ in range(repeats):
        cal_ids: set[str] = set()
        test_ids: set[str] = set()
        for family in sorted(families):
            ids = sorted(families[family])
            chosen = set(rng.sample(ids, calibration_per_family))
            cal_ids.update(chosen)
            test_ids.update(set(ids) - chosen)
        for system in systems:
            cal = filter_templates(full_records[system], cal_ids)
            test = filter_templates(full_records[system], test_ids)
            shape = infer_pool_shape(test)
            candidate = choose_component_rule(
                estimate_variance_components(cal), costs[system], budget,
                shape.templates, shape.generations, shape.states,
            )
            candidate_j = observed_design_j(test, candidate, budget)
            _, oracle_j = system_oracle_j(test, costs[system], budget)
            regrets[system].append(candidate_j / oracle_j if oracle_j > 0 else 1.0)
    return {system: regret_summary(values) for system, values in regrets.items()}


def leave_one_family_out_stability(
    full_records: Mapping[str, Sequence[AuditRecord]],
    template_family: Mapping[str, str],
    costs: Mapping[str, CostModel],
    budget: float,
) -> dict[str, dict[str, float]]:
    """Calibrate on all but one family and evaluate on that held-out family."""
    systems = sorted(full_records)
    families: dict[str, set[str]] = {}
    for template_id, family in template_family.items():
        families.setdefault(family, set()).add(template_id)
    all_ids = set(template_family)
    regrets = {s: [] for s in systems}
    for family in sorted(families):
        test_ids = families[family]
        cal_ids = all_ids - test_ids
        for system in systems:
            cal = filter_templates(full_records[system], cal_ids)
            test = filter_templates(full_records[system], test_ids)
            shape = infer_pool_shape(test)
            candidate = choose_component_rule(
                estimate_variance_components(cal), costs[system], budget,
                shape.templates, shape.generations, shape.states,
            )
            candidate_j = observed_design_j(test, candidate, budget)
            _, oracle_j = system_oracle_j(test, costs[system], budget)
            regrets[system].append(candidate_j / oracle_j if oracle_j > 0 else 1.0)
    return {system: regret_summary(values) for system, values in regrets.items()}


def _subset_generations(records: Sequence[AuditRecord], template_ids: set[str], generation_limit: int) -> list[AuditRecord]:
    return [r for r in records if r.template_id in template_ids and r.generation_id < generation_limit]


def _mean_stratified_components(values: Sequence[StratifiedVarianceComponents]) -> StratifiedVarianceComponents:
    if not values:
        raise ValueError("stratified pooling needs at least one component vector")
    kinds = tuple(values[0].edit)
    return StratifiedVarianceComponents(
        template=mean(v.template for v in values),
        generation=mean(v.generation for v in values),
        edit={kind: mean(v.edit[kind] for v in values) for kind in kinds},
        weights=values[0].weights,
    )


def _shrink_stratified(
    pilot: StratifiedVarianceComponents,
    pooled: StratifiedVarianceComponents,
    weight: float,
) -> StratifiedVarianceComponents:
    return StratifiedVarianceComponents(
        template=weight * pilot.template + (1 - weight) * pooled.template,
        generation=weight * pilot.generation + (1 - weight) * pooled.generation,
        edit={kind: weight * pilot.edit[kind] + (1 - weight) * pooled.edit[kind] for kind in pilot.edit},
        weights=pilot.weights,
    )


def cross_environment_transfer_report(
    source_calibration: Mapping[str, Sequence[AuditRecord]],
    source_test: Mapping[str, Sequence[AuditRecord]],
    target_calibration: Mapping[str, Sequence[AuditRecord]],
    target_test: Mapping[str, Sequence[AuditRecord]],
    source_costs: Mapping[str, CostModel],
    target_costs: Mapping[str, CostModel],
    budget: float,
    fixed_depths: Sequence[int],
    *,
    target_template_family: Mapping[str, str] | None = None,
) -> dict[str, object]:
    systems = sorted(target_test)
    shape = infer_pool_shape(target_test[systems[0]])
    source_shape = infer_pool_shape(source_test[systems[0]])
    source_components = {s: estimate_variance_components(source_calibration[s]) for s in systems}
    target_components = {s: estimate_variance_components(target_calibration[s]) for s in systems}
    test_components = {s: estimate_finite_variance_components(target_test[s]) for s in systems}

    # Freeze source g/k, then remap q using target-environment measured costs.
    source_rule = choose_shared_rule(
        source_components, source_costs, budget,
        source_shape.templates, source_shape.generations, source_shape.states,
    )
    if source_rule.g > shape.generations:
        raise ValueError("source pooled rule requests more generations than target environment provides")

    def eval_rule(g: int, k: int) -> tuple[float, float]:
        js: list[float] = []
        ks: list[int] = []
        for s in systems:
            a = allocation_for_rule(
                test_components[s], target_costs[s], budget,
                shape.templates, shape.generations, shape.states,
                g, k, finite_reference=True,
            )
            js.append(budget * a.variance)
            ks.append(k)
        return mean(js), mean(ks)

    result: dict[str, dict[str, float | int]] = {}
    for k in fixed_depths:
        js, ks = [], []
        for s in systems:
            a = choose_fixed_depth(
                target_components[s], target_costs[s], budget,
                shape.templates, shape.generations, shape.states, k,
            )
            js.append(observed_design_j(target_test[s], a, budget))
            ks.append(a.k)
        result[f"fixed_k{k}"] = {"mean_J": mean(js), "mean_k": mean(ks)}

    source_mean_j, source_mean_k = eval_rule(source_rule.g, source_rule.k)
    result["source_pooled_transfer"] = {
        "mean_J": source_mean_j, "mean_k": source_mean_k, "g": source_rule.g, "k": source_rule.k
    }

    target_pooled_rule = choose_shared_rule(
        target_components, target_costs, budget, shape.templates, shape.generations, shape.states
    )
    pooled_mean_j, pooled_mean_k = eval_rule(target_pooled_rule.g, target_pooled_rule.k)
    result["target_pooled"] = {
        "mean_J": pooled_mean_j, "mean_k": pooled_mean_k, "g": target_pooled_rule.g, "k": target_pooled_rule.k
    }

    loso_rows: list[tuple[float, int]] = []
    for held in systems:
        comps = {s: target_components[s] for s in systems if s != held}
        csts = {s: target_costs[s] for s in systems if s != held}
        rule = choose_shared_rule(comps, csts, budget, shape.templates, shape.generations, shape.states)
        a = allocation_for_rule(
            test_components[held], target_costs[held], budget,
            shape.templates, shape.generations, shape.states,
            rule.g, rule.k, finite_reference=True,
        )
        loso_rows.append((budget * a.variance, a.k))
    result["leave_one_system_out"] = {
        "mean_J": mean(x for x, _ in loso_rows), "mean_k": mean(k for _, k in loso_rows)
    }

    system_rows: list[tuple[float, int]] = []
    for s in systems:
        a = choose_component_rule(
            target_components[s], target_costs[s], budget,
            shape.templates, shape.generations, shape.states,
        )
        system_rows.append((observed_design_j(target_test[s], a, budget), a.k))
    result["full_system_calibration"] = {
        "mean_J": mean(x for x, _ in system_rows), "mean_k": mean(k for _, k in system_rows)
    }

    # Small calibration: one template per target family, two generations, all
    # states. A common shrinkage weight is selected using two complementary
    # within-calibration folds and then applied to the four-class components.
    if target_template_family:
        families: dict[str, list[str]] = {}
        calibration_ids = {r.template_id for rows in target_calibration.values() for r in rows}
        for tid in sorted(calibration_ids):
            if tid in target_template_family:
                families.setdefault(target_template_family[tid], []).append(tid)
        if families and all(len(ids) >= 2 for ids in families.values()):
            left_ids = {sorted(ids)[0] for ids in families.values()}
            right_ids = {sorted(ids)[1] for ids in families.values()}
            pooled_unstrat = VarianceComponents(
                template=mean(v.template for v in target_components.values()),
                generation=mean(v.generation for v in target_components.values()),
                edit=mean(v.edit for v in target_components.values()),
            )
            pooled_strat = _mean_stratified_components([
                estimate_stratified_variance_components(target_calibration[s]) for s in systems
            ])
            pilot_rows: list[tuple[float, int]] = []
            for s in systems:
                left = _subset_generations(target_calibration[s], left_ids, 2)
                right = _subset_generations(target_calibration[s], right_ids, 2)
                folds = [
                    (estimate_variance_components(left), estimate_variance_components(right)),
                    (estimate_variance_components(right), estimate_variance_components(left)),
                ]
                weight = select_pilot_shrinkage_weight(folds, pooled_unstrat)
                pilot_strat = estimate_stratified_variance_components(left)
                shrunk = _shrink_stratified(pilot_strat, pooled_strat, weight)
                m_by_type = {kind: shape.states // len(EDIT_TYPES) for kind in EDIT_TYPES}
                alloc = optimize_stratified_allocation(
                    shrunk, target_costs[s], budget,
                    shape.templates, shape.generations, m_by_type,
                    finite_reference=False,
                )
                test_strat = _estimate_finite_stratified_components(target_test[s])
                j = budget * _stratified_test_variance(test_strat, alloc, shape, m_by_type)
                pilot_rows.append((j, alloc.k))
            result["small_calibration_stratified"] = {
                "mean_J": mean(x for x, _ in pilot_rows),
                "mean_k": mean(k for _, k in pilot_rows),
            }

    best = min(float(values["mean_J"]) for values in result.values())
    for values in result.values():
        values["relative_to_best_percent"] = 100.0 * (float(values["mean_J"]) / best - 1.0) if best > 0 else 0.0
    return result


def _nested_index(records: Sequence[AuditRecord]) -> dict[str, dict[int, list[AuditRecord]]]:
    indexed: dict[str, dict[int, list[AuditRecord]]] = {}
    for record in records:
        indexed.setdefault(record.template_id, {}).setdefault(record.generation_id, []).append(record)
    return indexed


def _draw_records(
    index: Mapping[str, Mapping[int, Sequence[AuditRecord]]],
    q: int,
    g: int,
    k: int,
    rng: random.Random,
) -> list[AuditRecord]:
    templates = rng.sample(sorted(index), q)
    output: list[AuditRecord] = []
    for template_id in templates:
        generations = index[template_id]
        for generation_id in rng.sample(sorted(generations), g):
            output.extend(rng.sample(list(generations[generation_id]), k))
    return output


def _three_level_interval(sample: Sequence[AuditRecord], full_shape: PoolShape) -> tuple[float, float]:
    point = risk(sample)
    shape = infer_pool_shape(sample)
    components = estimate_finite_variance_components(
        sample, full_generations=full_shape.generations, full_states=full_shape.states
    )
    variance = finite_population_variance(
        components, shape.templates, shape.generations, shape.states,
        full_shape.states, full_shape.templates, full_shape.generations,
    )
    critical = t_critical_95(shape.templates - 1)
    half = critical * math.sqrt(max(0.0, variance))
    return max(0.0, point - half), min(1.0, point + half)


def _program_independent_interval(sample: Sequence[AuditRecord], full_shape: PoolShape) -> tuple[float, float]:
    point = risk(sample)
    programs: dict[tuple[str, int], list[float]] = {}
    for record in sample:
        programs.setdefault((record.template_id, record.generation_id), []).append(float(record.failed))
    means = [mean(v) for v in programs.values()]
    n = len(means)
    if n < 2:
        return point, point
    population_n = full_shape.templates * full_shape.generations
    variance = max(0.0, (1 / n - 1 / population_n) * _sample_variance(means))
    critical = t_critical_95(n - 1)
    half = critical * math.sqrt(variance)
    return max(0.0, point - half), min(1.0, point + half)


def confidence_interval_coverage(
    records: Sequence[AuditRecord],
    q: int,
    g: int,
    k: int,
    *,
    repeats: int = 5000,
    seed: int = 20270901,
) -> dict[str, CoverageResult]:
    values = _observed(records)
    full_shape = infer_pool_shape(values)
    if q > full_shape.templates or g > full_shape.generations or k > full_shape.states:
        raise ValueError("coverage allocation exceeds finite pool")
    target = risk(values)
    index = _nested_index(values)
    rng = random.Random(seed)
    counts = {"three_level": 0, "program_independent": 0}
    widths = {"three_level": [], "program_independent": []}
    for _ in range(repeats):
        sample = _draw_records(index, q, g, k, rng)
        intervals = {
            "three_level": _three_level_interval(sample, full_shape),
            "program_independent": _program_independent_interval(sample, full_shape),
        }
        for name, (low, high) in intervals.items():
            counts[name] += int(low <= target <= high)
            widths[name].append(high - low)
    return {
        name: CoverageResult(counts[name], repeats, counts[name] / repeats, mean(widths[name]))
        for name in counts
    }


def paired_replay_decisions(
    records_a: Sequence[AuditRecord],
    records_b: Sequence[AuditRecord],
    allocation: Allocation,
    *,
    repeats: int = 2000,
    seed: int = 20270901,
) -> DecisionResult:
    observations = paired_observations(records_a, records_b)
    by_template: dict[str, dict[int, list[float]]] = {}
    for obs in observations:
        by_template.setdefault(obs.template_id, {}).setdefault(obs.generation_id, []).append(obs.difference)
    Q = len(by_template)
    Gs = {len(v) for v in by_template.values()}
    Ms = {len(states) for v in by_template.values() for states in v.values()}
    if len(Gs) != 1 or len(Ms) != 1:
        raise ValueError("paired replay requires balanced matched pools")
    if allocation.q > Q or allocation.g > next(iter(Gs)) or allocation.k > next(iter(Ms)):
        raise ValueError("paired allocation exceeds matched pool")
    target = mean(obs.difference for obs in observations)
    target_sign = 0 if abs(target) < 1e-15 else (1 if target > 0 else -1)
    rng = random.Random(seed)
    correct = ties = 0
    for _ in range(repeats):
        values: list[float] = []
        for template_id in rng.sample(sorted(by_template), allocation.q):
            generations = by_template[template_id]
            for generation_id in rng.sample(sorted(generations), allocation.g):
                values.extend(rng.sample(generations[generation_id], allocation.k))
        estimate = mean(values)
        sign = 0 if abs(estimate) < 1e-15 else (1 if estimate > 0 else -1)
        if sign == 0:
            ties += 1
        elif sign == target_sign:
            correct += 1
    return DecisionResult(correct, ties, repeats)


def _paired_stratified_components(
    records_a: Sequence[AuditRecord], records_b: Sequence[AuditRecord]
) -> StratifiedVarianceComponents:
    observations = paired_observations(records_a, records_b)
    by_program: dict[tuple[str, int], dict[str, list[float]]] = {}
    for obs in observations:
        by_program.setdefault((obs.template_id, obs.generation_id), {k: [] for k in EDIT_TYPES})[obs.edit_type].append(obs.difference)
    template_program_means: dict[str, list[float]] = {}
    edit_vars: dict[str, list[float]] = {k: [] for k in EDIT_TYPES}
    for (template_id, _), strata in by_program.items():
        if any(not strata[k] for k in EDIT_TYPES):
            raise ValueError("paired stratified calibration requires all edit types")
        program_mean = mean(mean(strata[k]) for k in EDIT_TYPES)
        template_program_means.setdefault(template_id, []).append(program_mean)
        for k in EDIT_TYPES:
            edit_vars[k].append(_sample_variance(strata[k]))
    return StratifiedVarianceComponents(
        template=_sample_variance([mean(v) for v in template_program_means.values()]),
        generation=mean(_sample_variance(v) for v in template_program_means.values()),
        edit={k: mean(v) for k, v in edit_vars.items()},
    )


def pairwise_decision_report(
    calibration_records: Mapping[str, Sequence[AuditRecord]],
    test_records: Mapping[str, Sequence[AuditRecord]],
    costs: Mapping[str, CostModel],
    budgets: Sequence[float],
    *,
    fixed_depths: Sequence[int] = (8, 9, 10),
    repeats: int = 2000,
    seed: int = 20270901,
) -> dict[str, dict[str, float]]:
    systems = sorted(test_records)
    pairs = list(combinations(systems, 2))
    shape = infer_pool_shape(test_records[systems[0]])
    m_by_type = {k: shape.states // len(EDIT_TYPES) for k in EDIT_TYPES}
    output: dict[str, dict[str, float]] = {}
    for budget in budgets:
        methods: dict[str, list[DecisionResult]] = {f"fixed_k{k}": [] for k in fixed_depths}
        methods["paired_system"] = []
        methods["paired_system_stratified"] = []
        for pair_index, (a, b) in enumerate(pairs):
            cal_a, cal_b = calibration_records[a], calibration_records[b]
            test_a, test_b = test_records[a], test_records[b]
            pair_cost = paired_cost_model(costs[a], costs[b])
            components = paired_variance_components(cal_a, cal_b)
            for k in fixed_depths:
                alloc = choose_fixed_depth(components, pair_cost, budget, shape.templates, shape.generations, shape.states, k)
                methods[f"fixed_k{k}"].append(
                    paired_replay_decisions(test_a, test_b, alloc, repeats=repeats, seed=seed + pair_index * 101 + k)
                )
            alloc = choose_component_rule(components, pair_cost, budget, shape.templates, shape.generations, shape.states)
            methods["paired_system"].append(
                paired_replay_decisions(test_a, test_b, alloc, repeats=repeats, seed=seed + pair_index * 101 + 41)
            )
            strat_components = _paired_stratified_components(cal_a, cal_b)
            strat_alloc = optimize_stratified_allocation(
                strat_components, pair_cost, budget, shape.templates, shape.generations, m_by_type,
                finite_reference=False,
            )
            # Replay the stratified design directly with matched state classes.
            methods["paired_system_stratified"].append(
                _paired_stratified_replay_decisions(
                    test_a, test_b, strat_alloc, repeats=repeats, seed=seed + pair_index * 101 + 73
                )
            )
        output[str(int(budget))] = {}
        for method, rows in methods.items():
            total = sum(r.total for r in rows)
            output[str(int(budget))][method] = {
                "correct_rate": sum(r.correct for r in rows) / total,
                "tie_rate": sum(r.ties for r in rows) / total,
            }
    return output


def _paired_stratified_replay_decisions(
    records_a: Sequence[AuditRecord],
    records_b: Sequence[AuditRecord],
    allocation: StratifiedAllocation,
    *,
    repeats: int,
    seed: int,
) -> DecisionResult:
    obs = paired_observations(records_a, records_b)
    nested: dict[str, dict[int, dict[str, list[float]]]] = {}
    for x in obs:
        nested.setdefault(x.template_id, {}).setdefault(x.generation_id, {k: [] for k in EDIT_TYPES})[x.edit_type].append(x.difference)
    target = mean(x.difference for x in obs)
    target_sign = 0 if abs(target) < 1e-15 else (1 if target > 0 else -1)
    rng = random.Random(seed)
    correct = ties = 0
    for _ in range(repeats):
        estimates: list[float] = []
        for t in rng.sample(sorted(nested), allocation.q):
            for g in rng.sample(sorted(nested[t]), allocation.g):
                weighted = []
                for kind in EDIT_TYPES:
                    k = allocation.k_by_type[kind]
                    weighted.append(mean(rng.sample(nested[t][g][kind], k)))
                estimates.append(mean(weighted))
        estimate = mean(estimates)
        sign = 0 if abs(estimate) < 1e-15 else (1 if estimate > 0 else -1)
        if sign == 0:
            ties += 1
        elif sign == target_sign:
            correct += 1
    return DecisionResult(correct, ties, repeats)


def cohen_kappa(labels_a: Sequence[bool], labels_b: Sequence[bool]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("kappa requires equally sized non-empty label vectors")
    n = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    pa = mean(int(x) for x in labels_a)
    pb = mean(int(x) for x in labels_b)
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected >= 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def expert_validation_report(
    population_records: Sequence[AuditRecord],
    annotations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Inverse-probability expert validation for system x edit type x auto label strata.

    Annotation rows require ``system_id``, ``template_id``, ``generation_id``,
    ``state_id``, ``expert1_label``, ``expert2_label`` and ``consensus_label``.
    Sampling probabilities are derived from the finite population and the
    realized number of annotations in each stratum.
    """
    population = _observed(population_records)
    pop_index = {(r.system_id, r.template_id, r.generation_id, r.state_id): r for r in population}
    pop_strata: dict[tuple[str, str, bool], int] = {}
    for r in population:
        pop_strata[(r.system_id, r.edit_type, bool(r.failed))] = pop_strata.get((r.system_id, r.edit_type, bool(r.failed)), 0) + 1
    sample_strata: dict[tuple[str, str, bool], int] = {}
    resolved: list[tuple[AuditRecord, bool, bool, bool]] = []
    for row in annotations:
        key = (str(row["system_id"]), str(row["template_id"]), int(row["generation_id"]), str(row["state_id"]))
        if key not in pop_index:
            raise ValueError(f"expert annotation key not present in population: {key}")
        r = pop_index[key]
        stratum = (r.system_id, r.edit_type, bool(r.failed))
        sample_strata[stratum] = sample_strata.get(stratum, 0) + 1
        resolved.append((r, bool(row["expert1_label"]), bool(row["expert2_label"]), bool(row["consensus_label"])))

    by_system: dict[str, list[tuple[float, bool, bool]]] = {}
    expert1, expert2 = [], []
    for r, e1, e2, consensus in resolved:
        stratum = (r.system_id, r.edit_type, bool(r.failed))
        n_h = sample_strata[stratum]
        N_h = pop_strata[stratum]
        weight = N_h / n_h
        by_system.setdefault(r.system_id, []).append((weight, bool(r.failed), consensus))
        expert1.append(e1)
        expert2.append(e2)

    systems_out: dict[str, object] = {}
    for system, rows in sorted(by_system.items()):
        total_w = sum(w for w, _, _ in rows)
        expert_risk = sum(w * int(e) for w, _, e in rows) / total_w
        auto_risk = sum(w * int(a) for w, a, _ in rows) / total_w
        tp = sum(w for w, a, e in rows if a and e)
        fp = sum(w for w, a, e in rows if a and not e)
        tn = sum(w for w, a, e in rows if not a and not e)
        fn = sum(w for w, a, e in rows if not a and e)
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        specificity = tn / (tn + fp) if tn + fp else 1.0
        accuracy = (tp + tn) / (tp + fp + tn + fn)
        systems_out[system] = {
            "expert_reference_risk": expert_risk,
            "automatic_risk": auto_risk,
            "precision": precision,
            "recall": recall,
            "specificity": specificity,
            "accuracy": accuracy,
        }
    return {
        "sample_count": len(resolved),
        "cohen_kappa_expert1_expert2": cohen_kappa(expert1, expert2),
        "systems": systems_out,
    }
