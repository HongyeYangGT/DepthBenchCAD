"""Statistical allocation strategies specified by the paper.

This module deliberately works only with observed calibration and audit records.
It contains the deployment-level rules that sit above the three-level variance
equations in :mod:`depthbenchcad.variance`: pooled and leave-one-system-out
rules, pilot shrinkage, edit-type strata, paired comparisons, and timing
summaries.  The functions do not create CAD outcomes or impute missing audit
states.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import floor, inf, isfinite
from statistics import mean, median
from typing import Iterable, Mapping, Sequence

from .allocation import Allocation, allocation_cost, optimize_allocation
from .schema import AuditRecord, EDIT_TYPES
from .variance import VarianceComponents, finite_population_variance, superpopulation_variance


def _finite_nonnegative(value: float, name: str) -> float:
    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def _positive_int(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _sample_variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = mean(values)
    return sum((value - average) ** 2 for value in values) / (len(values) - 1)


@dataclass(frozen=True)
class CostModel:
    """Measured wall-clock costs for the three evidence layers.

    Values can be raw seconds or normalized edit-cost units, provided all three
    use the same unit.  A template is prepared once, while a generation and its
    requested edit states are purchased for each template-generation pair.
    """

    template: float
    generation: float
    edit: float

    def __post_init__(self) -> None:
        template = _finite_nonnegative(self.template, "template cost")
        generation = _finite_nonnegative(self.generation, "generation cost")
        edit = _finite_nonnegative(self.edit, "edit cost")
        if template + generation + edit == 0:
            raise ValueError("at least one cost must be positive")
        object.__setattr__(self, "template", template)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "edit", edit)

    def total(self, q: int, g: int, k: int) -> float:
        """Return ``q*cT + q*g*(cI + k*cE)`` from Equation (6)."""
        return allocation_cost(q, g, k, self.template, self.generation, self.edit)


@dataclass(frozen=True)
class CostSummary:
    """Trimmed, ordinary, and median timing summaries required by Section 4.1."""

    n: int
    trimmed_mean_10pct: float
    ordinary_mean: float
    median: float


def trimmed_mean(values: Iterable[float], trim_fraction: float = 0.10) -> float:
    """Compute a symmetric trimmed mean, dropping ``floor(n * fraction)`` tails."""
    if not 0 <= trim_fraction < 0.5:
        raise ValueError("trim_fraction must be in [0, 0.5)")
    observations = [float(value) for value in values]
    if not observations:
        raise ValueError("cannot summarize an empty timing collection")
    if any(not isfinite(value) for value in observations):
        raise ValueError("timings must be finite")
    observations.sort()
    cut = floor(len(observations) * trim_fraction)
    retained = observations[cut : len(observations) - cut] if cut else observations
    return mean(retained)


def summarize_costs(values: Iterable[float]) -> CostSummary:
    """Report the paper's 10% trimmed mean with mean/median sensitivity values."""
    observations = [float(value) for value in values]
    if not observations:
        raise ValueError("cannot summarize an empty timing collection")
    if any(not isfinite(value) for value in observations):
        raise ValueError("timings must be finite")
    return CostSummary(
        n=len(observations),
        trimmed_mean_10pct=trimmed_mean(observations),
        ordinary_mean=mean(observations),
        median=median(observations),
    )


def measured_cost_model(
    template_seconds: Iterable[float], generation_seconds: Iterable[float], edit_seconds: Iterable[float]
) -> CostModel:
    """Construct the allocation cost model from 10%-trimmed timing samples."""
    return CostModel(
        template=trimmed_mean(template_seconds),
        generation=trimmed_mean(generation_seconds),
        edit=trimmed_mean(edit_seconds),
    )


def _validate_bounds(max_templates: int, max_generations: int, max_states: int) -> None:
    _positive_int(max_templates, "max_templates")
    _positive_int(max_generations, "max_generations")
    _positive_int(max_states, "max_states")


