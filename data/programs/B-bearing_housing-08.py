"""Reference CadQuery program for DepthBenchCAD task B-bearing_housing-08."""

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
    height = _positive(params, "height")
    base_length = _positive(params, "base_length")
    base_width = _positive(params, "base_width")
    base_height = _positive(params, "base_height")
    if bore_diameter >= outer_diameter:
        raise ValueError("infeasible bearing housing dimensions")
    base = cq.Workplane("XY").box(base_length, base_width, base_height)
    overlap = min(0.5, base_height * 0.1)
    housing = cq.Workplane("XY").circle(outer_diameter / 2).extrude(height + overlap).translate((0, 0, base_height / 2 - overlap))
    part = base.union(housing)
    part = part.faces(">Z").workplane().hole(bore_diameter)
    # A shallow concentric bearing seat gives the housing a real stepped
    # interface whose diameter must track both bore and outer shell.
    seat_diameter = bore_diameter + 0.35 * (outer_diameter - bore_diameter)
    seat_depth = max(1.2, min(0.18 * height, 0.30 * height))
    seat = cq.Workplane("XY").circle(seat_diameter / 2).extrude(seat_depth + 0.2).translate((0, 0, base_height / 2 + height - seat_depth))
    part = part.cut(seat)
    # Four-corner mounting pattern.  Hole size and setback are derived from
    # the housing/base envelope, keeping the bolt pattern outside the bearing
    # cylinder even at the legal support boundary.
    corner_land = max(0.8, 0.012 * min(base_length, base_width))
    mount_radius = max(1.2, min(0.025 * outer_diameter, 0.16 * base_height, 0.035 * min(base_length, base_width)))
    xoff = base_length / 2 - corner_land - mount_radius
    yoff = base_width / 2 - corner_land - mount_radius
    points = [(-xoff, -yoff), (-xoff, yoff), (xoff, -yoff), (xoff, yoff)]
    cutters = cq.Workplane("XY").workplane(offset=-base_height / 2 - 1).pushPoints(points).circle(mount_radius).extrude(base_height + 2)
    return part.cut(cutters)
