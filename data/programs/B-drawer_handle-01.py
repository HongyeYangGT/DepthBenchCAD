"""Reference CadQuery program for DepthBenchCAD task B-drawer_handle-01."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    span = _positive(params, "span")
    grip_diameter = _positive(params, "grip_diameter")
    grip_height = _positive(params, "grip_height")
    mount_diameter = _positive(params, "mount_diameter")
    mount_spacing = _positive(params, "mount_spacing")
    mount_height = _positive(params, "mount_height")
    if mount_spacing + grip_diameter >= span or grip_diameter >= mount_diameter:
        raise ValueError("infeasible handle dimensions")
    part = cq.Workplane("XY").circle(mount_diameter / 2).extrude(mount_height).translate((-mount_spacing / 2, 0, 0))
    part = part.union(cq.Workplane("XY").circle(mount_diameter / 2).extrude(mount_height).translate((mount_spacing / 2, 0, 0)))
    left_post = cq.Workplane("XY").circle(grip_diameter / 2).extrude(grip_height).translate((-mount_spacing / 2, 0, mount_height / 2))
    right_post = cq.Workplane("XY").circle(grip_diameter / 2).extrude(grip_height).translate((mount_spacing / 2, 0, mount_height / 2))
    bridge = cq.Workplane("YZ").circle(grip_diameter / 2).extrude(span).translate((-span / 2, 0, grip_height + mount_height / 2))
    part = part.union(left_post).union(right_post).union(bridge)
    bore = max(2.0, min(grip_diameter * 0.42, mount_diameter * 0.28))
    cutters = cq.Workplane("XY").workplane(offset=-1).pushPoints([(-mount_spacing / 2, 0), (mount_spacing / 2, 0)]).circle(bore / 2).extrude(mount_height + 2)
    return part.cut(cutters)