def _allocation_variance(
    components: VarianceComponents,
    q: int,
    g: int,
    k: int,
    max_templates: int,
    max_generations: int,
    max_states: int,
    finite_reference: bool,
) -> float:
    if finite_reference:
        return finite_population_variance(
            components, q, g, k, max_states, max_templates, max_generations
        )
    return superpopulation_variance(components, q, g, k, max_states)


def allocation_for_rule(
    components: VarianceComponents,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    g: int,
    k: int,
    *,
    finite_reference: bool = True,
) -> Allocation:
    """Apply frozen ``g``/``k`` to a system and buy its maximum feasible ``q``.

    This is the common final step for the pooled and leave-one-system-out rules:
    the shared rule is unchanged, while the target system's measured costs set
    its feasible number of templates.
    """
    _validate_bounds(max_templates, max_generations, max_states)
    _positive_int(g, "g")
    _positive_int(k, "k")
    budget = _finite_nonnegative(budget, "budget")
    if g > max_generations or k > max_states:
        raise ValueError("frozen rule exceeds the finite reference pool")
    per_template = cost.template + g * (cost.generation + k * cost.edit)
    if per_template <= 0:
        raise ValueError("a sampled template must have positive cost")
    q = min(max_templates, int(budget // per_template))
    if q < 1:
        raise ValueError("budget does not buy one template under this rule")
    total_cost = cost.total(q, g, k)
    return Allocation(
        q=q,
        g=g,
        k=k,
        cost=total_cost,
        variance=_allocation_variance(
            components,
            q,
            g,
            k,
            max_templates,
            max_generations,
            max_states,
            finite_reference,
        ),
    )


def fixed_depth_allocation(
    components: VarianceComponents,
    k: int,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    *,
    finite_reference: bool = True,
) -> Allocation:
    """Choose ``g`` at a prescribed audit depth and use the largest feasible ``q``.

    This implements the fixed-depth baseline in Section 4.4.  It deliberately
    does not inspect another depth while selecting the result.
    """
    _validate_bounds(max_templates, max_generations, max_states)
    _positive_int(k, "k")
    if k > max_states:
        raise ValueError("k cannot exceed the finite edit population")
    candidates: list[Allocation] = []
    for g in range(1, max_generations + 1):
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
                    finite_reference=finite_reference,
                )
            )
        except ValueError as error:
            if "budget does not buy" not in str(error):
                raise
    if not candidates:
        raise ValueError("budget does not buy one template at this audit depth")
    return min(candidates, key=lambda item: (item.variance, -item.q, item.cost, item.g))


def optimized_allocation(
    components: VarianceComponents,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
) -> Allocation:
    """Run the paper's integer search with a :class:`CostModel` argument."""
    _validate_bounds(max_templates, max_generations, max_states)
    return optimize_allocation(
        components,
        budget,
        cost.template,
        cost.generation,
        cost.edit,
        max_templates,
        max_generations,
        max_states,
        max_templates,
        max_generations,
    )


def aggregate_components(values: Iterable[VarianceComponents]) -> VarianceComponents:
    """Pool system calibration components by their arithmetic mean."""
    items = list(values)
    if not items:
        raise ValueError("at least one calibration component vector is required")
    return VarianceComponents(
        template=mean(component.template for component in items),
        generation=mean(component.generation for component in items),
        edit=mean(component.edit for component in items),
    )


def average_cost_model(values: Iterable[CostModel]) -> CostModel:
    """Use the cross-system mean cost model when freezing a global rule."""
    items = list(values)
    if not items:
        raise ValueError("at least one system cost model is required")
    return CostModel(
        template=mean(item.template for item in items),
        generation=mean(item.generation for item in items),
        edit=mean(item.edit for item in items),
    )


