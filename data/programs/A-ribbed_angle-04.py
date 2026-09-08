"""Reference CadQuery program for DepthBenchCAD task A-ribbed_angle-04."""

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
    rib_thickness = _positive(params, "rib_thickness")
    rib_count = int(_positive(params, "rib_count"))
    if wall >= min(width, height) / 2 or rib_count < 2:
        raise ValueError("infeasible angle dimensions")
    base = cq.Workplane("XY").box(length, width, wall)
    web = cq.Workplane("XY").box(length, wall, height).translate((0, -width / 2 + wall / 2, (height - wall) / 2))
    part = base.union(web)
    for index in range(rib_count):
        x = -length / 2 + (index + 0.5) * length / rib_count
        rib = cq.Workplane("XY").box(rib_thickness, width / 2, height / 2).translate((x, -width / 4, height / 4))
        part = part.union(rib)
    return part
