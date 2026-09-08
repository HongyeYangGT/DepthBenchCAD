"""Reference CadQuery program for DepthBenchCAD task A-mounting_bracket-04."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    length = _positive(params, "length")
    width = _positive(params, "width")
    height = _positive(params, "height")
    wall = _positive(params, "wall")
    hole_diameter = _positive(params, "hole_diameter")
    hole_spacing = _positive(params, "hole_spacing")
    if wall >= min(length, width, height) / 2 or hole_diameter >= wall * 1.6:
        raise ValueError("infeasible bracket dimensions")
    base = cq.Workplane("XY").box(length, width, wall)
    upright = cq.Workplane("XY").box(wall, width, height).translate((-length / 2 + wall / 2, 0, (height - wall) / 2))
    part = base.union(upright)
    # A derived corner gusset makes the bracket structurally non-trivial while
    # remaining fully controlled by the existing design parameters.
    gusset = cq.Workplane("XY").box(2.2 * wall, width * 0.42, height * 0.32).translate((-length / 2 + 1.1 * wall, 0, wall + 0.16 * height))
    part = part.union(gusset)
    points = [(-hole_spacing / 2, 0), (hole_spacing / 2, 0)]
    return part.faces(">Z").workplane().pushPoints(points).hole(hole_diameter)
