"""Contract tests for the complete DepthBenchCAD task corpus."""

import ast
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from depthbenchcad.audit import validate_parameters
from depthbenchcad.catalog import build_catalog, catalog_summary
from depthbenchcad.schema import EDIT_TYPES


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="depthbenchcad-catalog-test-")
        cls.root = Path(cls.temporary.name)
        cls.templates = build_catalog(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_paper_cardinalities_and_template_splits(self):
        self.assertEqual(
            catalog_summary(self.templates),
            {"templates": 120, "families": 14, "states": 1920},
        )
        environments = Counter(template.constraints["environment"] for template in self.templates)
        splits = Counter(
            (template.constraints["environment"], template.constraints["split"])
            for template in self.templates
        )
        self.assertEqual(environments, {"A": 72, "B": 48})
        self.assertEqual(
            splits,
            {("A", "calibration"): 24, ("A", "test"): 48,
             ("B", "calibration"): 12, ("B", "test"): 36},
        )

    def test_states_are_complete_legal_and_balanced(self):
        for template in self.templates:
            self.assertEqual(len(template.states), 16)
            self.assertEqual(Counter(state.edit_type for state in template.states), {kind: 4 for kind in EDIT_TYPES})
            for state in template.states:
                self.assertEqual(set(state.parameters), set(template.parameters))
                self.assertTrue(validate_parameters(state)[0])


    def test_linked_position_edits_use_structural_response(self):
        plate = next(template for template in self.templates if template.task_family == "bolt_pattern_plate")
        for state in [s for s in plate.states if s.edit_type == "linked"]:
            rules = state.expected_relations.get("metric_responses", [])
            self.assertEqual(rules, [{"metric": "geometry_signature", "direction": "change"}])

    def test_drawer_handle_range_is_not_conditioned_on_reference_geometry(self):
        handles = [template for template in self.templates if template.task_family == "drawer_handle"]
        self.assertTrue(handles)
        for template in handles:
            # The declared task range stays fixed across variants. Difficulty is
            # handled by legal frozen states, never by shrinking the range to
            # accommodate a reference implementation.
            self.assertEqual(template.parameter_ranges["span"], (78.0, 158.0))

    def test_every_reference_program_is_standalone_python(self):
        programs = sorted((self.root / "data" / "programs").glob("*.py"))
        self.assertEqual(len(programs), 120)
        for program in programs:
            tree = ast.parse(program.read_text(encoding="utf-8"), filename=str(program))
            self.assertTrue(
                any(isinstance(node, ast.FunctionDef) and node.name == "build" for node in tree.body),
                program.name,
            )


if __name__ == "__main__":
    unittest.main()
