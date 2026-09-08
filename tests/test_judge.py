"""Automatic-judge tests for the ordered Section 4.2 checks."""

import unittest

from depthbenchcad.judge import judge_geometry
from depthbenchcad.schema import EditState, Template


def _flange() -> Template:
    params = {
        "outer_diameter": 80.0,
        "thickness": 10.0,
        "bore_diameter": 28.0,
        "bolt_circle": 58.0,
        "bolt_diameter": 7.0,
    }
    state = EditState(
        "f-local-1", "local", dict(params),
        expected_relations={"must_respond": True, "metric_responses": [{"metric": "volume", "direction": "increase", "minimum_relative_delta": 0.001}]},
        tolerance={"length_mm": 0.05, "relative_volume": 0.005, "angle_deg": 0.1},
    )
    return Template(
        "f", "flange_plate", "fixture", params,
        {k: (0.1, 200.0) for k in params},
        {
            "connected_components": 1,
            "topology": {"min_faces": 8, "min_edges": 16},
            "metric_tolerance": {"length_mm": 0.05, "relative_volume": 0.005, "angle_deg": 0.1},
        },
        (state,),
    )


def _metrics() -> dict:
    circles = [
        {"radius": 14.0, "center_x": 0.0, "center_y": 0.0, "center_z": 0.0, "axis": "z"},
        {"radius": 3.5, "center_x": 29.0, "center_y": 0.0, "center_z": 0.0, "axis": "z"},
        {"radius": 3.5, "center_x": 0.0, "center_y": 29.0, "center_z": 0.0, "axis": "z"},
        {"radius": 3.5, "center_x": -29.0, "center_y": 0.0, "center_z": 0.0, "axis": "z"},
        {"radius": 3.5, "center_x": 0.0, "center_y": -29.0, "center_z": 0.0, "axis": "z"},
    ]
    return {
        "is_valid": True,
        "volume": 1000.0,
        "solid_count": 1,
        "face_count": 8,
        "edge_count": 18,
        "bbox_x": 80.0,
        "bbox_y": 80.0,
        "bbox_z": 10.0,
        "center_x": 0.0,
        "center_y": 0.0,
        "center_z": 5.0,
        "geometry_signature": "abc",
        "circle_edges": circles,
    }


class JudgeTests(unittest.TestCase):
    def test_nominal_geometry_passes_all_six_groups(self):
        decision = judge_geometry(_flange(), None, _metrics())
        self.assertEqual(decision.status, "pass")
        self.assertIsNone(decision.failure_stage)

    def test_missing_hole_fails_topology(self):
        metrics = _metrics()
        metrics["circle_edges"] = metrics["circle_edges"][:-1]
        decision = judge_geometry(_flange(), None, metrics)
        self.assertEqual(decision.status, "fail")
        self.assertEqual(decision.failure_stage, "topology")

    def test_tolerance_boundary_routes_to_review(self):
        metrics = _metrics()
        # For Lref=80 mm the paper tolerance is max(0.05, 0.001*80)=0.08 mm.
        metrics["bbox_x"] = 80.08
        decision = judge_geometry(_flange(), None, metrics)
        self.assertEqual(decision.status, "review")
        self.assertEqual(decision.failure_stage, "gray_zone_review")

    def test_no_parameter_response_is_failure(self):
        template = _flange()
        state = template.states[0]
        observed = _metrics()
        baseline = dict(observed)
        decision = judge_geometry(template, state, observed, baseline=baseline)
        self.assertEqual(decision.status, "fail")
        self.assertEqual(decision.failure_stage, "parameter_response")


if __name__ == "__main__":
    unittest.main()