@dataclass(frozen=True)
class AllocationRule:
    """A frozen pooled rule before it is mapped to a target system's cost."""

    components: VarianceComponents
    g: int
    k: int
    budget: float
    max_templates: int
    max_generations: int
    max_states: int
    reference_cost: CostModel

    def apply(
        self,
        target_cost: CostModel,
        *,
        evaluation_components: VarianceComponents | None = None,
        target_max_templates: int | None = None,
    ) -> Allocation:
        """Map the fixed rule to one target system's measured execution cost."""
        return allocation_for_rule(
            evaluation_components or self.components,
            target_cost,
            self.budget,
            target_max_templates or self.max_templates,
            self.max_generations,
            self.max_states,
            self.g,
            self.k,
        )


def select_pooled_rule(
    calibration_components: Mapping[str, VarianceComponents] | Iterable[VarianceComponents],
    calibration_costs: Mapping[str, CostModel] | Iterable[CostModel],
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    *,
    reference_cost: CostModel | None = None,
) -> AllocationRule:
    """Freeze a cross-system ``g``/``k`` rule from calibration systems.

    The reference cost defaults to the mean measured calibration cost.  Call
    :meth:`AllocationRule.apply` for each target system; that keeps ``g`` and
    ``k`` fixed while recomputing ``q_s(g, k)`` from that target's cost.
    """
    components = aggregate_components(
        calibration_components.values()
        if isinstance(calibration_components, Mapping)
        else calibration_components
    )
    cost_values = calibration_costs.values() if isinstance(calibration_costs, Mapping) else calibration_costs
    chosen_cost = reference_cost or average_cost_model(cost_values)
    selection = optimized_allocation(
        components,
        chosen_cost,
        budget,
        max_templates,
        max_generations,
        max_states,
    )
    return AllocationRule(
        components=components,
        g=selection.g,
        k=selection.k,
        budget=float(budget),
        max_templates=max_templates,
        max_generations=max_generations,
        max_states=max_states,
        reference_cost=chosen_cost,
    )


def pooled_allocations(
    calibration_components: Mapping[str, VarianceComponents],
    system_costs: Mapping[str, CostModel],
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
) -> tuple[AllocationRule, dict[str, Allocation]]:
    """Select one cross-system rule and map it to all systems' measured costs."""
    if not system_costs:
        raise ValueError("at least one target system cost is required")
    rule = select_pooled_rule(
        calibration_components,
        system_costs,
        budget,
        max_templates,
        max_generations,
        max_states,
    )
    return rule, {name: rule.apply(cost) for name, cost in system_costs.items()}


def leave_one_system_out_rule(
    calibration_components: Mapping[str, VarianceComponents],
    calibration_costs: Mapping[str, CostModel],
    held_out: str,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
) -> AllocationRule:
    """Build a new-system rule without using the held-out system's calibration."""
    if held_out not in calibration_components:
        raise KeyError(f"unknown held-out system: {held_out}")
    remaining_components = {
        name: component for name, component in calibration_components.items() if name != held_out
    }
    remaining_costs = {name: cost for name, cost in calibration_costs.items() if name != held_out}
    if not remaining_components or not remaining_costs:
        raise ValueError("leave-one-system-out requires at least one other system")
    return select_pooled_rule(
        remaining_components,
        remaining_costs,
        budget,
        max_templates,
        max_generations,
        max_states,
    )


def leave_one_system_out_allocations(
    calibration_components: Mapping[str, VarianceComponents],
    calibration_costs: Mapping[str, CostModel],
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
) -> dict[str, Allocation]:
    """Return target-cost mappings for every leave-one-system-out experiment."""
    if set(calibration_components) != set(calibration_costs):
        raise ValueError("component and cost mappings must name the same systems")
    allocations: dict[str, Allocation] = {}
    for system, target_cost in calibration_costs.items():
        rule = leave_one_system_out_rule(
            calibration_components,
            calibration_costs,
            system,
            budget,
            max_templates,
            max_generations,
            max_states,
        )
        allocations[system] = rule.apply(target_cost)
    return allocations


