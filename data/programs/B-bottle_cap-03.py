"""Reference CadQuery program for DepthBenchCAD task B-bottle_cap-03."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    height = _positive(params, "height")
    wall = _positive(params, "wall")
    rib_depth = _positive(params, "rib_depth")
    rib_count = int(_positive(params, "rib_count"))
    if wall >= outer_diameter / 3 or rib_depth >= outer_diameter / 5 or rib_count < 8:
        raise ValueError("infeasible cap dimensions")
    inner_diameter = outer_diameter - 2 * wall
    part = cq.Workplane("XY").circle(outer_diameter / 2).circle(inner_diameter / 2).extrude(height).translate((0, 0, -height / 2))
    overlap = min(0.4, rib_depth * 0.25)
    for index in range(rib_count):
        angle = index * 360.0 / rib_count
        tangential_pitch = math.pi * outer_diameter / rib_count
        rib_width = min(outer_diameter * 0.12, tangential_pitch * 0.56)
        rib = cq.Workplane("XY").box(rib_depth + overlap, rib_width, height * 0.78)
        rib = rib.translate((outer_diameter / 2 + rib_depth / 2 - overlap / 2, 0, 0)).rotate((0, 0, 0), (0, 0, 1), angle)
        part = part.union(rib)
    return part
