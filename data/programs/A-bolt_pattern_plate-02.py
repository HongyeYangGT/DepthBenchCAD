"""Reference CadQuery program for DepthBenchCAD task A-bolt_pattern_plate-02."""

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
    thickness = _positive(params, "thickness")
    hole_diameter = _positive(params, "hole_diameter")
    hole_spacing_x = _positive(params, "hole_spacing_x")
    hole_spacing_y = _positive(params, "hole_spacing_y")
    if hole_spacing_x + hole_diameter >= length or hole_spacing_y + hole_diameter >= width:
        raise ValueError("bolt pattern does not fit plate")
    plate = cq.Workplane("XY").box(length, width, thickness)
    points = [(x, y) for x in (-hole_spacing_x / 2, hole_spacing_x / 2) for y in (-hole_spacing_y / 2, hole_spacing_y / 2)]
    return plate.faces(">Z").workplane().pushPoints(points).hole(hole_diameter)