def shrink_components(
    pilot: VarianceComponents, pooled: VarianceComponents, pilot_weight: float
) -> VarianceComponents:
    """Componentwise pilot-to-pooled shrinkage, with one common CV weight."""
    pilot_weight = float(pilot_weight)
    if not isfinite(pilot_weight) or not 0 <= pilot_weight <= 1:
        raise ValueError("pilot_weight must be in [0, 1]")
    return VarianceComponents(
        template=pilot_weight * pilot.template + (1 - pilot_weight) * pooled.template,
        generation=pilot_weight * pilot.generation + (1 - pilot_weight) * pooled.generation,
        edit=pilot_weight * pilot.edit + (1 - pilot_weight) * pooled.edit,
    )


def select_pilot_shrinkage_weight(
    folds: Iterable[tuple[VarianceComponents, VarianceComponents]],
    pooled: VarianceComponents,
    candidates: Iterable[float] | None = None,
) -> float:
    """Select a pilot weight by internal calibration cross-validation.

    Each fold is ``(pilot_estimate, held_out_estimate)``.  Squared error is
    averaged over the three variance components, matching the paper's stated
    use of internal calibration data instead of test templates.
    """
    observations = list(folds)
    if not observations:
        raise ValueError("at least one internal calibration fold is required")
    weights = list(candidates) if candidates is not None else [index / 20 for index in range(21)]
    if not weights:
        raise ValueError("at least one shrinkage candidate is required")
    scored: list[tuple[float, float]] = []
    for weight in weights:
        shrunk_errors: list[float] = []
        for pilot, held_out in observations:
            shrunk = shrink_components(pilot, pooled, float(weight))
            shrunk_errors.extend(
                (
                    (shrunk.template - held_out.template) ** 2,
                    (shrunk.generation - held_out.generation) ** 2,
                    (shrunk.edit - held_out.edit) ** 2,
                )
            )
        scored.append((mean(shrunk_errors), float(weight)))
    return min(scored, key=lambda item: (item[0], item[1]))[1]


def small_pilot_allocation(
    pilot: VarianceComponents,
    pooled: VarianceComponents,
    pilot_weight: float,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
) -> Allocation:
    """Allocate formal evaluation from a small-pilot shrinkage estimate.

    Pilot execution cost is deliberately not deducted here.  It should be
    reported separately and assessed with :func:`calibration_break_even_rounds`.
    """
    return optimized_allocation(
        shrink_components(pilot, pooled, pilot_weight),
        cost,
        budget,
        max_templates,
        max_generations,
        max_states,
    )


def _normalized_weights(
    edit_variances: Mapping[str, float], weights: Mapping[str, float] | None = None
) -> dict[str, float]:
    edit_types = tuple(edit_variances)
    if not edit_types:
        raise ValueError("at least one edit stratum is required")
    if weights is None:
        return {kind: 1.0 / len(edit_types) for kind in edit_types}
    if set(weights) != set(edit_types):
        raise ValueError("stratum weights must match edit variance keys")
    result = {kind: _finite_nonnegative(weights[kind], f"weight for {kind}") for kind in edit_types}
    total = sum(result.values())
    if total <= 0:
        raise ValueError("stratum weights must sum to a positive value")
    return {kind: value / total for kind, value in result.items()}


@dataclass(frozen=True)
class StratifiedVarianceComponents:
    """Three-level components with one within-program component per edit type."""

    template: float
    generation: float
    edit: Mapping[str, float]
    weights: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        template = _finite_nonnegative(self.template, "template variance")
        generation = _finite_nonnegative(self.generation, "generation variance")
        edit = {str(kind): _finite_nonnegative(value, f"edit variance for {kind}") for kind, value in self.edit.items()}
        normal_weights = _normalized_weights(edit, self.weights)
        object.__setattr__(self, "template", template)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "edit", edit)
        object.__setattr__(self, "weights", normal_weights)


