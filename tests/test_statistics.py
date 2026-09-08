from depthbenchcad.allocation import allocation_cost, optimize_allocation
from depthbenchcad.schema import AuditRecord
from depthbenchcad.variance import (
    VarianceComponents,
    estimate_finite_variance_components,
    estimate_variance_components,
    finite_population_variance,
    superpopulation_variance,
)


def records():
    out = []
    for template in ("t1", "t2", "t3"):
        for generation in (0, 1):
            for state in range(4):
                out.append(
                    AuditRecord(
                        system_id="S1",
                        template_id=template,
                        generation_id=generation,
                        state_id=f"{template}-{generation}-{state}",
                        edit_type="local",
                        failed=bool((state + generation + (template == "t3")) % 2),
                        initial_valid=True,
                    )
                )
    return out


def test_variance_components_are_nonnegative():
    v = estimate_variance_components(records())
    assert v.template >= 0
    assert v.generation >= 0
    assert v.edit >= 0


def test_finite_correction_is_no_larger_than_superpopulation():
    v = VarianceComponents(0.2, 0.1, 0.05)
    assert finite_population_variance(v, 2, 2, 2, 4, 3, 2) <= superpopulation_variance(v, 2, 2, 2, 4)


def test_integer_allocation_is_feasible():
    v = VarianceComponents(0.2, 0.1, 0.05)
    result = optimize_allocation(v, 100, 2, 1, 1, 10, 4, 4, 10, 4)
    assert result.q >= 1 and result.g >= 1 and result.k >= 1
    assert result.cost <= 100
    assert result.cost == allocation_cost(result.q, result.g, result.k, 2, 1, 1)


def test_complete_finite_components_use_full_template_means():
    rows = []
    # Two full generations per template; edit states are constant inside a program.
    patterns = {
        "t1": {0: 0, 1: 1},
        "t2": {0: 0, 1: 0},
        "t3": {0: 1, 1: 1},
    }
    for template, generations in patterns.items():
        for generation, label in generations.items():
            for state in range(4):
                rows.append(AuditRecord(
                    system_id="S", template_id=template, generation_id=generation,
                    state_id=f"{template}-{generation}-{state}", edit_type="local",
                    failed=bool(label), initial_valid=True,
                ))
    finite = estimate_finite_variance_components(rows)
    # Full template means are 0.5, 0.0, 1.0; their sample variance is 0.25.
    assert abs(finite.template - 0.25) < 1e-12
    assert finite.edit == 0.0


def test_partial_finite_component_estimator_accepts_known_full_sizes():
    subset = [r for r in records() if r.generation_id == 0 and r.state_id.endswith(("-0", "-1"))]
    v = estimate_finite_variance_components(subset, full_generations=2, full_states=4)
    assert v.template >= 0 and v.generation >= 0 and v.edit >= 0
