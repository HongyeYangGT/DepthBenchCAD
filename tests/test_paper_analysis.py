import unittest

from depthbenchcad.paper_analysis import (
    benefit_direction_report,
    choose_component_rule,
    cohen_kappa,
    regret_summary,
)
from depthbenchcad.strategies import CostModel
from depthbenchcad.variance import VarianceComponents


class PaperAnalysisTests(unittest.TestCase):
    def test_component_rule_respects_budget_and_depth(self):
        allocation = choose_component_rule(
            VarianceComponents(0.03, 0.02, 0.15), CostModel(2, 8, 1),
            1024, 48, 5, 16, allowed_k=(4, 8, 16),
        )
        self.assertLessEqual(allocation.cost, 1024)
        self.assertIn(allocation.k, {4, 8, 16})

    def test_benefit_direction_loss_is_zero_when_prediction_is_correct(self):
        report = {
            "S1": {
                4: {"predicted_J": 0.2, "J": 0.3},
                8: {"predicted_J": 0.1, "J": 0.2},
            }
        }
        out = benefit_direction_report(report, ((4, 8),))
        self.assertEqual(out["correct"], 1)
        self.assertEqual(out["comparisons"]["S1"]["k4_to_k8"]["recommendation_loss"], 0)

    def test_regret_summary_and_kappa(self):
        out = regret_summary([1.0, 1.02, 1.08, 1.20])
        self.assertAlmostEqual(out["robust_coverage_5pct"], 0.5)
        self.assertAlmostEqual(cohen_kappa([True, False, True, False], [True, False, True, False]), 1.0)


if __name__ == "__main__":
    unittest.main()