@dataclass(frozen=True)
class StratifiedAllocation:
    q: int
    g: int
    k_by_type: Mapping[str, int]
    cost: float
    variance: float

    @property
    def k(self) -> int:
        """Total state audits per program across all strata."""
        return sum(self.k_by_type.values())


def _program_groups(records: Iterable[AuditRecord]) -> dict[tuple[str, str, int], list[AuditRecord]]:
    groups: dict[tuple[str, str, int], list[AuditRecord]] = {}
    for record in records:
        groups.setdefault((record.system_id, record.template_id, record.generation_id), []).append(record)
    if not groups:
        raise ValueError("no audit records")
    return groups


def estimate_stratified_variance_components(
    records: Iterable[AuditRecord],
    *,
    weights: Mapping[str, float] | None = None,
    edit_types: Sequence[str] = EDIT_TYPES,
) -> StratifiedVarianceComponents:
    """Estimate the paper's four-class edit-state variance components.

    Every included program must contain at least one observed record for every
    requested type.  Complete 16-state calibration data are preferred, because
    state-level variance from sparse samples is inherently less stable.
    """
    kinds = tuple(edit_types)
    if not kinds or len(set(kinds)) != len(kinds):
        raise ValueError("edit_types must be non-empty and unique")
    requested_weights = {kind: 1.0 / len(kinds) for kind in kinds} if weights is None else dict(weights)
    if set(requested_weights) != set(kinds):
        raise ValueError("weights must name exactly the requested edit types")
    normal_weights = _normalized_weights({kind: 0.0 for kind in kinds}, requested_weights)

    template_program_means: dict[str, list[float]] = {}
    within_type_variances: dict[str, list[float]] = {kind: [] for kind in kinds}
    for (_, template_id, _), program in _program_groups(records).items():
        by_type: dict[str, list[float]] = {kind: [] for kind in kinds}
        for record in program:
            if record.edit_type in by_type:
                by_type[record.edit_type].append(float(record.failed))
        missing = [kind for kind, values in by_type.items() if not values]
        if missing:
            raise ValueError(f"program {template_id!r} lacks edit strata: {', '.join(missing)}")
        program_mean = sum(normal_weights[kind] * mean(by_type[kind]) for kind in kinds)
        template_program_means.setdefault(template_id, []).append(program_mean)
        for kind in kinds:
            within_type_variances[kind].append(_sample_variance(by_type[kind]))

    template_means = [mean(program_means) for program_means in template_program_means.values()]
    raw_generation = {template_id: _sample_variance(program_means) for template_id, program_means in template_program_means.items()}
    generation = mean(raw_generation.values())
    lower_level_noise = mean(
        raw_generation[template_id] / len(program_means)
        for template_id, program_means in template_program_means.items()
    )
    template = max(0.0, _sample_variance(template_means) - lower_level_noise)
    return StratifiedVarianceComponents(
        template=template,
        generation=generation,
        edit={kind: mean(values) for kind, values in within_type_variances.items()},
        weights=normal_weights,
    )


def stratified_risk(
    records: Iterable[AuditRecord],
    *,
    weights: Mapping[str, float] | None = None,
    edit_types: Sequence[str] = EDIT_TYPES,
) -> float:
    """Estimate risk with equal (or supplied) weights over edit-type means."""
    kinds = tuple(edit_types)
    if not kinds:
        raise ValueError("at least one edit type is required")
    use_weights = _normalized_weights(
        {kind: 0.0 for kind in kinds},
        {kind: 1.0 / len(kinds) for kind in kinds} if weights is None else weights,
    )
    values: list[float] = []
    for _, program in _program_groups(records).items():
        by_type: dict[str, list[float]] = {kind: [] for kind in kinds}
        for record in program:
            if record.edit_type in by_type:
                by_type[record.edit_type].append(float(record.failed))
        if any(not observations for observations in by_type.values()):
            raise ValueError("every program needs an observation from each requested stratum")
        values.append(sum(use_weights[kind] * mean(by_type[kind]) for kind in kinds))
    return mean(values)


