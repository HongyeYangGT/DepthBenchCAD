"""Reference CadQuery program for DepthBenchCAD task A-pipe_clamp-07."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    inner_diameter = _positive(params, "inner_diameter")
    width = _positive(params, "width")
    lug_length = _positive(params, "lug_length")
    lug_thickness = _positive(params, "lug_thickness")
    if inner_diameter >= outer_diameter or lug_thickness >= width:
        raise ValueError("infeasible clamp dimensions")
    body = cq.Workplane("XY").circle(outer_diameter / 2).circle(inner_diameter / 2).extrude(width).translate((0, 0, -width / 2))
    overlap = min(0.5, lug_length * 0.05)
    lug_y = outer_diameter / 2 + lug_length / 2 - overlap / 2
    lug_depth = lug_length + overlap
    upper = cq.Workplane("XY").box(lug_thickness, lug_depth, width).translate((0, lug_y, 0))
    lower = cq.Workplane("XY").box(lug_thickness, lug_depth, width).translate((0, -lug_y, 0))
    part = body.union(upper).union(lower)
    mount_hole = max(2.0, 0.42 * lug_thickness)
    points = [(0, lug_y), (0, -lug_y)]
    cutters = cq.Workplane("XY").workplane(offset=-width / 2 - 1).pushPoints(points).circle(mount_hole / 2).extrude(width + 2)
    part = part.cut(cutters)
    cbore = min(lug_thickness * 0.82, mount_hole * 1.7)
    cbore_depth = min(2.0, width * 0.12)
    counter = cq.Workplane("XY").workplane(offset=width / 2 - cbore_depth).pushPoints(points).circle(cbore / 2).extrude(cbore_depth)
    return part.cut(counter)
