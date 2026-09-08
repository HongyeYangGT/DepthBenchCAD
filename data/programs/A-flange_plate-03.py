"""Reference CadQuery program for DepthBenchCAD task A-flange_plate-03."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    thickness = _positive(params, "thickness")
    bore_diameter = _positive(params, "bore_diameter")
    bolt_circle = _positive(params, "bolt_circle")
    bolt_diameter = _positive(params, "bolt_diameter")
    if bore_diameter >= outer_diameter or bolt_circle + bolt_diameter >= outer_diameter:
        raise ValueError("infeasible flange dimensions")
    part = cq.Workplane("XY").circle(outer_diameter / 2).circle(bore_diameter / 2).extrude(thickness)
    points = [(bolt_circle / 2 * math.cos(index * math.pi / 2), bolt_circle / 2 * math.sin(index * math.pi / 2)) for index in range(4)]
    part = part.faces(">Z").workplane().pushPoints(points).hole(bolt_diameter)
    cbore_diameter = min(bolt_diameter * 1.75, max(bolt_diameter + 0.8, (bolt_circle - bore_diameter) * 0.42))
    cbore_depth = min(2.2, thickness * 0.28)
    cutters = cq.Workplane("XY").workplane(offset=thickness - cbore_depth).pushPoints(points).circle(cbore_diameter / 2).extrude(cbore_depth)
    return part.cut(cutters)