def stratified_variance(
    components: StratifiedVarianceComponents,
    q: int,
    g: int,
    k_by_type: Mapping[str, int],
    m_by_type: Mapping[str, int],
    *,
    reference_templates: int | None = None,
    reference_generations: int | None = None,
) -> float:
    """Variance for a weighted finite edit-state stratum design.

    The edit term is ``sum_h W_h^2 (1/k_h - 1/M_h) sigma_Eh^2 / (q*g)``.
    Supplying both reference sizes applies the template and generation finite
    population corrections from Equation (5).
    """
    _positive_int(q, "q")
    _positive_int(g, "g")
    if set(k_by_type) != set(components.edit) or set(m_by_type) != set(components.edit):
        raise ValueError("stratum allocation and population sizes must match variance strata")
    if (reference_templates is None) != (reference_generations is None):
        raise ValueError("reference_templates and reference_generations are supplied together")
    if reference_templates is None:
        score = components.template / q + components.generation / (q * g)
    else:
        _positive_int(reference_templates, "reference_templates")
        _positive_int(reference_generations, "reference_generations")
        if q > reference_templates or g > reference_generations:
            raise ValueError("sample size exceeds finite reference pool")
        score = (1 / q - 1 / reference_templates) * components.template
        score += (1 / q) * (1 / g - 1 / reference_generations) * components.generation
    for kind, edit_variance in components.edit.items():
        k = _positive_int(k_by_type[kind], f"k for {kind}")
        m = _positive_int(m_by_type[kind], f"M for {kind}")
        if k > m:
            raise ValueError(f"k for {kind} exceeds its finite edit population")
        score += components.weights[kind] ** 2 * (1 / k - 1 / m) * edit_variance / (q * g)
    return score


