"""Reference CadQuery program for DepthBenchCAD task B-lattice_panel-06."""

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
    frame_width = _positive(params, "frame_width")
    bar_count = int(_positive(params, "bar_count"))
    bar_thickness = _positive(params, "bar_thickness")
    if frame_width * 2 >= min(length, width) or bar_count < 2:
        raise ValueError("infeasible lattice dimensions")
    outer = cq.Workplane("XY").box(length, width, thickness)
    inner = cq.Workplane("XY").box(length - 2 * frame_width, width - 2 * frame_width, thickness + 2)
    part = outer.cut(inner)
    span = length - 2 * frame_width
    for index in range(bar_count):
        x = -span / 2 + (index + 0.5) * span / bar_count
        bar = cq.Workplane("XY").box(bar_thickness, width - 2 * frame_width, thickness)
        part = part.union(bar.translate((x, 0, 0)))
    return part
