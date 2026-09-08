"""Challenge construction for the DepthBenchCAD counterfactual audit benchmark.

This module is deliberately independent of candidate programs.  It defines
engineering legality, deterministic design-space diversification, and frozen
counterfactual interventions before any candidate is executed.  Reference
programs are validated against these states; task difficulty is never relaxed
because a reference or model fails.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Iterable


COUNT_PARAMETERS = {"rib_count", "teeth", "knuckle_count", "bar_count"}
PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29)

# Frozen design constants. These explicit values preserve the released task
# population independently of repository/package naming.
NOMINAL_OFFSETS = {
    "mounting_bracket": 446, "flange_plate": 81, "stepped_shaft": 750,
    "electronics_enclosure": 994, "belt_pulley": 499, "ribbed_angle": 235,
    "bolt_pattern_plate": 513, "pipe_clamp": 836, "gear_blank": 790,
    "hinge": 809, "drawer_handle": 258, "bottle_cap": 1009,
    "lattice_panel": 321, "bearing_housing": 993,
}
CALIBRATION_VARIANTS = {
    "mounting_bracket": (1, 6, 9), "flange_plate": (5, 7, 8),
    "stepped_shaft": (2, 3, 4), "electronics_enclosure": (7, 8, 9),
    "belt_pulley": (1, 2, 5), "ribbed_angle": (4, 6, 8),
    "bolt_pattern_plate": (2, 6, 9), "pipe_clamp": (5, 6, 9),
    "gear_blank": (1, 8), "hinge": (1, 8), "drawer_handle": (1, 8),
    "bottle_cap": (2, 7), "lattice_panel": (6, 7), "bearing_housing": (3, 7),
}


def _vdc(index: int, base: int) -> float:
    value = 0.0
    denom = 1.0
    while index:
        index, remainder = divmod(index, base)
        denom *= base
        value += remainder / denom
    return value


def _clip(value: float, bounds: tuple[float, float], *, count: bool = False) -> float:
    lo, hi = map(float, bounds)
    value = min(hi, max(lo, float(value)))
    if count:
        value = float(min(int(math.floor(hi)), max(int(math.ceil(lo)), round(value))))
    return round(value, 6)


def _scale(p: dict[str, float]) -> float:
    dimensional = [abs(float(v)) for k, v in p.items() if k not in COUNT_PARAMETERS]
    return max(dimensional or [1.0])


def constraint_margins(family: str, p: dict[str, float]) -> dict[str, float]:
    """Positive values denote a legal engineering margin.

    These are task semantics, not post-hoc pass-rate controls.  They are used
    both to freeze legal states and to audit the corpus for near-boundary
    challenge coverage.
    """
    if family == "mounting_bracket":
        return {
            "wall_clearance": min(p["length"], p["width"], p["height"]) / 2 - p["wall"],
            "hole_vs_wall": 1.6 * p["wall"] - p["hole_diameter"],
            "hole_edge_clearance": p["length"] - p["hole_spacing"] - p["hole_diameter"],
            "hole_separation": p["hole_spacing"] - p["hole_diameter"],
        }
    if family == "flange_plate":
        return {
            "bore_wall": p["outer_diameter"] - p["bore_diameter"],
            "bolt_edge_clearance": p["outer_diameter"] - p["bolt_circle"] - p["bolt_diameter"],
            "bore_bolt_clearance": p["bolt_circle"] - p["bolt_diameter"] - p["bore_diameter"],
        }
    if family == "stepped_shaft":
        return {
            "shoulder_step": p["shoulder_diameter"] - p["shaft_diameter"],
            "shaft_wall": p["shaft_diameter"] - p["bore_diameter"],
            "shoulder_axial_fit": p["shaft_length"] - p["shoulder_length"],
        }
    if family == "electronics_enclosure":
        return {
            "interior_x": p["length"] - 2 * p["wall"],
            "interior_y": p["width"] - 2 * p["wall"],
            "interior_z": p["height"] - p["wall"],
        }
    if family == "belt_pulley":
        return {
            "hub_to_rim": p["outer_diameter"] - p["hub_diameter"],
            "bore_to_hub": p["hub_diameter"] - p["bore_diameter"],
            "hub_overhang": p["hub_length"] - p["width"],
        }
    if family == "ribbed_angle":
        return {
            "wall_clearance": min(p["width"], p["height"]) - 2 * p["wall"],
            "rib_pitch_clearance": p["length"] / max(1.0, p["rib_count"]) - p["rib_thickness"],
            "rib_count_min": p["rib_count"] - 1.5,
        }
    if family == "bolt_pattern_plate":
        return {
            "hole_edge_x": p["length"] - p["hole_spacing_x"] - p["hole_diameter"],
            "hole_edge_y": p["width"] - p["hole_spacing_y"] - p["hole_diameter"],
            "hole_separation_x": p["hole_spacing_x"] - p["hole_diameter"],
            "hole_separation_y": p["hole_spacing_y"] - p["hole_diameter"],
        }
    if family == "pipe_clamp":
        return {
            "ring_wall": p["outer_diameter"] - p["inner_diameter"],
            "lug_width_clearance": p["width"] - p["lug_thickness"],
            "lug_length_positive": p["lug_length"],
        }
    if family == "gear_blank":
        return {
            "tooth_radial_depth": p["outer_diameter"] - p["root_diameter"],
            "root_wall": p["root_diameter"] - p["bore_diameter"],
            "tooth_count_min": p["teeth"] - 5.5,
        }
    if family == "hinge":
        return {
            "pin_wall": p["barrel_diameter"] - p["pin_diameter"],
            "knuckle_count_min": p["knuckle_count"] - 2.5,
            "leaf_to_barrel": p["leaf_width"] - p["barrel_diameter"] / 2,
        }
    if family == "drawer_handle":
        return {
            "bridge_reach": p["span"] - p["mount_spacing"] - p["grip_diameter"],
            "grip_vs_mount": p["mount_diameter"] - p["grip_diameter"],
            "post_height": p["grip_height"] - p["mount_height"] * 0.35,
        }
    if family == "bottle_cap":
        return {
            "hollow_wall": p["outer_diameter"] / 3 - p["wall"],
            "rib_depth_limit": p["outer_diameter"] / 5 - p["rib_depth"],
            "inner_diameter": p["outer_diameter"] - 2 * p["wall"],
            "rib_count_min": p["rib_count"] - 7.5,
        }
    if family == "lattice_panel":
        return {
            "frame_x": p["length"] - 2 * p["frame_width"],
            "frame_y": p["width"] - 2 * p["frame_width"],
            "bar_pitch_clearance": (p["length"] - 2 * p["frame_width"]) / max(1.0, p["bar_count"]) - p["bar_thickness"],
            "bar_count_min": p["bar_count"] - 1.5,
        }
    if family == "bearing_housing":
        return {
            "bearing_wall": p["outer_diameter"] - p["bore_diameter"],
            "base_length_support": p["base_length"] - 1.02 * p["outer_diameter"],
            "base_width_support": p["base_width"] - 0.72 * p["outer_diameter"],
            "base_height_positive": p["base_height"],
        }
    raise KeyError(f"unknown family: {family}")


def safety_margin(p: dict[str, float]) -> float:
    """Absolute margin used to separate legal states from tolerance gray zones."""
    return max(0.30, 0.0035 * _scale(p))


def is_legal(family: str, p: dict[str, float], *, margin: float | None = None) -> bool:
    threshold = safety_margin(p) if margin is None else float(margin)
    for name, value in constraint_margins(family, p).items():
        required = 0.25 if "count_min" in name else threshold
        if float(value) <= required:
            return False
    return True


def normalized_distance(a: dict[str, float], b: dict[str, float], ranges: dict[str, tuple[float, float]]) -> float:
    total = 0.0
    for key in a:
        lo, hi = ranges[key]
        span = max(float(hi) - float(lo), 1e-9)
        total += ((float(a[key]) - float(b[key])) / span) ** 2
    return math.sqrt(total)


def diversified_nominals(
    family: str,
    base: dict[str, float],
    ranges: dict[str, tuple[float, float]],
    count: int,
    linked: tuple[str, ...] = (),
) -> list[dict[str, float]]:
    """Generate legal, ratio-diverse template instances using a Halton design.

    Values occupy an interior 10--90% band; relational difficulty is reserved
    for frozen boundary interventions rather than accidentally illegal nominals.
    """
    offset = NOMINAL_OFFSETS[family]
    keys = list(base)
    accepted: list[dict[str, float]] = []
    attempt = 0
    while len(accepted) < count and attempt < 50000:
        idx = offset + attempt + 1
        candidate: dict[str, float] = {}
        for j, key in enumerate(keys):
            u = _vdc(idx + 37 * j, PRIMES[j])
            u = 0.10 + 0.80 * u
            lo, hi = ranges[key]
            candidate[key] = _clip(lo + u * (hi - lo), ranges[key], count=key in COUNT_PARAMETERS)
        attempt += 1
        # Keep nominals well inside engineering feasibility while retaining
        # non-dimensional diversity across parameters.
        if not is_legal(family, candidate, margin=max(1.25, 0.06 * _scale(candidate))):
            continue
        if linked:
            linked_lo = max(float(ranges[k][0]) / float(candidate[k]) for k in linked)
            linked_hi = min(float(ranges[k][1]) / float(candidate[k]) for k in linked)
            # Reserve substantial room on both sides for dependency-closure
            # interventions; this is a task-design criterion, not a pass-rate fix.
            if linked_lo > 0.84 or linked_hi < 1.16:
                continue
        if any(normalized_distance(candidate, prior, ranges) < 0.27 for prior in accepted):
            continue
        accepted.append(candidate)
    if len(accepted) != count:
        raise RuntimeError(f"could not construct {count} diverse legal nominals for {family}")
    return accepted


def split_variants(family: str, variants: int, calibration_count: int) -> set[int]:
    """Fixed seeded family-internal split independent of design magnitude/order."""
    selected = set(CALIBRATION_VARIANTS[family])
    if len(selected) != calibration_count or any(v < 1 or v > variants for v in selected):
        raise ValueError(f"frozen split does not match {family} cardinalities")
    return selected


def local_parameters(family: str, keys: Iterable[str]) -> tuple[str, ...]:
    preferred = {
        "mounting_bracket": ("length", "wall", "hole_diameter", "hole_spacing"),
        "flange_plate": ("outer_diameter", "bore_diameter", "bolt_circle", "bolt_diameter"),
        "stepped_shaft": ("shaft_length", "shaft_diameter", "bore_diameter", "shoulder_length"),
        "electronics_enclosure": ("length", "width", "height", "wall"),
        "belt_pulley": ("outer_diameter", "bore_diameter", "width", "hub_length"),
        "ribbed_angle": ("length", "wall", "rib_thickness", "height"),
        "bolt_pattern_plate": ("length", "width", "hole_diameter", "thickness"),
        "pipe_clamp": ("outer_diameter", "inner_diameter", "width", "lug_thickness"),
        "gear_blank": ("outer_diameter", "root_diameter", "bore_diameter", "thickness"),
        "hinge": ("leaf_length", "leaf_width", "barrel_diameter", "pin_diameter"),
        "drawer_handle": ("span", "grip_diameter", "mount_spacing", "mount_height"),
        "bottle_cap": ("outer_diameter", "height", "wall", "rib_depth"),
        "lattice_panel": ("length", "width", "frame_width", "bar_thickness"),
        "bearing_housing": ("outer_diameter", "bore_diameter", "base_length", "base_width"),
    }[family]
    allowed = set(keys)
    return tuple(k for k in preferred if k in allowed)


def make_local_states(family: str, base: dict[str, float], ranges: dict[str, tuple[float, float]]) -> list[tuple[dict[str, float], dict[str, Any]]]:
    states: list[tuple[dict[str, float], dict[str, Any]]] = []
    for idx, key in enumerate(local_parameters(family, base)):
        lo, hi = ranges[key]
        direction = -1 if idx % 2 == 0 else 1
        fractions = (0.32, 0.26, 0.21, 0.16, 0.12)
        chosen = None
        for fraction in fractions:
            target = base[key] + direction * fraction * (hi - lo)
            candidate = dict(base)
            candidate[key] = _clip(target, ranges[key], count=key in COUNT_PARAMETERS)
            if normalized_distance(candidate, base, ranges) >= 0.10 and is_legal(family, candidate):
                chosen = candidate
                break
        if chosen is None:
            # Try the opposite direction without changing the task constraints.
            for fraction in fractions:
                target = base[key] - direction * fraction * (hi - lo)
                candidate = dict(base)
                candidate[key] = _clip(target, ranges[key], count=key in COUNT_PARAMETERS)
                if normalized_distance(candidate, base, ranges) >= 0.10 and is_legal(family, candidate):
                    chosen = candidate
                    break
        if chosen is None:
            raise RuntimeError(f"no challenging legal local edit for {family}:{key}")
        states.append((chosen, {"changed_parameters": [key], "intervention": f"single_parameter:{key}"}))
    if len(states) != 4:
        raise RuntimeError(f"local profile for {family} did not yield four states")
    return states


def _boundary_pool(family: str, base: dict[str, float], ranges: dict[str, tuple[float, float]]) -> list[tuple[float, str, dict[str, float], list[str]]]:
    keys = list(base)
    scale = _scale(base)
    safe = safety_margin(base)
    pool: list[tuple[float, str, dict[str, float], list[str]]] = []
    digest = int.from_bytes(hashlib.sha256(f"boundary:{family}".encode()).digest()[:4], "big")
    # One- and two-parameter interventions.  Bias samples towards legal edges
    # and relational boundaries, then rank by the actual engineering margin.
    pairs: list[tuple[str, ...]] = [(k,) for k in keys]
    pairs += [(keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))]
    for pi, changed in enumerate(pairs):
        for sample in range(1, 72):
            candidate = dict(base)
            for cj, key in enumerate(changed):
                u = _vdc(digest % 997 + sample + 31 * pi + 13 * cj, PRIMES[(pi + cj) % len(PRIMES)])
                # Cubic edge bias retains some interior samples while strongly
                # populating the near-boundary region.
                edge_u = 0.5 * (u ** 3) if (sample + cj) % 2 == 0 else 1.0 - 0.5 * ((1.0 - u) ** 3)
                lo, hi = ranges[key]
                candidate[key] = _clip(lo + edge_u * (hi - lo), ranges[key], count=key in COUNT_PARAMETERS)
            if normalized_distance(candidate, base, ranges) < 0.10:
                continue
            margins = constraint_margins(family, candidate)
            min_name, min_value = min(margins.items(), key=lambda item: item[1])
            # Legal and outside the judge gray zone, yet genuinely close to a
            # relational boundary (<= 5% characteristic length).
            candidate_safe = 0.25 if "count_min" in min_name else safety_margin(candidate)
            if min_value <= candidate_safe or min_value > max(1.25, 0.05 * _scale(candidate)):
                continue
            pool.append((min_value / scale, min_name, candidate, list(changed)))
    pool.sort(key=lambda row: row[0])
    return pool


def make_boundary_states(family: str, base: dict[str, float], ranges: dict[str, tuple[float, float]], exclude: Iterable[dict[str, float]] = ()) -> list[tuple[dict[str, float], dict[str, Any]]]:
    pool = _boundary_pool(family, base, ranges)
    selected: list[tuple[dict[str, float], dict[str, Any]]] = []
    used_margins: set[str] = set()
    used_vectors: list[dict[str, float]] = []
    excluded_vectors = {tuple(sorted(v.items())) for v in exclude}
    # Prefer four distinct active constraint boundaries.
    for _, margin_name, candidate, changed in pool:
        if tuple(sorted(candidate.items())) in excluded_vectors:
            continue
        if margin_name in used_margins:
            continue
        if any(normalized_distance(candidate, prior, ranges) < 0.075 for prior in used_vectors):
            continue
        margin_value = constraint_margins(family, candidate)[margin_name]
        selected.append((candidate, {
            "changed_parameters": changed,
            "boundary": True,
            "active_constraint": margin_name,
            "engineering_margin": margin_value,
        }))
        used_margins.add(margin_name)
        used_vectors.append(candidate)
        if len(selected) == 4:
            return selected
    # Some families expose only 2--3 independent inequalities. Fill remaining
    # slots with geometrically distinct approaches to the same boundary.
    for _, margin_name, candidate, changed in pool:
        if tuple(sorted(candidate.items())) in excluded_vectors:
            continue
        if any(normalized_distance(candidate, prior, ranges) < 0.055 for prior in used_vectors):
            continue
        margin_value = constraint_margins(family, candidate)[margin_name]
        selected.append((candidate, {
            "changed_parameters": changed,
            "boundary": True,
            "active_constraint": margin_name,
            "engineering_margin": margin_value,
        }))
        used_vectors.append(candidate)
        if len(selected) == 4:
            return selected
    raise RuntimeError(f"could not construct four legal near-boundary states for {family}")


def make_linked_states(
    family: str,
    base: dict[str, float],
    ranges: dict[str, tuple[float, float]],
    linked: tuple[str, ...],
) -> list[tuple[dict[str, float], dict[str, Any]]]:
    """Construct four coupled edits from the feasible common scale interval.

    The interval is derived from the task ranges before execution.  Candidates
    are then filtered only by engineering legality; no reference/model outcome
    enters this construction.
    """
    lower = max(float(ranges[k][0]) / float(base[k]) for k in linked)
    upper = min(float(ranges[k][1]) / float(base[k]) for k in linked)
    if not lower < 1.0 < upper:
        raise RuntimeError(f"linked scale interval for {family} does not straddle nominal")

    # Dense deterministic factor pool. Prefer substantial perturbations on
    # both sides while retaining four legal states for nominals near range edges.
    factors = [lower + (upper - lower) * i / 120.0 for i in range(1, 120)]
    legal: list[tuple[float, dict[str, float]]] = []
    for factor in factors:
        if abs(factor - 1.0) < 0.045:
            continue
        candidate = dict(base)
        for key in linked:
            candidate[key] = _clip(base[key] * factor, ranges[key], count=key in COUNT_PARAMETERS)
        if normalized_distance(candidate, base, ranges) < 0.10:
            continue
        if is_legal(family, candidate):
            legal.append((factor, candidate))

    below = sorted((row for row in legal if row[0] < 1.0), key=lambda r: r[0])
    above = sorted((row for row in legal if row[0] > 1.0), key=lambda r: r[0], reverse=True)
    chosen: list[tuple[float, dict[str, float]]] = []
    if len(below) >= 2 and len(above) >= 2:
        # Extreme plus mid-extreme on each side.
        chosen = [below[0], below[len(below)//2], above[len(above)//2], above[0]]
    else:
        legal.sort(key=lambda r: abs(math.log(r[0])), reverse=True)
        for row in legal:
            if all(abs(math.log(row[0] / prior[0])) > 0.055 for prior in chosen):
                chosen.append(row)
            if len(chosen) == 4:
                break
    if len(chosen) != 4:
        raise RuntimeError(f"could not construct four challenging linked edits for {family}")

    chosen.sort(key=lambda r: r[0])
    return [
        (candidate, {
            "changed_parameters": list(linked),
            "dependency_closure": list(linked),
            "preserve_ratio": list(linked),
            "scale_factor": factor,
        })
        for factor, candidate in chosen
    ]


def _count_targets(base_value: float, bounds: tuple[float, float]) -> list[float]:
    lo, hi = int(math.ceil(bounds[0])), int(math.floor(bounds[1]))
    nominal = int(round(base_value))
    span = max(1, hi - lo)
    candidates = [v for v in range(lo, hi + 1) if v != nominal and abs(v - nominal) / span >= 0.16]
    if len(candidates) < 4:
        candidates = [v for v in range(lo, hi + 1) if v != nominal]
    # Farthest values first; greedily retain separation between semantic states.
    candidates.sort(key=lambda v: (-abs(v - nominal), v))
    chosen: list[int] = []
    for v in candidates:
        if all(abs(v - prior) >= 1 for prior in chosen):
            chosen.append(v)
        if len(chosen) == 4:
            break
    if len(chosen) < 4:
        raise RuntimeError("semantic count parameter needs four distinct non-nominal values")
    return [float(v) for v in chosen]


def make_semantic_states(
    family: str,
    base: dict[str, float],
    ranges: dict[str, tuple[float, float]],
    semantic_contract: Iterable[str],
) -> list[tuple[dict[str, float], dict[str, Any]]]:
    levels = (-0.24, -0.12, 0.12, 0.24)
    states: list[tuple[dict[str, float], dict[str, Any]]] = []

    count_key = {
        "ribbed_angle": "rib_count",
        "gear_blank": "teeth",
        "hinge": "knuckle_count",
        "bottle_cap": "rib_count",
        "lattice_panel": "bar_count",
    }.get(family)
    count_values = _count_targets(base[count_key], ranges[count_key]) if count_key else None

    for idx, level in enumerate(levels):
        c = dict(base)
        changed: list[str] = []

        def setv(key: str, value: float) -> None:
            c[key] = _clip(value, ranges[key], count=key in COUNT_PARAMETERS)
            if abs(c[key] - base[key]) > 1e-9 and key not in changed:
                changed.append(key)

        if family == "mounting_bracket":
            setv("hole_spacing", base["hole_spacing"] * (1 + level))
            setv("hole_diameter", base["hole_diameter"] * (1 - 0.35 * level))
        elif family == "flange_plate":
            setv("bolt_circle", base["bolt_circle"] * (1 + level))
            setv("bolt_diameter", base["bolt_diameter"] * (1 - 0.30 * level))
        elif family == "stepped_shaft":
            setv("shoulder_length", base["shoulder_length"] * (1 + level))
            setv("shoulder_diameter", base["shoulder_diameter"] * (1 + 0.45 * level))
        elif family == "electronics_enclosure":
            # Strengthen/thin the shell while approximately preserving the
            # nominal internal footprint: a semantic dependency closure.
            delta = level * 0.42 * (ranges["wall"][1] - ranges["wall"][0])
            setv("wall", base["wall"] + delta)
            actual_delta = c["wall"] - base["wall"]
            setv("length", base["length"] + 2 * actual_delta)
            setv("width", base["width"] + 2 * actual_delta)
        elif family == "belt_pulley":
            setv("hub_length", base["hub_length"] * (1 + level))
            setv("hub_diameter", base["hub_diameter"] * (1 + 0.50 * level))
        elif family == "ribbed_angle":
            assert count_key and count_values
            setv(count_key, count_values[idx])
            ratio = base[count_key] / c[count_key]
            setv("rib_thickness", base["rib_thickness"] * min(1.35, max(0.70, ratio ** 0.45)))
        elif family == "bolt_pattern_plate":
            setv("hole_diameter", base["hole_diameter"] * (1 + 0.50 * level))
            setv("hole_spacing_x", base["hole_spacing_x"] * (1 + level))
            setv("hole_spacing_y", base["hole_spacing_y"] * (1 + 0.70 * level))
        elif family == "pipe_clamp":
            setv("lug_length", base["lug_length"] * (1 + level))
            setv("lug_thickness", base["lug_thickness"] * (1 + 0.55 * level))
        elif family == "gear_blank":
            assert count_key and count_values
            setv(count_key, count_values[idx])
            # Vary tooth radial depth with count so the semantic edit cannot be
            # satisfied by changing only the discrete loop count.
            setv("root_diameter", base["root_diameter"] * (1 - 0.16 * level))
        elif family == "hinge":
            assert count_key and count_values
            setv(count_key, count_values[idx])
            setv("barrel_diameter", base["barrel_diameter"] * (1 + 0.35 * level))
            setv("pin_diameter", base["pin_diameter"] * (1 + 0.20 * level))
        elif family == "drawer_handle":
            # Ergonomic-rise intervention: the grip elevation and the support
            # posts co-vary.  Mount spacing is intentionally left fixed so a
            # candidate cannot satisfy the edit by merely sliding the bosses
            # while leaving the handle profile stale.
            setv("grip_height", base["grip_height"] * (1 + 1.05 * level))
            setv("mount_height", base["mount_height"] * (1 + 0.75 * level))
        elif family == "bottle_cap":
            assert count_key and count_values
            setv(count_key, count_values[idx])
            setv("rib_depth", base["rib_depth"] * (base[count_key] / c[count_key]) ** 0.35)
        elif family == "lattice_panel":
            assert count_key and count_values
            setv(count_key, count_values[idx])
            setv("bar_thickness", base["bar_thickness"] * (base[count_key] / c[count_key]) ** 0.50)
        elif family == "bearing_housing":
            setv("bore_diameter", base["bore_diameter"] * (1 + level))
            setv("outer_diameter", base["outer_diameter"] * (1 + 0.55 * level))
            setv("base_width", base["base_width"] * (1 + 0.30 * level))
        else:
            raise KeyError(family)

        if len(changed) < 2:
            raise RuntimeError(f"semantic state for {family} collapsed to fewer than two parameter changes")
        if not is_legal(family, c):
            # Reduce semantic intensity, never task constraints.
            # This changes the intervention magnitude while retaining the same
            # dependency closure and a >=10% design-space move requirement.
            for shrink in (0.82, 0.68, 0.56):
                # Recurse via interpolation from base to the already-defined
                # semantic target; discrete count remains fixed.
                trial = dict(base)
                for key in changed:
                    if key == count_key:
                        trial[key] = c[key]
                    else:
                        trial[key] = _clip(base[key] + shrink * (c[key] - base[key]), ranges[key], count=key in COUNT_PARAMETERS)
                if normalized_distance(trial, base, ranges) >= 0.10 and is_legal(family, trial):
                    c = trial
                    break
            else:
                raise RuntimeError(f"semantic intervention is infeasible for {family} template")
        if normalized_distance(c, base, ranges) < 0.10:
            raise RuntimeError(f"semantic intervention too weak for {family}")
        states.append((c, {
            "changed_parameters": [k for k in c if abs(c[k] - base[k]) > 1e-9],
            "dependency_closure": [k for k in c if abs(c[k] - base[k]) > 1e-9],
            "semantic_contract": list(semantic_contract),
            "semantic_level": level,
        }))

    vectors = [tuple(sorted(c.items())) for c, _ in states]
    if len(set(vectors)) != 4:
        raise RuntimeError(f"semantic states are not unique for {family}")
    return states