def optimize_stratified_allocation(
    components: StratifiedVarianceComponents,
    cost: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    m_by_type: Mapping[str, int],
    *,
    minimum_per_type: int = 1,
    finite_reference: bool = True,
) -> StratifiedAllocation:
    """Integer search over ``q, g, (k_h)`` with every edit type represented."""
    _positive_int(max_templates, "max_templates")
    _positive_int(max_generations, "max_generations")
    _positive_int(minimum_per_type, "minimum_per_type")
    budget = _finite_nonnegative(budget, "budget")
    if set(m_by_type) != set(components.edit):
        raise ValueError("m_by_type must match the component edit strata")
    ordered_types = tuple(components.edit)
    populations = {kind: _positive_int(m_by_type[kind], f"M for {kind}") for kind in ordered_types}
    if any(minimum_per_type > population for population in populations.values()):
        raise ValueError("minimum_per_type exceeds a stratum population")

    best: StratifiedAllocation | None = None
    ranges = [range(minimum_per_type, populations[kind] + 1) for kind in ordered_types]
    for counts in product(*ranges):
        k_by_type = dict(zip(ordered_types, counts))
        total_k = sum(counts)
        for g in range(1, max_generations + 1):
            per_template = cost.template + g * (cost.generation + total_k * cost.edit)
            if per_template <= 0:
                raise ValueError("a sampled template must have positive cost")
            q = min(max_templates, int(budget // per_template))
            if q < 1:
                continue
            variance = stratified_variance(
                components,
                q,
                g,
                k_by_type,
                populations,
                reference_templates=max_templates if finite_reference else None,
                reference_generations=max_generations if finite_reference else None,
            )
            candidate = StratifiedAllocation(
                q=q,
                g=g,
                k_by_type=k_by_type,
                cost=cost.template * q + q * g * (cost.generation + total_k * cost.edit),
                variance=variance,
            )
            if best is None or (
                candidate.variance,
                -candidate.q,
                candidate.cost,
                candidate.g,
                tuple(candidate.k_by_type.values()),
            ) < (
                best.variance,
                -best.q,
                best.cost,
                best.g,
                tuple(best.k_by_type.values()),
            ):
                best = candidate
    if best is None:
        raise ValueError("budget does not buy one stratified template-generation package")
    return best


def stratified_state_sample(
    records: Iterable[AuditRecord],
    k_by_type: Mapping[str, int],
    seed: int = 20270901,
) -> dict[tuple[str, str, int], tuple[str, ...]]:
    """Sample observed frozen states without replacement inside every edit class."""
    groups = _program_groups(records)
    rng = __import__("random").Random(seed)
    selected: dict[tuple[str, str, int], tuple[str, ...]] = {}
    for key, program in groups.items():
        by_type: dict[str, list[AuditRecord]] = {kind: [] for kind in k_by_type}
        for record in program:
            if record.edit_type in by_type:
                by_type[record.edit_type].append(record)
        state_ids: list[str] = []
        for kind, requested in k_by_type.items():
            requested = _positive_int(requested, f"k for {kind}")
            if requested > len(by_type[kind]):
                raise ValueError(f"program {key} has too few observed {kind} states")
            state_ids.extend(record.state_id for record in rng.sample(by_type[kind], requested))
        selected[key] = tuple(state_ids)
    return selected


@dataclass(frozen=True)
class PairedObservation:
    """One exact A-minus-B difference at a shared frozen state."""

    template_id: str
    generation_id: int
    state_id: str
    edit_type: str
    difference: float


def _index_paired_records(records: Iterable[AuditRecord]) -> dict[tuple[str, int, str], AuditRecord]:
    indexed: dict[tuple[str, int, str], AuditRecord] = {}
    for record in records:
        key = (record.template_id, record.generation_id, record.state_id)
        if key in indexed:
            raise ValueError(f"duplicate paired audit key: {key}")
        indexed[key] = record
    if not indexed:
        raise ValueError("paired comparison needs audit records")
    return indexed


def paired_observations(
    records_a: Iterable[AuditRecord], records_b: Iterable[AuditRecord]
) -> tuple[PairedObservation, ...]:
    """Build strict matched A-minus-B observations for the same T/I/E keys."""
    left = _index_paired_records(records_a)
    right = _index_paired_records(records_b)
    if left.keys() != right.keys():
        missing_from_a = sorted(right.keys() - left.keys())
        missing_from_b = sorted(left.keys() - right.keys())
        raise ValueError(
            "paired pools must have identical keys "
            f"(missing from A: {missing_from_a[:3]}, missing from B: {missing_from_b[:3]})"
        )
    observations: list[PairedObservation] = []
    for key in sorted(left):
        first, second = left[key], right[key]
        if first.edit_type != second.edit_type:
            raise ValueError(f"paired state {key} has different edit types")
        observations.append(
            PairedObservation(
                template_id=first.template_id,
                generation_id=first.generation_id,
                state_id=first.state_id,
                edit_type=first.edit_type,
                difference=float(int(first.failed) - int(second.failed)),
            )
        )
    return tuple(observations)


def _estimate_numeric_components(observations: Iterable[PairedObservation]) -> VarianceComponents:
    by_template: dict[str, dict[int, list[float]]] = {}
    for observation in observations:
        by_template.setdefault(observation.template_id, {}).setdefault(observation.generation_id, []).append(
            observation.difference
        )
    if not by_template:
        raise ValueError("cannot estimate components from an empty comparison")
    program_means: dict[str, list[float]] = {}
    edit_variances: list[float] = []
    for template_id, generations in by_template.items():
        program_means[template_id] = []
        for differences in generations.values():
            program_means[template_id].append(mean(differences))
            edit_variances.append(_sample_variance(differences))
    template_means = [mean(values) for values in program_means.values()]
    raw_generation = {template_id: _sample_variance(values) for template_id, values in program_means.items()}
    template_noise = mean(
        raw_generation[template_id] / len(values)
        for template_id, values in program_means.items()
    )
    return VarianceComponents(
        template=max(0.0, _sample_variance(template_means) - template_noise),
        generation=mean(raw_generation.values()),
        edit=mean(edit_variances),
    )


def paired_variance_components(
    records_a: Iterable[AuditRecord], records_b: Iterable[AuditRecord]
) -> VarianceComponents:
    """Estimate the three components of ``Z = Y(A) - Y(B)``."""
    return _estimate_numeric_components(paired_observations(records_a, records_b))


def paired_risk_difference(records_a: Iterable[AuditRecord], records_b: Iterable[AuditRecord]) -> float:
    """Estimate the mean risk difference ``R_A - R_B`` on matched evidence."""
    observations = paired_observations(records_a, records_b)
    return mean(observation.difference for observation in observations)


def paired_cost_model(
    cost_a: CostModel, cost_b: CostModel, *, template_cost: float | None = None
) -> CostModel:
    """Combine two systems' costs for a paired comparison.

    Template preparation is shared.  If no shared value is supplied, the larger
    system-specific preparation estimate is conservative; generation and edit
    execution are incurred for both systems.
    """
    shared_template = max(cost_a.template, cost_b.template) if template_cost is None else template_cost
    return CostModel(
        template=shared_template,
        generation=cost_a.generation + cost_b.generation,
        edit=cost_a.edit + cost_b.edit,
    )


def paired_allocation(
    records_a: Iterable[AuditRecord],
    records_b: Iterable[AuditRecord],
    cost_a: CostModel,
    cost_b: CostModel,
    budget: float,
    max_templates: int,
    max_generations: int,
    max_states: int,
    *,
    template_cost: float | None = None,
) -> Allocation:
    """Choose an integer allocation from matched A/B variance and paired cost."""
    return optimized_allocation(
        paired_variance_components(records_a, records_b),
        paired_cost_model(cost_a, cost_b, template_cost=template_cost),
        budget,
        max_templates,
        max_generations,
        max_states,
    )


def _validated_p_values(p_values: Mapping[str, float]) -> list[tuple[str, float]]:
    ordered: list[tuple[str, float]] = []
    for name, value in p_values.items():
        value = float(value)
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"p-value for {name!r} must be finite and in [0, 1]")
        ordered.append((name, value))
    return sorted(ordered, key=lambda item: (item[1], item[0]))


def holm_adjusted_pvalues(p_values: Mapping[str, float]) -> dict[str, float]:
    """Compute Holm step-down adjusted p-values for the model-pair family."""
    ordered = _validated_p_values(p_values)
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, (count - rank) * value))
        adjusted[name] = running
    return adjusted


