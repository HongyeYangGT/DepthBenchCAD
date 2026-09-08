"""Tests for the distinction between model and infrastructure failures."""

import unittest

from depthbenchcad.executor import audit_generation
from depthbenchcad.schema import EditState, GenerationRecord, Template


def _template() -> Template:
    state = EditState("t-local-1", "local", {"length": 1.0})
    return Template(
        template_id="t",
        task_family="fixture",
        description="fixture",
        parameters={"length": 1.0},
        parameter_ranges={"length": (0.5, 2.0)},
        constraints={},
        states=(state,),
    )


class ExecutorTests(unittest.TestCase):
    def test_environment_failure_is_not_a_model_label(self):
        template = _template()
        generation = GenerationRecord(
            system_id="S1",
            template_id="t",
            generation_id=0,
            seed=1,
            program="missing.py",
            initial_valid=False,
            failure_stage="environment",
        )
        record = audit_generation(template, generation, template.states[0])
        self.assertIsNone(record.failed)
        self.assertFalse(record.automatic_label)
        self.assertEqual(record.failure_stage, "environment")

    def test_invalid_model_program_counts_as_failure(self):
        template = _template()
        generation = GenerationRecord(
            system_id="S1",
            template_id="t",
            generation_id=0,
            seed=1,
            program="broken.py",
            initial_valid=False,
            failure_stage="build",
        )
        record = audit_generation(template, generation, template.states[0])
        self.assertTrue(record.failed)
        self.assertEqual(record.failure_stage, "initial_build")


if __name__ == "__main__":
    unittest.main()
