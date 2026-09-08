"""Challenge-quality tests: legality, diversity, split integrity, and anti-no-op rules."""

import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from depthbenchcad.catalog import build_catalog
from depthbenchcad.challenge import constraint_margins, normalized_distance, safety_margin


class ChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="depthbenchcad-challenge-")
        cls.templates = build_catalog(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_1920_states_are_unique_legal_and_substantial(self):
        for template in self.templates:
            vectors = {tuple(sorted(state.parameters.items())) for state in template.states}
            self.assertEqual(len(vectors), 16, template.template_id)
            self.assertEqual(Counter(s.edit_type for s in template.states), {"local": 4, "boundary": 4, "linked": 4, "semantic": 4})
            for state in template.states:
                distance = normalized_distance(state.parameters, template.parameters, template.parameter_ranges)
                self.assertGreaterEqual(distance, 0.10, state.state_id)
                for name, value in constraint_margins(template.task_family, state.parameters).items():
                    required = 0.25 if "count_min" in name else safety_margin(state.parameters)
                    self.assertGreater(value, required, (state.state_id, name, value, required))

    def test_boundary_states_approach_real_engineering_constraints(self):
        for template in self.templates:
            boundary = [s for s in template.states if s.edit_type == "boundary"]
            self.assertEqual(len(boundary), 4)
            for state in boundary:
                rel = state.expected_relations
                self.assertTrue(rel.get("active_constraint"), state.state_id)
                scale = max(v for k, v in state.parameters.items() if k not in {"rib_count", "teeth", "knuckle_count", "bar_count"})
                normalized_margin = float(rel["engineering_margin"]) / scale
                self.assertLessEqual(normalized_margin, 0.05, state.state_id)

    def test_semantic_states_require_multi_parameter_dependency_closure(self):
        for template in self.templates:
            for state in [s for s in template.states if s.edit_type == "semantic"]:
                changed = state.expected_relations.get("dependency_closure", [])
                self.assertGreaterEqual(len(changed), 2, state.state_id)
                self.assertTrue(state.expected_relations.get("semantic_contract"), state.state_id)

    def test_variants_are_not_uniform_scale_copies(self):
        by_family = defaultdict(list)
        for template in self.templates:
            by_family[template.task_family].append(template)
        for family, templates in by_family.items():
            # Compare normalized ratios against each family's first template.
            keys = list(templates[0].parameters)
            base = templates[0].parameters
            ratio_signatures = set()
            for t in templates:
                ratios = []
                for key in keys:
                    if key in {"rib_count", "teeth", "knuckle_count", "bar_count"}:
                        continue
                    ratios.append(round(t.parameters[key] / base[key], 3))
                # A uniform scale copy would have every ratio equal.
                ratio_signatures.add(len(set(ratios)))
            self.assertTrue(any(n > 1 for n in ratio_signatures), family)

    def test_calibration_split_is_not_variant_prefix(self):
        by_family = defaultdict(list)
        for template in self.templates:
            by_family[template.task_family].append(template)
        for family, templates in by_family.items():
            calibration = sorted(int(t.template_id.rsplit("-", 1)[1]) for t in templates if t.constraints["split"] == "calibration")
            prefix = list(range(1, len(calibration) + 1))
            self.assertNotEqual(calibration, prefix, family)


if __name__ == "__main__":
    unittest.main()
