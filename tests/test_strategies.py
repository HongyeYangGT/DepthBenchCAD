"""Focused standard-library tests for paper allocation strategies."""

from math import isinf
import unittest

from depthbenchcad.replay import FiniteAuditPool, finite_pool_replay
from depthbenchcad.schema import AuditRecord, EDIT_TYPES
from depthbenchcad.strategies import (
    CostModel,
    calibration_break_even_rounds,
    estimate_stratified_variance_components,
    fixed_depth_allocation,
    holm_adjusted_pvalues,
    holm_rejections,
    leave_one_system_out_allocations,
    leave_one_system_out_rule,
    optimize_stratified_allocation,
    paired_allocation,
    paired_observations,
    paired_risk_difference,
    paired_variance_components,
    pooled_allocations,
    select_pilot_shrinkage_weight,
    shrink_components,
    stratified_risk,
    stratified_state_sample,
    summarize_costs,
    trimmed_mean,
)
from depthbenchcad.variance import VarianceComponents


def _records(system_id="A"):
    records = []
    for template_index, template_id in enumerate(("t0", "t1", "t2")):
        for generation_id in range(2):
            for edit_index, edit_type in enumerate(EDIT_TYPES):
                for state_index in range(2):
                    records.append(
                        AuditRecord(
                            system_id=system_id,
                            template_id=template_id,
                            generation_id=generation_id,
                            state_id=f"{edit_type}-{state_index}",
                            edit_type=edit_type,
                            failed=bool((template_index + generation_id + edit_index + state_index) % 2),
                            initial_valid=True,
                        )
                    )
    return records