def holm_rejections(p_values: Mapping[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Return Holm sequential test decisions at a family-wise error level."""
    alpha = float(alpha)
    if not isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    ordered = _validated_p_values(p_values)
    count = len(ordered)
    rejected: dict[str, bool] = {name: False for name, _ in ordered}
    for rank, (name, value) in enumerate(ordered):
        if value <= alpha / (count - rank):
            rejected[name] = True
        else:
            break
    return rejected


def calibration_break_even_rounds(
    pilot_cost: float,
    formal_budget: float,
    j_global: float,
    j_pilot: float,
) -> float:
    """Return the continuous approximate pilot break-even count from Equation (9).

    ``inf`` means the pilot allocation has no formal-evaluation efficiency gain
    and therefore cannot recover its separately reported calibration cost.
    """
    pilot_cost = _finite_nonnegative(pilot_cost, "pilot_cost")
    formal_budget = _finite_nonnegative(formal_budget, "formal_budget")
    j_global = _finite_nonnegative(j_global, "j_global")
    j_pilot = _finite_nonnegative(j_pilot, "j_pilot")
    if formal_budget == 0:
        raise ValueError("formal_budget must be positive")
    if j_pilot >= j_global or j_global == 0:
        return inf
    return pilot_cost / (formal_budget * (1 - j_pilot / j_global))


break_even_rounds = calibration_break_even_rounds

