"""Reference CadQuery program for DepthBenchCAD task A-belt_pulley-01."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    bore_diameter = _positive(params, "bore_diameter")
    width = _positive(params, "width")
    hub_diameter = _positive(params, "hub_diameter")
    hub_length = _positive(params, "hub_length")
    if not bore_diameter < hub_diameter < outer_diameter or hub_length < width:
        raise ValueError("infeasible pulley dimensions")
    rim = cq.Workplane("XY").circle(outer_diameter / 2).extrude(width)
    hub = cq.Workplane("XY").circle(hub_diameter / 2).extrude(hub_length).translate((0, 0, -(hub_length - width) / 2))
    part = rim.union(hub)
    part = part.faces(">Z").workplane().hole(bore_diameter)
    radial_clearance = hub_diameter - bore_diameter
    cbore_diameter = bore_diameter + 0.38 * radial_clearance
    cbore_depth = min(3.0, hub_length * 0.12)
    top_z = (hub_length + width) / 2
    bottom_z = -(hub_length - width) / 2
    cutter = cq.Workplane("XY").workplane(offset=top_z - cbore_depth).circle(cbore_diameter / 2).extrude(cbore_depth)
    part = part.cut(cutter)
    tier_diameter = bore_diameter + 0.72 * radial_clearance
    tier_depth = max(0.8, cbore_depth * 0.45)
    top_tier = cq.Workplane("XY").workplane(offset=top_z - tier_depth).circle(tier_diameter / 2).extrude(tier_depth)
    bottom_tier = cq.Workplane("XY").workplane(offset=bottom_z).circle(cbore_diameter / 2).extrude(tier_depth)
    return part.cut(top_tier).cut(bottom_tier)
