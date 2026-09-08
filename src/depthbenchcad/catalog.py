"""DepthBenchCAD task catalog derived from the BenchCAD task corpus.

This module packages the 120 DepthBenchCAD task definitions used in the study, derived from BenchCAD source tasks: eight
non-overlapping families with nine variants in environment A, and six
non-overlapping families with eight variants in environment B. Every item is
paired with its legal parameter ranges, task contract, reference CadQuery
program, calibration/test membership, and sixteen frozen counterfactual states.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from .audit import freeze_sixteen_states
from .challenge import diversified_nominals, split_variants
from .io import write_json
from .schema import EditState, Template, to_jsonable


@dataclass(frozen=True)
class FamilySpec:
    environment: str
    slug: str
    title: str
    description: str
    parameters: dict[str, float]
    parameter_ranges: dict[str, tuple[float, float]]
    primary_parameter: str
    linked_parameters: tuple[str, ...]
    semantic_parameter: str
    semantic_contract: tuple[str, ...]
    min_faces: int
    source: str


def _source(task: str, body: str) -> str:
    return f'''"""Reference CadQuery program for DepthBenchCAD task {task}."""

import cadquery as cq
import math


def _positive(params, name):
    value = float(params[name])
    if value <= 0:
        raise ValueError(f"{{name}} must be positive")
    return value


{body.strip()}
'''


def _specs() -> tuple[FamilySpec, ...]:
    return (
        FamilySpec(
            "A", "mounting_bracket", "Mounting bracket",
            "L-shaped mounting bracket with a drilled base and upright support.",
            {"length": 72.0, "width": 44.0, "height": 48.0, "wall": 6.0, "hole_diameter": 6.0, "hole_spacing": 42.0},
            {"length": (52.0, 96.0), "width": (30.0, 64.0), "height": (30.0, 78.0), "wall": (3.0, 12.0), "hole_diameter": (3.0, 10.0), "hole_spacing": (24.0, 62.0)},
            "length", ("length", "width"), "hole_spacing", ("base mounting pattern remains symmetric", "upright remains connected to the base"), 12,
            _source("mounting_bracket", '''
def build(params):
    length = _positive(params, "length")
    width = _positive(params, "width")
    height = _positive(params, "height")
    wall = _positive(params, "wall")
    hole_diameter = _positive(params, "hole_diameter")
    hole_spacing = _positive(params, "hole_spacing")
    if wall >= min(length, width, height) / 2 or hole_diameter >= wall * 1.6:
        raise ValueError("infeasible bracket dimensions")
    base = cq.Workplane("XY").box(length, width, wall)
    upright = cq.Workplane("XY").box(wall, width, height).translate((-length / 2 + wall / 2, 0, (height - wall) / 2))
    part = base.union(upright)
    # A derived corner gusset makes the bracket structurally non-trivial while
    # remaining fully controlled by the existing design parameters.
    gusset = cq.Workplane("XY").box(2.2 * wall, width * 0.42, height * 0.32).translate((-length / 2 + 1.1 * wall, 0, wall + 0.16 * height))
    part = part.union(gusset)
    points = [(-hole_spacing / 2, 0), (hole_spacing / 2, 0)]
    return part.faces(">Z").workplane().pushPoints(points).hole(hole_diameter)
'''),
        ),
        FamilySpec(
            "A", "flange_plate", "Bolt-circle flange",
            "Circular flange plate with a central bore and four evenly spaced bolts.",
            {"outer_diameter": 80.0, "thickness": 10.0, "bore_diameter": 28.0, "bolt_circle": 58.0, "bolt_diameter": 7.0},
            {"outer_diameter": (58.0, 112.0), "thickness": (5.0, 20.0), "bore_diameter": (12.0, 44.0), "bolt_circle": (38.0, 86.0), "bolt_diameter": (3.0, 11.0)},
            "outer_diameter", ("outer_diameter", "bolt_circle"), "bolt_circle", ("bolt holes stay on an even bolt circle", "central bore remains concentric"), 14,
            _source("flange_plate", '''
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
'''),
        ),
        FamilySpec(
            "A", "stepped_shaft", "Stepped shaft",
            "Rotational shaft with a shoulder and axial bore.",
            {"shaft_diameter": 24.0, "shoulder_diameter": 40.0, "shaft_length": 64.0, "shoulder_length": 18.0, "bore_diameter": 8.0},
            {"shaft_diameter": (14.0, 34.0), "shoulder_diameter": (28.0, 56.0), "shaft_length": (40.0, 92.0), "shoulder_length": (10.0, 32.0), "bore_diameter": (3.0, 14.0)},
            "shaft_length", ("shaft_diameter", "shoulder_diameter"), "shoulder_length", ("shoulder stays wider than the shaft", "axial bore remains concentric"), 8,
            _source("stepped_shaft", '''
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
'''),
        ),
        FamilySpec(
            "A", "electronics_enclosure", "Electronics enclosure",
            "Open-top rectangular enclosure with a uniform wall thickness.",
            {"length": 92.0, "width": 68.0, "height": 42.0, "wall": 3.5},
            {"length": (64.0, 128.0), "width": (46.0, 96.0), "height": (28.0, 70.0), "wall": (2.0, 40.0)},
            "length", ("length", "width"), "wall", ("interior clearance follows the exterior envelope", "the enclosure remains a single shell"), 10,
            _source("electronics_enclosure", '''
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
'''),
        ),
        FamilySpec(
            "A", "belt_pulley", "Belt pulley",
            "Stepped pulley with hub, rim, and axial bore.",
            {"outer_diameter": 72.0, "bore_diameter": 14.0, "width": 24.0, "hub_diameter": 36.0, "hub_length": 36.0},
            {"outer_diameter": (52.0, 108.0), "bore_diameter": (6.0, 24.0), "width": (12.0, 42.0), "hub_diameter": (24.0, 56.0), "hub_length": (20.0, 56.0)},
            "outer_diameter", ("outer_diameter", "hub_diameter"), "hub_length", ("hub remains concentric with the rim", "bore passes through the assembled pulley"), 10,
            _source("belt_pulley", '''
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
'''),
        ),
        FamilySpec(
            "A", "ribbed_angle", "Ribbed angle support",
            "Structural angle with repeated triangular-equivalent ribs represented by web blocks.",
            {"length": 96.0, "width": 54.0, "height": 62.0, "wall": 5.0, "rib_thickness": 6.0, "rib_count": 4.0},
            {"length": (68.0, 138.0), "width": (36.0, 82.0), "height": (42.0, 94.0), "wall": (3.0, 10.0), "rib_thickness": (3.0, 10.0), "rib_count": (2.0, 7.0)},
            "length", ("width", "height"), "rib_count", ("ribs are evenly distributed along the support", "base and vertical web remain connected"), 16,
            _source("ribbed_angle", '''
def build(params):
    length = _positive(params, "length")
    width = _positive(params, "width")
    height = _positive(params, "height")
    wall = _positive(params, "wall")
    rib_thickness = _positive(params, "rib_thickness")
    rib_count = int(_positive(params, "rib_count"))
    if wall >= min(width, height) / 2 or rib_count < 2:
        raise ValueError("infeasible angle dimensions")
    base = cq.Workplane("XY").box(length, width, wall)
    web = cq.Workplane("XY").box(length, wall, height).translate((0, -width / 2 + wall / 2, (height - wall) / 2))
    part = base.union(web)
    for index in range(rib_count):
        x = -length / 2 + (index + 0.5) * length / rib_count
        rib = cq.Workplane("XY").box(rib_thickness, width / 2, height / 2).translate((x, -width / 4, height / 4))
        part = part.union(rib)
    return part
'''),
        ),
        FamilySpec(
            "A", "bolt_pattern_plate", "Bolt-pattern plate",
            "Rectangular mounting plate with a symmetric four-hole pattern.",
            {"length": 88.0, "width": 58.0, "thickness": 8.0, "hole_diameter": 7.0, "hole_spacing_x": 58.0, "hole_spacing_y": 30.0},
            {"length": (62.0, 126.0), "width": (42.0, 86.0), "thickness": (4.0, 16.0), "hole_diameter": (3.0, 11.0), "hole_spacing_x": (34.0, 92.0), "hole_spacing_y": (20.0, 58.0)},
            "length", ("hole_spacing_x", "hole_spacing_y"), "hole_diameter", ("hole pattern is symmetric about both centerlines", "holes remain inside the plate"), 10,
            _source("bolt_pattern_plate", '''
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
'''),
        ),
        FamilySpec(
            "A", "pipe_clamp", "Pipe clamp",
            "Split-style pipe-support body with a hollow bore and two mounting lugs.",
            {"outer_diameter": 66.0, "inner_diameter": 46.0, "width": 24.0, "lug_length": 26.0, "lug_thickness": 8.0},
            {"outer_diameter": (48.0, 94.0), "inner_diameter": (28.0, 70.0), "width": (14.0, 42.0), "lug_length": (16.0, 44.0), "lug_thickness": (4.0, 14.0)},
            "outer_diameter", ("outer_diameter", "inner_diameter"), "lug_length", ("pipe bore remains concentric", "two lugs remain mirrored around the clamp body"), 14,
            _source("pipe_clamp", '''
def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    inner_diameter = _positive(params, "inner_diameter")
    width = _positive(params, "width")
    lug_length = _positive(params, "lug_length")
    lug_thickness = _positive(params, "lug_thickness")
    if inner_diameter >= outer_diameter or lug_thickness >= width:
        raise ValueError("infeasible clamp dimensions")
    body = cq.Workplane("XY").circle(outer_diameter / 2).circle(inner_diameter / 2).extrude(width).translate((0, 0, -width / 2))
    overlap = min(0.5, lug_length * 0.05)
    lug_y = outer_diameter / 2 + lug_length / 2 - overlap / 2
    lug_depth = lug_length + overlap
    upper = cq.Workplane("XY").box(lug_thickness, lug_depth, width).translate((0, lug_y, 0))
    lower = cq.Workplane("XY").box(lug_thickness, lug_depth, width).translate((0, -lug_y, 0))
    part = body.union(upper).union(lower)
    mount_hole = max(2.0, 0.42 * lug_thickness)
    points = [(0, lug_y), (0, -lug_y)]
    cutters = cq.Workplane("XY").workplane(offset=-width / 2 - 1).pushPoints(points).circle(mount_hole / 2).extrude(width + 2)
    part = part.cut(cutters)
    cbore = min(lug_thickness * 0.82, mount_hole * 1.7)
    cbore_depth = min(2.0, width * 0.12)
    counter = cq.Workplane("XY").workplane(offset=width / 2 - cbore_depth).pushPoints(points).circle(cbore / 2).extrude(cbore_depth)
    return part.cut(counter)
'''),
        ),
        FamilySpec(
            "B", "gear_blank", "Gear blank",
            "Radial gear-like blank with an axial bore and parametrized tooth count.",
            {"outer_diameter": 76.0, "root_diameter": 58.0, "thickness": 12.0, "bore_diameter": 16.0, "teeth": 12.0},
            {"outer_diameter": (54.0, 110.0), "root_diameter": (38.0, 86.0), "thickness": (6.0, 22.0), "bore_diameter": (6.0, 28.0), "teeth": (8.0, 20.0)},
            "outer_diameter", ("outer_diameter", "root_diameter"), "teeth", ("teeth are evenly distributed radially", "bore stays concentric with the gear blank"), 20,
            _source("gear_blank", '''
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
'''),
        ),
        FamilySpec(
            "B", "hinge", "Leaf hinge",
            "Two-leaf hinge with alternating knuckles and a through pin bore.",
            {"leaf_length": 76.0, "leaf_width": 34.0, "leaf_thickness": 3.0, "barrel_diameter": 10.0, "knuckle_count": 5.0, "pin_diameter": 4.0},
            {"leaf_length": (52.0, 112.0), "leaf_width": (22.0, 52.0), "leaf_thickness": (2.0, 6.0), "barrel_diameter": (6.0, 16.0), "knuckle_count": (3.0, 7.0), "pin_diameter": (2.0, 7.0)},
            "leaf_length", ("leaf_width", "barrel_diameter"), "knuckle_count", ("knuckles span the hinge axis", "pin bore runs through every knuckle"), 18,
            _source("hinge", '''
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
'''),
        ),
        FamilySpec(
            "B", "drawer_handle", "Drawer handle",
            "Bridge-style drawer handle with symmetric mounting bosses.",
            {"span": 112.0, "grip_diameter": 12.0, "grip_height": 28.0, "mount_diameter": 22.0, "mount_spacing": 84.0, "mount_height": 8.0},
            {"span": (78.0, 158.0), "grip_diameter": (7.0, 20.0), "grip_height": (16.0, 46.0), "mount_diameter": (14.0, 34.0), "mount_spacing": (54.0, 124.0), "mount_height": (4.0, 16.0)},
            "span", ("span", "mount_spacing"), "grip_height", ("mounts remain symmetric", "grip spans the two mounting bosses"), 12,
            _source("drawer_handle", '''
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
'''),
        ),
        FamilySpec(
            "B", "bottle_cap", "Ribbed bottle cap",
            "Hollow cylindrical cap with a wall and repeated external grip ribs.",
            {"outer_diameter": 50.0, "height": 28.0, "wall": 2.5, "rib_depth": 2.0, "rib_count": 18.0},
            {"outer_diameter": (34.0, 76.0), "height": (18.0, 46.0), "wall": (1.5, 15.0), "rib_depth": (1.0, 9.0), "rib_count": (8.0, 32.0)},
            "outer_diameter", ("outer_diameter", "height"), "rib_count", ("cap stays hollow", "ribs are evenly distributed around the outside"), 24,
            _source("bottle_cap", '''
def build(params):
    outer_diameter = _positive(params, "outer_diameter")
    height = _positive(params, "height")
    wall = _positive(params, "wall")
    rib_depth = _positive(params, "rib_depth")
    rib_count = int(_positive(params, "rib_count"))
    if wall >= outer_diameter / 3 or rib_depth >= outer_diameter / 5 or rib_count < 8:
        raise ValueError("infeasible cap dimensions")
    inner_diameter = outer_diameter - 2 * wall
    part = cq.Workplane("XY").circle(outer_diameter / 2).circle(inner_diameter / 2).extrude(height).translate((0, 0, -height / 2))
    overlap = min(0.4, rib_depth * 0.25)
    for index in range(rib_count):
        angle = index * 360.0 / rib_count
        tangential_pitch = math.pi * outer_diameter / rib_count
        rib_width = min(outer_diameter * 0.12, tangential_pitch * 0.56)
        rib = cq.Workplane("XY").box(rib_depth + overlap, rib_width, height * 0.78)
        rib = rib.translate((outer_diameter / 2 + rib_depth / 2 - overlap / 2, 0, 0)).rotate((0, 0, 0), (0, 0, 1), angle)
        part = part.union(rib)
    return part
'''),
        ),
        FamilySpec(
            "B", "lattice_panel", "Lattice panel",
            "Rectangular frame with evenly spaced internal lattice bars.",
            {"length": 120.0, "width": 84.0, "thickness": 5.0, "frame_width": 8.0, "bar_count": 5.0, "bar_thickness": 4.0},
            {"length": (84.0, 172.0), "width": (58.0, 124.0), "thickness": (3.0, 10.0), "frame_width": (5.0, 14.0), "bar_count": (3.0, 9.0), "bar_thickness": (2.0, 8.0)},
            "length", ("length", "width"), "bar_count", ("frame closes all four edges", "bars are evenly spaced inside the frame"), 18,
            _source("lattice_panel", '''
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
'''),
        ),
        FamilySpec(
            "B", "bearing_housing", "Bearing housing",
            "Cylindrical bearing housing integrated with a rectangular mounting base.",
            {"outer_diameter": 76.0, "bore_diameter": 42.0, "height": 32.0, "base_length": 108.0, "base_width": 72.0, "base_height": 10.0},
            {"outer_diameter": (54.0, 112.0), "bore_diameter": (28.0, 68.0), "height": (18.0, 52.0), "base_length": (78.0, 152.0), "base_width": (52.0, 102.0), "base_height": (5.0, 18.0)},
            "outer_diameter", ("base_length", "base_width"), "bore_diameter", ("bore remains concentric with the housing", "stepped bearing seat remains concentric", "housing remains joined to its mounting base", "four base mounting holes remain symmetric"), 14,
            _source("bearing_housing", '''
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
'''),
        ),
    )


FAMILY_SPECS = _specs()


def families_for(environment: str) -> tuple[FamilySpec, ...]:
    if environment not in {"A", "B", "both"}:
        raise ValueError("environment must be A, B, or both")
    return tuple(spec for spec in FAMILY_SPECS if environment == "both" or spec.environment == environment)


def _variant_parameters(spec: FamilySpec, variant: int, variants: int) -> dict[str, float]:
    """Return one member of the deterministic ratio-diverse design set."""
    return diversified_nominals(spec.slug, spec.parameters, spec.parameter_ranges, variants, spec.linked_parameters)[variant - 1]


def _task_constraints(spec: FamilySpec, split: str) -> dict[str, Any]:
    return {
        "positive_volume": True,
        "connected_components": 1,
        "topology": {"min_faces": spec.min_faces, "min_edges": spec.min_faces * 2},
        "primary_parameter": spec.primary_parameter,
        "linked_parameters": list(spec.linked_parameters),
        "semantic_parameter": spec.semantic_parameter,
        "semantic_contract": list(spec.semantic_contract),
        "metric_tolerance": {"length_mm": 0.05, "relative_volume": 0.005, "angle_deg": 0.1},
        "automatic_judge": {
            "protocol": "paper_section_4.2",
            "version": 2,
            "profile": spec.slug,
            "gray_zone_band": [0.90, 1.10],
        },
        "environment": spec.environment,
        "split": split,
    }


def _template_id(spec: FamilySpec, variant: int) -> str:
    return f"{spec.environment}-{spec.slug}-{variant:02d}"


def build_catalog(root: str | Path, environment: str = "both") -> list[Template]:
    """Build the complete released DepthBenchCAD corpus and write its reference programs."""
    root = Path(root)
    program_dir = root / "data" / "programs"
    program_dir.mkdir(parents=True, exist_ok=True)
    templates: list[Template] = []
    for spec in families_for(environment):
        variants = 9 if spec.environment == "A" else 8
        calibration_count = 3 if spec.environment == "A" else 2
        calibration_variants = split_variants(spec.slug, variants, calibration_count)
        for variant in range(1, variants + 1):
            template_id = _template_id(spec, variant)
            source = spec.source.replace(f"DepthBenchCAD task {spec.slug}", f"DepthBenchCAD task {template_id}")
            ast.parse(source, filename=f"{template_id}.py")
            program_file = program_dir / f"{template_id}.py"
            program_file.write_text(source, encoding="utf-8")
            parameters = _variant_parameters(spec, variant, variants)
            parameter_ranges = dict(spec.parameter_ranges)
            split = "calibration" if variant in calibration_variants else "test"
            seed_state = EditState(f"{template_id}-nominal", "local", dict(parameters))
            nominal = Template(
                template_id=template_id,
                task_family=spec.slug,
                description=spec.description,
                parameters=parameters,
                parameter_ranges=parameter_ranges,
                constraints=_task_constraints(spec, split),
                states=(seed_state,),
                program_path=f"../programs/{program_file.name}",
            )
            templates.append(replace(nominal, states=freeze_sixteen_states(nominal)))
    return templates


def write_catalog(root: str | Path, environment: str = "both") -> Path:
    """Materialize the corpus JSON manifest and return its path."""
    root = Path(root)
    templates = build_catalog(root, environment)
    output = root / "data" / "templates" / "depthbenchcad_tasks.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    counts = {
        "A": {"families": 8, "templates": 72, "calibration": 24, "test": 48},
        "B": {"families": 6, "templates": 48, "calibration": 12, "test": 36},
    }
    selected = {key: dict(value, name=f"DepthBenchCAD-{key}") for key, value in counts.items() if environment in {"both", key}}
    write_json(
        output,
        {
            "schema_version": 1,
            "benchmark": "DepthBenchCAD",
            "corpus": "depthbenchcad_v1",
            "provenance": "DepthBenchCAD task corpus used in the study, constructed from BenchCAD source tasks and packaged with the frozen calibration/test split and 16-state counterfactual audit specification.",
            "task_source": "BenchCAD",
            "source_corpus": "BenchCAD",
            "task_identity": "depthbenchcad_study_tasks",
            "environments": selected,
            "templates": [to_jsonable(template) for template in templates],
        },
    )
    return output


def catalog_summary(templates: Iterable[Template]) -> dict[str, int]:
    items = list(templates)
    return {
        "templates": len(items),
        "families": len({template.task_family for template in items}),
        "states": sum(len(template.states) for template in items),
    }