class StrategyTests(unittest.TestCase):
    def test_cost_summary_uses_symmetric_trim_and_standard_median(self):
        timings = list(range(1, 11))
        self.assertAlmostEqual(trimmed_mean(timings), 5.5)
        summary = summarize_costs(timings)
        self.assertAlmostEqual(summary.trimmed_mean_10pct, 5.5)
        self.assertAlmostEqual(summary.ordinary_mean, 5.5)
        self.assertAlmostEqual(summary.median, 5.5)
        with self.assertRaises(ValueError):
            trimmed_mean([1.0, float("inf")])

    def test_fixed_pooled_and_leave_one_out_rules_are_budget_feasible(self):
        components = {
            "A": VarianceComponents(0.2, 0.1, 0.08),
            "B": VarianceComponents(0.3, 0.07, 0.04),
            "C": VarianceComponents(0.1, 0.2, 0.12),
        }
        costs = {
            "A": CostModel(2, 1, 1),
            "B": CostModel(2, 3, 1),
            "C": CostModel(2, 8, 1),
        }
        fixed = fixed_depth_allocation(components["A"], 2, costs["A"], 100, 10, 4, 4)
        self.assertEqual(fixed.k, 2)
        self.assertLessEqual(fixed.cost, 100)

        rule, pooled = pooled_allocations(components, costs, 100, 10, 4, 4)
        self.assertEqual({result.g for result in pooled.values()}, {rule.g})
        self.assertEqual({result.k for result in pooled.values()}, {rule.k})
        self.assertTrue(all(result.cost <= 100 for result in pooled.values()))

        loso_rule = leave_one_system_out_rule(components, costs, "A", 100, 10, 4, 4)
        self.assertNotEqual(loso_rule.components, components["A"])
        loso = leave_one_system_out_allocations(components, costs, 100, 10, 4, 4)
        self.assertEqual(set(loso), set(components))
        self.assertTrue(all(result.cost <= 100 for result in loso.values()))

    def test_pilot_shrinkage_can_be_selected_without_test_records(self):
        pooled = VarianceComponents(0.2, 0.1, 0.05)
        pilot = VarianceComponents(0.8, 0.4, 0.2)
        shrunk = shrink_components(pilot, pooled, 0.25)
        self.assertAlmostEqual(shrunk.template, 0.35)
        folds = [(pilot, pooled), (VarianceComponents(0.7, 0.3, 0.1), pooled)]
        self.assertEqual(select_pilot_shrinkage_weight(folds, pooled, [0.0, 0.5, 1.0]), 0.0)

    def test_edit_type_stratification_covers_all_four_classes(self):
        records = _records()
        components = estimate_stratified_variance_components(records)
        self.assertEqual(set(components.edit), set(EDIT_TYPES))
        self.assertAlmostEqual(stratified_risk(records), 0.5)
        allocation = optimize_stratified_allocation(
            components,
            CostModel(2, 1, 1),
            250,
            3,
            2,
            {edit_type: 2 for edit_type in EDIT_TYPES},
        )
        self.assertLessEqual(allocation.cost, 250)
        self.assertEqual(set(allocation.k_by_type), set(EDIT_TYPES))
        self.assertTrue(all(count >= 1 for count in allocation.k_by_type.values()))
        selected = stratified_state_sample(records, {edit_type: 1 for edit_type in EDIT_TYPES})
        self.assertTrue(all(len(states) == 4 for states in selected.values()))

    def test_paired_variance_requires_exact_alignment_and_combines_costs(self):
        records_a = _records("A")
        records_b = [
            AuditRecord(
                system_id="B",
                template_id=record.template_id,
                generation_id=record.generation_id,
                state_id=record.state_id,
                edit_type=record.edit_type,
                failed=not record.failed,
                initial_valid=True,
            )
            for record in records_a
        ]
        observations = paired_observations(records_a, records_b)
        self.assertEqual(len(observations), len(records_a))
        self.assertAlmostEqual(paired_risk_difference(records_a, records_b), 0.0)
        components = paired_variance_components(records_a, records_b)
        self.assertGreaterEqual(components.edit, 0)
        allocation = paired_allocation(
            records_a,
            records_b,
            CostModel(2, 1, 1),
            CostModel(2, 3, 1),
            500,
            3,
            2,
            8,
        )
        self.assertLessEqual(allocation.cost, 500)
        with self.assertRaises(ValueError):
            paired_observations(records_a, records_b[:-1])

    def test_holm_and_break_even_follow_paper_rules(self):
        p_values = {"first": 0.01, "second": 0.03, "third": 0.04}
        adjusted = holm_adjusted_pvalues(p_values)
        self.assertAlmostEqual(adjusted["first"], 0.03)
        self.assertAlmostEqual(adjusted["second"], 0.06)
        self.assertAlmostEqual(adjusted["third"], 0.06)
        self.assertEqual(holm_rejections(p_values), {"first": True, "second": False, "third": False})
        self.assertAlmostEqual(calibration_break_even_rounds(200, 100, 2, 1), 4.0)
        self.assertTrue(isinf(calibration_break_even_rounds(200, 100, 1, 1)))

    def test_finite_pool_replay_only_resamples_complete_observed_records(self):
        records = _records()
        pool = FiniteAuditPool(records)
        self.assertEqual(pool.shape.templates, 3)
        self.assertEqual(pool.shape.generations_per_template, 2)
        self.assertEqual(pool.shape.states_per_program, 8)
        first = pool.draw(2, 1, 4, seed=8)
        second = pool.draw(2, 1, 4, seed=8)
        self.assertEqual(first, second)
        self.assertEqual(len(first.state_keys), 8)
        replay = pool.replay(2, 1, 4, repeats=25, seed=9)
        self.assertEqual(len(replay.estimates), 25)
        self.assertGreaterEqual(replay.mse, 0)
        self.assertGreaterEqual(pool.program_mse(4, repeats=20, seed=9), 0)
        self.assertGreaterEqual(pool.design_variance(2, 1, 4), 0)
        direct = finite_pool_replay(records, 2, 1, 4, repeats=4, seed=9)
        from_pool = pool.replay(2, 1, 4, repeats=4, seed=9)
        self.assertEqual(direct.estimates, from_pool.estimates)


if __name__ == "__main__":
    unittest.main()
