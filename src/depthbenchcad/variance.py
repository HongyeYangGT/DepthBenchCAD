"""Three-level variance estimates from the paper's sampling model."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Iterable

from .schema import AuditRecord


@dataclass(frozen=True)
class VarianceComponents:
    template: float
    generation: float
    edit: float


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return sum((x - m) ** 2 for x in values) / (len(values) - 1)


def estimate_variance_components(records: Iterable[AuditRecord], full_state_count: int | None = None) -> VarianceComponents:
    """Estimate ``sigma_T^2``, ``sigma_G^2`` and ``sigma_E^2`` by method of moments.

    The benchmark is a nested template -> generation -> edit design.  A raw
    variance of template means contains residual generation noise, and a raw
    variance of generation means can contain edit-subsampling noise.  The
    estimator therefore removes those lower-level contributions before using
    the components in Equations (4) and (5).

    Complete 16-state calibration records are the intended input.  When
    ``full_state_count`` is supplied for a partial state sample, the finite-state
    measurement contribution ``(1/k - 1/M) S_E^2`` is also removed from the
    generation component.  Negative method-of-moments residuals are truncated
    at zero, the standard non-negative variance-component convention used by
    this executable protocol.
    """
    if full_state_count is not None and (
        not isinstance(full_state_count, int) or isinstance(full_state_count, bool) or full_state_count < 1
    ):
        raise ValueError("full_state_count must be a positive integer")

    by_template: dict[str, dict[int, list[int]]] = {}
    for r in records:
        if r.failed is None:
            raise ValueError("variance estimation requires observed failed labels")
        by_template.setdefault(r.template_id, {}).setdefault(r.generation_id, []).append(int(r.failed))
    if not by_template:
        raise ValueError("cannot estimate variance from an empty record set")

    program_means_by_template: dict[str, list[float]] = {}
    raw_generation_variance_by_template: dict[str, float] = {}
    edit_noise_by_template: dict[str, float] = {}
    edit_vars: list[float] = []

    for template_id, generations in by_template.items():
        means: list[float] = []
        per_program_edit_noise: list[float] = []
        for failures in generations.values():
            values = [float(x) for x in failures]
            means.append(mean(values))
            edit_var = _sample_variance(values)
            edit_vars.append(edit_var)
            M = full_state_count if full_state_count is not None else len(values)
            if len(values) > M:
                raise ValueError("observed state count cannot exceed full_state_count")
            per_program_edit_noise.append((1 / len(values) - 1 / M) * edit_var)
        program_means_by_template[template_id] = means
        raw_generation_variance_by_template[template_id] = _sample_variance(means)
        edit_noise_by_template[template_id] = mean(per_program_edit_noise)

    edit_component = mean(edit_vars) if edit_vars else 0.0
    generation_components = [
        max(0.0, raw_generation_variance_by_template[t] - edit_noise_by_template[t])
        for t in program_means_by_template
    ]
    generation_component = mean(generation_components)

    template_means = [mean(values) for values in program_means_by_template.values()]
    raw_template_variance = _sample_variance(template_means)
    template_lower_level_noise = mean(
        raw_generation_variance_by_template[t] / len(program_means_by_template[t])
        for t in program_means_by_template
    )
    template_component = max(0.0, raw_template_variance - template_lower_level_noise)

    for component in (template_component, generation_component, edit_component):
        if not isfinite(component) or component < 0:
            raise ValueError("variance estimate is not finite and non-negative")
    return VarianceComponents(template_component, generation_component, edit_component)



def estimate_finite_variance_components(
    records: Iterable[AuditRecord],
    *,
    full_generations: int | None = None,
    full_states: int | None = None,
) -> VarianceComponents:
    """Estimate the finite reference-pool components used by Equation (5).

    With a complete pool this returns the direct finite-population quantities:
    variance of full template means, mean within-template variance of full
    program means, and mean within-program state variance.  With a partial
    nested sample it removes the known generation/state sampling contribution
    so the same components can be estimated during coverage replays.
    """
    if full_generations is not None and (
        not isinstance(full_generations, int) or isinstance(full_generations, bool) or full_generations < 1
    ):
        raise ValueError("full_generations must be a positive integer")
    if full_states is not None and (
        not isinstance(full_states, int) or isinstance(full_states, bool) or full_states < 1
    ):
        raise ValueError("full_states must be a positive integer")

    by_template: dict[str, dict[int, list[int]]] = {}
    for r in records:
        if r.failed is None:
            raise ValueError("variance estimation requires observed failed labels")
        by_template.setdefault(r.template_id, {}).setdefault(r.generation_id, []).append(int(r.failed))
    if not by_template:
        raise ValueError("cannot estimate variance from an empty record set")

    template_means: list[float] = []
    generation_components: list[float] = []
    template_measurement_noise: list[float] = []
    edit_vars: list[float] = []

    for generations in by_template.values():
        program_means: list[float] = []
        edit_noises: list[float] = []
        for failures in generations.values():
            values = [float(x) for x in failures]
            k = len(values)
            M = full_states if full_states is not None else k
            if k > M:
                raise ValueError("observed state count cannot exceed full_states")
            evar = _sample_variance(values)
            edit_vars.append(evar)
            program_means.append(mean(values))
            edit_noises.append((1 / k - 1 / M) * evar)

        g = len(program_means)
        G = full_generations if full_generations is not None else g
        if g > G:
            raise ValueError("observed generation count cannot exceed full_generations")
        raw_generation = _sample_variance(program_means)
        edit_noise = mean(edit_noises)
        generation_component = max(0.0, raw_generation - edit_noise)
        generation_components.append(generation_component)
        template_means.append(mean(program_means))
        template_measurement_noise.append(
            (1 / g - 1 / G) * generation_component + edit_noise / g
        )

    template_component = max(0.0, _sample_variance(template_means) - mean(template_measurement_noise))
    return VarianceComponents(
        template=template_component,
        generation=mean(generation_components),
        edit=mean(edit_vars),
    )

def superpopulation_variance(v: VarianceComponents, q: int, g: int, k: int, m: int) -> float:
    """Equation (4): Var(R-hat) for balanced three-level sampling."""
    for value, name in ((q, "q"), (g, "g"), (k, "k"), (m, "m")):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if k > m:
        raise ValueError("k cannot exceed the finite edit population M")
    return v.template / q + v.generation / (q * g) + (1 / q / g) * (1 / k - 1 / m) * v.edit


def finite_population_variance(
    v: VarianceComponents, q: int, g: int, k: int, m: int, Q: int, G: int
) -> float:
    """Equation (5): finite reference-pool variance."""
    for value, name in ((q, "q"), (g, "g"), (k, "k"), (m, "m"), (Q, "Q"), (G, "G")):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if Q < q or G < g:
        raise ValueError("sample sizes cannot exceed reference-pool sizes")
    if k > m:
        raise ValueError("k cannot exceed M")
    return (1 / q - 1 / Q) * v.template + (1 / q) * (1 / g - 1 / G) * v.generation + (1 / q / g) * (1 / k - 1 / m) * v.edit


def program_mse(full_failures: list[int], sampled_indices: list[int]) -> float:
    """MSE of a state subsample for one program, relative to all states."""
    if not full_failures or not sampled_indices:
        raise ValueError("full_failures and sampled_indices must be non-empty")
    if any(value not in (0, 1, False, True) for value in full_failures):
        raise ValueError("full_failures must contain binary labels")
    if len(set(sampled_indices)) != len(sampled_indices):
        raise ValueError("sampled_indices must not contain duplicates")
    if any(not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(full_failures) for index in sampled_indices):
        raise ValueError("sampled_indices must be valid indices")
    target = mean(full_failures)
    estimate = mean([full_failures[i] for i in sampled_indices])
    return (estimate - target) ** 2
