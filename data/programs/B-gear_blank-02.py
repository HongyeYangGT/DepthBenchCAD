"""Reference CadQuery program for DepthBenchCAD task B-gear_blank-02."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    root_diameter = _positive(params, "root_diameter")
    thickness = _positive(params, "thickness")
    bore_diameter = _positive(params, "bore_diameter")
    teeth = int(_positive(params, "teeth"))
    if not bore_diameter < root_diameter < outer_diameter or teeth < 6:
        raise ValueError("infeasible gear dimensions")
    part = cq.Workplane("XY").circle(root_diameter / 2).extrude(thickness).translate((0, 0, -thickness / 2))
    tooth_radial = (outer_diameter - root_diameter) / 2
    overlap = min(0.5, tooth_radial * 0.15)
    for index in range(teeth):
        angle = index * 360.0 / teeth
        tooth = cq.Workplane("XY").box(tooth_radial + overlap, tooth_radial * 1.25, thickness)
        tooth = tooth.translate((root_diameter / 2 + tooth_radial / 2 - overlap / 2, 0, 0)).rotate((0, 0, 0), (0, 0, 1), angle)
        part = part.union(tooth)
    return part.faces(">Z").workplane().hole(bore_diameter)
