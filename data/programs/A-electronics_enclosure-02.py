"""Reference CadQuery program for DepthBenchCAD task A-electronics_enclosure-02."""

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
    if wall * 2 >= min(length, width) or wall >= height:
        raise ValueError("infeasible enclosure dimensions")
    outer = cq.Workplane("XY").box(length, width, height)
    cavity = cq.Workplane("XY").box(length - 2 * wall, width - 2 * wall, height - wall).translate((0, 0, wall / 2))
    return outer.cut(cavity)
