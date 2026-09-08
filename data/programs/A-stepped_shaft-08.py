"""Reference CadQuery program for DepthBenchCAD task A-stepped_shaft-08."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    shaft_diameter = _positive(params, "shaft_diameter")
    shoulder_diameter = _positive(params, "shoulder_diameter")
    shaft_length = _positive(params, "shaft_length")
    shoulder_length = _positive(params, "shoulder_length")
    bore_diameter = _positive(params, "bore_diameter")
    if shoulder_diameter <= shaft_diameter or bore_diameter >= shaft_diameter:
        raise ValueError("infeasible shaft dimensions")
    shaft = cq.Workplane("XY").circle(shaft_diameter / 2).extrude(shaft_length)
    shoulder = cq.Workplane("XY").circle(shoulder_diameter / 2).extrude(shoulder_length).translate((0, 0, shaft_length - shoulder_length))
    part = shaft.union(shoulder)
    part = part.faces(">Z").workplane().hole(bore_diameter)
    radial_clearance = shaft_diameter - bore_diameter
    cbore_diameter = bore_diameter + 0.38 * radial_clearance
    cbore_depth = min(3.0, shoulder_length * 0.22)
    cutter = cq.Workplane("XY").workplane(offset=shaft_length - cbore_depth).circle(cbore_diameter / 2).extrude(cbore_depth)
    part = part.cut(cutter)
    tier_diameter = bore_diameter + 0.72 * radial_clearance
    tier_depth = max(0.8, cbore_depth * 0.45)
    top_tier = cq.Workplane("XY").workplane(offset=shaft_length - tier_depth).circle(tier_diameter / 2).extrude(tier_depth)
    bottom_tier = cq.Workplane("XY").workplane(offset=0).circle(cbore_diameter / 2).extrude(tier_depth)
    return part.cut(top_tier).cut(bottom_tier)
