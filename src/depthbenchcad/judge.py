"""Automatic geometry judge implementing the paper's Section 4.2 protocol.

The judge is candidate-implementation agnostic: it consumes only frozen task
and edit-state specifications plus geometry probes emitted by the isolated CAD
worker. Numerical checks use the paper tolerances and route borderline values
to manual review instead of turning floating-point noise into a binary label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from .schema import EditState, Template


GRAY_LOW = 0.90
GRAY_HIGH = 1.10


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # pass | fail | review
    stage: str
    observed: Any = None
    expected: Any = None
    tolerance: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class JudgeDecision:
    status: str  # pass | fail | review
    failure_stage: str | None
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def failed(self) -> bool | None:
        if self.status == "pass":
            return False
        if self.status == "fail":
            return True
        return None


def _length_tolerance(expected: float, state: EditState | None, template: Template) -> float:
    source = state.tolerance if state is not None else dict(template.constraints.get("metric_tolerance", {}))
    absolute = float(source.get("length_mm", 0.05))
    return max(absolute, 0.001 * abs(float(expected)))


def _relative_volume_tolerance(state: EditState | None, template: Template) -> float:
    source = state.tolerance if state is not None else dict(template.constraints.get("metric_tolerance", {}))
    return float(source.get("relative_volume", 0.005))


def _angle_tolerance(state: EditState | None, template: Template) -> float:
    source = state.tolerance if state is not None else dict(template.constraints.get("metric_tolerance", {}))
    return float(source.get("angle_deg", 0.1))


def _numeric_check(name: str, stage: str, observed: float | None, expected: float, tolerance: float) -> CheckResult:
    if observed is None or not math.isfinite(float(observed)):
        return CheckResult(name, "fail", stage, observed, expected, tolerance, "required geometry probe is missing")
    error = abs(float(observed) - float(expected))
    if error < GRAY_LOW * tolerance:
        status = "pass"
    elif error <= GRAY_HIGH * tolerance:
        status = "review"
    else:
        status = "fail"
    return CheckResult(name, status, stage, float(observed), float(expected), tolerance, f"absolute_error={error:.9g}")


def _margin_check(name: str, stage: str, margin: float, tolerance: float) -> CheckResult:
    """Check a non-negative clearance/containment margin with a review band."""
    margin = float(margin)
    if margin > GRAY_HIGH * tolerance:
        status = "pass"
    elif margin >= -GRAY_HIGH * tolerance:
        status = "review"
    else:
        status = "fail"
    return CheckResult(name, status, stage, margin, ">= 0", tolerance)


def _exact_check(name: str, stage: str, observed: Any, expected: Any) -> CheckResult:
    return CheckResult(name, "pass" if observed == expected else "fail", stage, observed, expected, 0.0)


def _first_nonpass(checks: list[CheckResult]) -> JudgeDecision | None:
    for check in checks:
        if check.status == "fail":
            return JudgeDecision("fail", check.stage, tuple(checks))
        if check.status == "review":
            return JudgeDecision("review", "gray_zone_review", tuple(checks))
    return None


def _bbox_expectations(family: str, p: dict[str, float]) -> dict[str, float]:
    profiles: dict[str, dict[str, float]] = {
        "mounting_bracket": {"bbox_x": p.get("length", 0.0), "bbox_y": p.get("width", 0.0), "bbox_z": p.get("height", 0.0)},
        "flange_plate": {"bbox_x": p.get("outer_diameter", 0.0), "bbox_y": p.get("outer_diameter", 0.0), "bbox_z": p.get("thickness", 0.0)},
        "stepped_shaft": {"bbox_x": p.get("shoulder_diameter", 0.0), "bbox_y": p.get("shoulder_diameter", 0.0), "bbox_z": p.get("shaft_length", 0.0)},
        "electronics_enclosure": {"bbox_x": p.get("length", 0.0), "bbox_y": p.get("width", 0.0), "bbox_z": p.get("height", 0.0)},
        "belt_pulley": {"bbox_x": p.get("outer_diameter", 0.0), "bbox_y": p.get("outer_diameter", 0.0), "bbox_z": p.get("hub_length", 0.0)},
        "ribbed_angle": {"bbox_x": p.get("length", 0.0), "bbox_y": p.get("width", 0.0), "bbox_z": p.get("height", 0.0)},
        "bolt_pattern_plate": {"bbox_x": p.get("length", 0.0), "bbox_y": p.get("width", 0.0), "bbox_z": p.get("thickness", 0.0)},
        "pipe_clamp": {"bbox_x": p.get("outer_diameter", 0.0), "bbox_y": p.get("outer_diameter", 0.0) + 2.0 * p.get("lug_length", 0.0), "bbox_z": p.get("width", 0.0)},
        "gear_blank": {"bbox_z": p.get("thickness", 0.0)},
        "hinge": {"bbox_x": p.get("leaf_length", 0.0), "bbox_y": 2.0 * p.get("leaf_width", 0.0) + p.get("barrel_diameter", 0.0), "bbox_z": p.get("barrel_diameter", 0.0)},
        "bottle_cap": {"bbox_z": p.get("height", 0.0)},
        "lattice_panel": {"bbox_x": p.get("length", 0.0), "bbox_y": p.get("width", 0.0), "bbox_z": p.get("thickness", 0.0)},
        "bearing_housing": {"bbox_x": max(p.get("base_length", 0.0), p.get("outer_diameter", 0.0)), "bbox_y": max(p.get("base_width", 0.0), p.get("outer_diameter", 0.0))},
    }
    return {k: float(v) for k, v in profiles.get(family, {}).items() if float(v) > 0}


def _circle_edges(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    values = metrics.get("circle_edges", [])
    return [dict(item) for item in values if isinstance(item, dict)]


def _unique_circle_axes(metrics: dict[str, Any], radius: float, axis: str, tolerance: float) -> list[dict[str, float]]:
    """Collapse top/bottom circular edges into unique geometric axes."""
    found: list[dict[str, float]] = []
    for edge in _circle_edges(metrics):
        try:
            if str(edge.get("axis")) != axis:
                continue
            r = float(edge["radius"])
            if abs(r - radius) > GRAY_HIGH * tolerance:
                continue
            center = {"x": float(edge["center_x"]), "y": float(edge["center_y"]), "z": float(edge["center_z"])}
        except (KeyError, TypeError, ValueError):
            continue
        perpendicular = [name for name in "xyz" if name != axis]
        duplicate = False
        for prior in found:
            if all(abs(center[name] - prior[name]) <= GRAY_HIGH * tolerance for name in perpendicular):
                duplicate = True
                break
        if not duplicate:
            found.append(center)
    return found


def _feature_expectations(family: str, p: dict[str, float]) -> list[dict[str, Any]]:
    if family == "mounting_bracket":
        s = p["hole_spacing"] / 2.0
        return [{"name": "mount_holes", "axis": "z", "radius": p["hole_diameter"] / 2.0, "centers": [(-s, 0.0), (s, 0.0)]}]
    if family == "flange_plate":
        r = p["bolt_circle"] / 2.0
        return [
            {"name": "central_bore", "axis": "z", "radius": p["bore_diameter"] / 2.0, "centers": [(0.0, 0.0)]},
            {"name": "bolt_holes", "axis": "z", "radius": p["bolt_diameter"] / 2.0, "centers": [(r, 0.0), (0.0, r), (-r, 0.0), (0.0, -r)], "even_angles": 90.0},
        ]
    if family == "stepped_shaft":
        return [{"name": "axial_bore", "axis": "z", "radius": p["bore_diameter"] / 2.0, "centers": [(0.0, 0.0)]}]
    if family == "belt_pulley":
        return [
            {"name": "bore", "axis": "z", "radius": p["bore_diameter"] / 2.0, "centers": [(0.0, 0.0)]},
            {"name": "hub", "axis": "z", "radius": p["hub_diameter"] / 2.0, "centers": [(0.0, 0.0)]},
        ]
    if family == "bolt_pattern_plate":
        sx, sy = p["hole_spacing_x"] / 2.0, p["hole_spacing_y"] / 2.0
        return [{"name": "plate_holes", "axis": "z", "radius": p["hole_diameter"] / 2.0, "centers": [(-sx, -sy), (sx, -sy), (-sx, sy), (sx, sy)]}]
    if family == "pipe_clamp":
        overlap = min(0.5, p["lug_length"] * 0.05)
        lug_y = p["outer_diameter"] / 2.0 + p["lug_length"] / 2.0 - overlap / 2.0
        mount_hole = max(2.0, 0.42 * p["lug_thickness"])
        return [
            {"name": "pipe_bore", "axis": "z", "radius": p["inner_diameter"] / 2.0, "centers": [(0.0, 0.0)]},
            {"name": "lug_mount_holes", "axis": "z", "radius": mount_hole / 2.0, "centers": [(0.0, lug_y), (0.0, -lug_y)]},
        ]
    if family == "gear_blank":
        return [{"name": "gear_bore", "axis": "z", "radius": p["bore_diameter"] / 2.0, "centers": [(0.0, 0.0)]}]
    if family == "hinge":
        return [{"name": "pin_bore", "axis": "x", "radius": p["pin_diameter"] / 2.0, "centers": [(0.0, 0.0)]}]
    if family == "drawer_handle":
        s = p["mount_spacing"] / 2.0
        bore = max(2.0, min(p["grip_diameter"] * 0.42, p["mount_diameter"] * 0.28))
        return [
            {"name": "mount_bosses", "axis": "z", "radius": p["mount_diameter"] / 2.0, "centers": [(-s, 0.0), (s, 0.0)]},
            {"name": "mount_bores", "axis": "z", "radius": bore / 2.0, "centers": [(-s, 0.0), (s, 0.0)]},
        ]
    if family == "bottle_cap":
        inner = (p["outer_diameter"] - 2.0 * p["wall"]) / 2.0
        return [{"name": "cap_cavity", "axis": "z", "radius": inner, "centers": [(0.0, 0.0)]}]
    if family == "bearing_housing":
        corner_land = max(0.8, 0.012 * min(p["base_length"], p["base_width"]))
        mount_radius = max(1.2, min(0.025 * p["outer_diameter"], 0.16 * p["base_height"], 0.035 * min(p["base_length"], p["base_width"])))
        xoff = p["base_length"] / 2 - corner_land - mount_radius
        yoff = p["base_width"] / 2 - corner_land - mount_radius
        seat_diameter = p["bore_diameter"] + 0.35 * (p["outer_diameter"] - p["bore_diameter"])
        return [
            {"name": "bearing_bore", "axis": "z", "radius": p["bore_diameter"] / 2.0, "centers": [(0.0, 0.0)]},
            {"name": "bearing_seat", "axis": "z", "radius": seat_diameter / 2.0, "centers": [(0.0, 0.0)]},
            {"name": "base_mount_holes", "axis": "z", "radius": mount_radius, "centers": [(-xoff, -yoff), (-xoff, yoff), (xoff, -yoff), (xoff, yoff)]},
        ]
    return []


def _check_features(template: Template, state: EditState | None, p: dict[str, float], metrics: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for feature in _feature_expectations(template.task_family, p):
        radius = float(feature["radius"])
        tol = _length_tolerance(max(radius * 2.0, 1.0), state, template)
        axis = str(feature["axis"])
        centers = list(feature["centers"])
        observed_axes = _unique_circle_axes(metrics, radius, axis, tol)
        checks.append(_exact_check(f"topology:{feature['name']}:count", "topology", len(observed_axes), len(centers)))
        if checks[-1].status == "fail":
            continue
        perpendicular = [name for name in "xyz" if name != axis]
        remaining = list(observed_axes)
        matched_points: list[tuple[float, float]] = []
        for expected_center in centers:
            best_index = None
            best_distance = float("inf")
            for index, observed in enumerate(remaining):
                point = (float(observed[perpendicular[0]]), float(observed[perpendicular[1]]))
                distance = math.dist(point, tuple(map(float, expected_center)))
                if distance < best_distance:
                    best_distance = distance
                    best_index = index
            if best_index is None:
                checks.append(CheckResult(f"geometry:{feature['name']}:center", "fail", "geometry_relation", None, expected_center, tol))
                continue
            observed = remaining.pop(best_index)
            point = (float(observed[perpendicular[0]]), float(observed[perpendicular[1]]))
            matched_points.append(point)
            checks.append(_numeric_check(f"geometry:{feature['name']}:center", "geometry_relation", best_distance, 0.0, tol))
        if feature.get("even_angles") and matched_points:
            angles = sorted((math.degrees(math.atan2(y, x)) + 360.0) % 360.0 for x, y in matched_points)
            gaps = [(angles[(i + 1) % len(angles)] - angles[i]) % 360.0 for i in range(len(angles))]
            expected_gap = float(feature["even_angles"])
            max_error = max(abs(gap - expected_gap) for gap in gaps)
            checks.append(_numeric_check(f"geometry:{feature['name']}:angular_spacing", "geometry_relation", max_error, 0.0, _angle_tolerance(state, template)))
    return checks


def _response_checks(template: Template, state: EditState, baseline: dict[str, Any], observed: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    if not state.expected_relations.get("must_respond", False):
        return checks
    for rule in list(state.expected_relations.get("metric_responses", [])):
        metric = str(rule.get("metric", ""))
        if metric not in baseline or metric not in observed:
            checks.append(CheckResult(f"response:{metric}", "fail", "parameter_response", observed.get(metric), baseline.get(metric), None, "required response metric missing"))
            continue
        direction = str(rule.get("direction", "change"))
        if direction == "change":
            status = "pass" if observed[metric] != baseline[metric] else "fail"
            checks.append(CheckResult(f"response:{metric}", status, "parameter_response", observed[metric], f"different from {baseline[metric]}", None))
            continue
        try:
            baseline_value = float(baseline[metric])
            observed_value = float(observed[metric])
        except (TypeError, ValueError):
            checks.append(CheckResult(f"response:{metric}", "fail", "parameter_response", observed.get(metric), baseline.get(metric), None))
            continue
        delta = observed_value - baseline_value
        minimum = max(1e-9, abs(baseline_value) * float(rule.get("minimum_relative_delta", 0.0)))
        signed = delta if direction == "increase" else -delta
        if signed > GRAY_HIGH * minimum:
            status = "pass"
        elif signed >= GRAY_LOW * minimum:
            status = "review"
        else:
            status = "fail"
        checks.append(CheckResult(f"response:{metric}:{direction}", status, "parameter_response", delta, f">= {minimum:g}", minimum))
    if not checks:
        changed = baseline.get("geometry_signature") != observed.get("geometry_signature")
        checks.append(CheckResult("response:geometry", "pass" if changed else "fail", "parameter_response", changed, True, None))
    return checks


def _face_probes(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in metrics.get("face_probes", []) if isinstance(item, dict)]


def _repeated_feature_checks(template: Template, state: EditState | None, p: dict[str, float], metrics: dict[str, Any]) -> list[CheckResult]:
    """Geometry-level counts for repeated semantic features.

    Counts are recovered from planar-face locations/normals rather than trusted
    from candidate parameters, so ignoring a loop/count edit is detected.
    """
    family = template.task_family
    faces = _face_probes(metrics)
    checks: list[CheckResult] = []

    if family in {"gear_blank", "bottle_cap"}:
        if family == "gear_blank":
            expected = int(round(p["teeth"]))
            core = p["root_diameter"] / 2.0
            extra = (p["outer_diameter"] - p["root_diameter"]) / 2.0
            zref = p["thickness"]
            name = "teeth"
        else:
            expected = int(round(p["rib_count"]))
            core = p["outer_diameter"] / 2.0
            extra = p["rib_depth"]
            zref = p["height"] * 0.78
            name = "grip_ribs"
        observed = 0
        for face in faces:
            if str(face.get("geom_type")) != "PLANE":
                continue
            try:
                x, y = float(face["center_x"]), float(face["center_y"])
                nx, ny = float(face.get("normal_x", 0.0)), float(face.get("normal_y", 0.0))
                r = math.hypot(x, y)
                if r <= core + 0.55 * extra or r <= 1e-9:
                    continue
                alignment = (nx * x + ny * y) / r
                if alignment < 0.92:
                    continue
                if float(face.get("bbox_z", 0.0)) < 0.55 * zref:
                    continue
                observed += 1
            except (KeyError, TypeError, ValueError):
                continue
        checks.append(_exact_check(f"semantic:{name}:feature_count", "semantic_relation", observed, expected))

    elif family == "ribbed_angle":
        expected = 2 * int(round(p["rib_count"]))
        observed = 0
        for face in faces:
            try:
                if str(face.get("geom_type")) != "PLANE" or abs(float(face.get("normal_x", 0.0))) < 0.92:
                    continue
                by, bz = float(face.get("bbox_y", 0.0)), float(face.get("bbox_z", 0.0))
                if 0.18 * p["width"] < by < 0.75 * p["width"] and 0.18 * p["height"] < bz < 0.75 * p["height"]:
                    observed += 1
            except (TypeError, ValueError):
                continue
        checks.append(_exact_check("semantic:ribs:side_face_count", "semantic_relation", observed, expected))

    elif family == "lattice_panel":
        expected = 2 * int(round(p["bar_count"]))
        inner_x = p["length"] - 2.0 * p["frame_width"]
        inner_y = p["width"] - 2.0 * p["frame_width"]
        tol = _length_tolerance(max(inner_x, inner_y), state, template)
        observed = 0
        for face in faces:
            try:
                if str(face.get("geom_type")) != "PLANE" or abs(float(face.get("normal_x", 0.0))) < 0.92:
                    continue
                if abs(float(face.get("bbox_y", 0.0)) - inner_y) > GRAY_HIGH * tol:
                    continue
                if abs(float(face.get("bbox_z", 0.0)) - p["thickness"]) > GRAY_HIGH * tol:
                    continue
                if abs(float(face.get("center_x", 0.0))) >= inner_x / 2.0 - GRAY_HIGH * tol:
                    continue
                observed += 1
            except (TypeError, ValueError):
                continue
        checks.append(_exact_check("semantic:lattice_bars:side_face_count", "semantic_relation", observed, expected))
    return checks


def _semantic_checks(template: Template, state: EditState | None, p: dict[str, float], metrics: dict[str, Any]) -> list[CheckResult]:
    family = template.task_family
    checks: list[CheckResult] = []
    solid_count = metrics.get("solid_count")

    def margin(name: str, value: float, ref: float = 1.0) -> None:
        checks.append(_margin_check(f"semantic:{name}", "semantic_relation", value, _length_tolerance(ref, state, template)))

    def center(name: str, axis: str, expected: float, ref: float) -> None:
        checks.append(_numeric_check(f"semantic:{name}", "semantic_relation", metrics.get(f"center_{axis}"), expected, _length_tolerance(ref, state, template)))

    if family == "mounting_bracket":
        margin("holes_inside_length", (p["length"] - p["hole_spacing"] - p["hole_diameter"]) / 2.0, p["length"])
        if solid_count is not None:
            checks.append(_exact_check("semantic:upright_connected", "semantic_relation", int(solid_count), 1))
        center("mount_pattern_y_symmetry", "y", 0.0, p["width"])
    elif family == "flange_plate":
        margin("bore_inside_flange", (p["outer_diameter"] - p["bore_diameter"]) / 2.0, p["outer_diameter"])
        margin("bolt_holes_inside_flange", (p["outer_diameter"] - p["bolt_circle"] - p["bolt_diameter"]) / 2.0, p["outer_diameter"])
        center("flange_x_concentric", "x", 0.0, p["outer_diameter"])
        center("flange_y_concentric", "y", 0.0, p["outer_diameter"])
    elif family == "stepped_shaft":
        margin("shoulder_wider_than_shaft", (p["shoulder_diameter"] - p["shaft_diameter"]) / 2.0, p["shoulder_diameter"])
        margin("bore_inside_shaft", (p["shaft_diameter"] - p["bore_diameter"]) / 2.0, p["shaft_diameter"])
        center("shaft_x_concentric", "x", 0.0, p["shoulder_diameter"])
        center("shaft_y_concentric", "y", 0.0, p["shoulder_diameter"])
    elif family == "electronics_enclosure":
        margin("interior_clearance_x", (p["length"] - 2 * p["wall"]) / 2.0, p["length"])
        margin("interior_clearance_y", (p["width"] - 2 * p["wall"]) / 2.0, p["width"])
        margin("interior_clearance_z", p["height"] - p["wall"], p["height"])
        if solid_count is not None:
            checks.append(_exact_check("semantic:single_shell", "semantic_relation", int(solid_count), 1))
        expected_volume = p["length"] * p["width"] * p["height"] - (p["length"] - 2*p["wall"]) * (p["width"] - 2*p["wall"]) * (p["height"] - p["wall"])
        volume_tol = abs(expected_volume) * _relative_volume_tolerance(state, template)
        checks.append(_numeric_check("semantic:enclosure_volume", "semantic_relation", metrics.get("volume"), expected_volume, max(volume_tol, 1e-9)))
    elif family == "belt_pulley":
        margin("hub_inside_rim", (p["outer_diameter"] - p["hub_diameter"]) / 2.0, p["outer_diameter"])
        margin("bore_inside_hub", (p["hub_diameter"] - p["bore_diameter"]) / 2.0, p["hub_diameter"])
        margin("hub_covers_rim_width", p["hub_length"] - p["width"], p["hub_length"])
        center("pulley_x_concentric", "x", 0.0, p["outer_diameter"])
        center("pulley_y_concentric", "y", 0.0, p["outer_diameter"])
    elif family == "ribbed_angle":
        if solid_count is not None:
            checks.append(_exact_check("semantic:web_connected", "semantic_relation", int(solid_count), 1))
        center("rib_distribution_x", "x", 0.0, p["length"])
    elif family == "bolt_pattern_plate":
        margin("holes_inside_x", (p["length"] - p["hole_spacing_x"] - p["hole_diameter"]) / 2.0, p["length"])
        margin("holes_inside_y", (p["width"] - p["hole_spacing_y"] - p["hole_diameter"]) / 2.0, p["width"])
        center("plate_pattern_x_symmetry", "x", 0.0, p["length"])
        center("plate_pattern_y_symmetry", "y", 0.0, p["width"])
    elif family == "pipe_clamp":
        margin("pipe_wall", (p["outer_diameter"] - p["inner_diameter"]) / 2.0, p["outer_diameter"])
        center("clamp_x_symmetry", "x", 0.0, p["outer_diameter"])
    elif family == "gear_blank":
        margin("root_inside_outer", (p["outer_diameter"] - p["root_diameter"]) / 2.0, p["outer_diameter"])
        margin("bore_inside_root", (p["root_diameter"] - p["bore_diameter"]) / 2.0, p["root_diameter"])
        center("gear_x_radial_symmetry", "x", 0.0, p["outer_diameter"])
        center("gear_y_radial_symmetry", "y", 0.0, p["outer_diameter"])
    elif family == "hinge":
        margin("pin_inside_knuckles", (p["barrel_diameter"] - p["pin_diameter"]) / 2.0, p["barrel_diameter"])
        center("hinge_y_axis", "y", 0.0, 2*p["leaf_width"] + p["barrel_diameter"])
        center("hinge_z_axis", "z", 0.0, p["barrel_diameter"])
        knuckles = int(round(p["knuckle_count"]))
        tol = _length_tolerance(p["barrel_diameter"], state, template)
        barrel_edges = [e for e in _circle_edges(metrics) if e.get("axis") == "x" and abs(float(e.get("radius", -1)) - p["barrel_diameter"]/2.0) <= GRAY_HIGH*tol]
        pin_edges = [e for e in _circle_edges(metrics) if e.get("axis") == "x" and abs(float(e.get("radius", -1)) - p["pin_diameter"]/2.0) <= GRAY_HIGH*tol]
        checks.append(_exact_check("semantic:knuckle_end_count", "semantic_relation", len(barrel_edges), 4 * knuckles))
        checks.append(_exact_check("semantic:pin_bore_through_knuckles", "semantic_relation", len(pin_edges), 2 * knuckles))
    elif family == "drawer_handle":
        center("handle_x_symmetry", "x", 0.0, p["span"])
        center("handle_y_symmetry", "y", 0.0, p["mount_diameter"])
        margin("mounts_within_span", (p["span"] - p["mount_spacing"] - p["grip_diameter"]) / 2.0, p["span"])
        tol = _length_tolerance(p["span"], state, template)
        bridge_edges = [e for e in _circle_edges(metrics) if e.get("axis") == "x" and abs(float(e.get("radius", -1)) - p["grip_diameter"]/2.0) <= GRAY_HIGH*tol]
        if len(bridge_edges) >= 2:
            xs = [float(e["center_x"]) for e in bridge_edges]
            checks.append(_numeric_check("semantic:grip_span", "semantic_relation", max(xs) - min(xs), p["span"], tol))
        else:
            checks.append(CheckResult("semantic:grip_span", "fail", "semantic_relation", len(bridge_edges), ">= 2 bridge end circles", tol))
    elif family == "bottle_cap":
        margin("cap_hollow_wall", (p["outer_diameter"] - 2*p["wall"]) / 2.0, p["outer_diameter"])
        center("rib_distribution_x", "x", 0.0, p["outer_diameter"])
        center("rib_distribution_y", "y", 0.0, p["outer_diameter"])
    elif family == "lattice_panel":
        margin("frame_inner_x", (p["length"] - 2*p["frame_width"]) / 2.0, p["length"])
        margin("frame_inner_y", (p["width"] - 2*p["frame_width"]) / 2.0, p["width"])
        if solid_count is not None:
            checks.append(_exact_check("semantic:closed_frame", "semantic_relation", int(solid_count), 1))
        center("bar_distribution_x", "x", 0.0, p["length"])
        center("bar_distribution_y", "y", 0.0, p["width"])
    elif family == "bearing_housing":
        margin("bore_inside_housing", (p["outer_diameter"] - p["bore_diameter"]) / 2.0, p["outer_diameter"])
        if solid_count is not None:
            checks.append(_exact_check("semantic:housing_joined_to_base", "semantic_relation", int(solid_count), 1))
        center("housing_x_concentric", "x", 0.0, p["base_length"])
        center("housing_y_concentric", "y", 0.0, p["base_width"])

    # Release-v2 engineering relations add anti-shortcut checks such as
    # feature-to-edge clearance, non-overlap, pitch clearance and support
    # envelopes. They are fixed by the task specification before execution.
    try:
        from .challenge import constraint_margins
        for relation_name, relation_margin in constraint_margins(family, p).items():
            if "count_min" in relation_name:
                continue
            margin(f"engineering:{relation_name}", relation_margin, max(p.values()))
    except KeyError:
        pass
    checks.extend(_repeated_feature_checks(template, state, p, metrics))
    return checks


def judge_geometry(
    template: Template,
    state: EditState | None,
    observed: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> JudgeDecision:
    """Apply the paper's ordered automatic checks to one built geometry.

    ``state=None`` validates the nominal build.  A ``review`` decision means the
    geometry landed in a tolerance gray band and must receive a human label
    before it enters the paper's primary risk estimate.
    """
    p = dict(template.parameters if state is None else state.parameters)
    checks: list[CheckResult] = []

    # 2. Valid entity and prescribed connected-component count.
    checks.append(_exact_check("entity:is_valid", "entity_validity", observed.get("is_valid"), True))
    if observed.get("volume") is None or float(observed.get("volume", 0.0)) <= 0:
        checks.append(CheckResult("entity:positive_volume", "fail", "entity_validity", observed.get("volume"), "> 0", None))
    else:
        checks.append(CheckResult("entity:positive_volume", "pass", "entity_validity", float(observed["volume"]), "> 0", None))
    expected_components = template.constraints.get("connected_components")
    if expected_components is not None:
        checks.append(_exact_check("entity:connected_components", "entity_validity", observed.get("solid_count"), int(expected_components)))
    decision = _first_nonpass(checks)
    if decision:
        return decision

    # 3. Topology rules, including hole/circular-feature counts.
    topology = dict(template.constraints.get("topology", {}))
    for metric, requirement in (("face_count", "min_faces"), ("edge_count", "min_edges")):
        minimum = topology.get(requirement)
        if minimum is not None:
            value = observed.get(metric)
            status = "pass" if value is not None and int(value) >= int(minimum) else "fail"
            checks.append(CheckResult(f"topology:{metric}", status, "topology", value, f">= {minimum}", 0.0))
    checks.extend(_check_features(template, state, p, observed))
    decision = _first_nonpass(checks)
    if decision:
        return decision

    # 4. Direction and magnitude of the edited parameter's geometric response.
    if state is not None and baseline is not None:
        checks.extend(_response_checks(template, state, baseline, observed))
        decision = _first_nonpass(checks)
        if decision:
            return decision

    # 5. Dimensions, spacing, symmetry and containment.
    for metric, expected in _bbox_expectations(template.task_family, p).items():
        checks.append(_numeric_check(f"dimension:{metric}", "geometry_relation", observed.get(metric), expected, _length_tolerance(expected, state, template)))
    decision = _first_nonpass(checks)
    if decision:
        return decision

    # 6. High-level design semantic relations.
    checks.extend(_semantic_checks(template, state, p, observed))
    decision = _first_nonpass(checks)
    if decision:
        return decision
    return JudgeDecision("pass", None, tuple(checks))


def checks_to_jsonable(decision: JudgeDecision) -> list[dict[str, Any]]:
    return [
        {
            "name": c.name,
            "status": c.status,
            "stage": c.stage,
            "observed": c.observed,
            "expected": c.expected,
            "tolerance": c.tolerance,
            "detail": c.detail,
        }
        for c in decision.checks
    ]
