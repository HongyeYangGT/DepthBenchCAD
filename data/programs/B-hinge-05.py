"""Reference CadQuery program for DepthBenchCAD task B-hinge-05."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    leaf_length = _positive(params, "leaf_length")
    leaf_width = _positive(params, "leaf_width")
    leaf_thickness = _positive(params, "leaf_thickness")
    barrel_diameter = _positive(params, "barrel_diameter")
    knuckle_count = int(_positive(params, "knuckle_count"))
    pin_diameter = _positive(params, "pin_diameter")
    if pin_diameter >= barrel_diameter or knuckle_count < 3:
        raise ValueError("infeasible hinge dimensions")
    ring_thickness = (barrel_diameter - pin_diameter) / 2
    overlap = min(0.4, leaf_width * 0.02, ring_thickness * 0.45)
    leaf_depth = leaf_width + overlap
    leaf_offset = barrel_diameter / 2 + leaf_width / 2 - overlap / 2
    left = cq.Workplane("XY").box(leaf_length, leaf_depth, leaf_thickness).translate((0, -leaf_offset, 0))
    right = cq.Workplane("XY").box(leaf_length, leaf_depth, leaf_thickness).translate((0, leaf_offset, 0))
    part = left.union(right)
    segment = leaf_length / knuckle_count
    for index in range(knuckle_count):
        # Build every knuckle as an annulus.  The bore is therefore encoded in
        # each repeated feature directly and cannot be accidentally filled by
        # a global post-hoc cut near a thin legal wall.
        barrel = cq.Workplane("YZ").circle(barrel_diameter / 2).circle(pin_diameter / 2).extrude(segment * 0.86)
        barrel = barrel.translate((-leaf_length / 2 + index * segment, 0, 0))
        part = part.union(barrel)
    return part
