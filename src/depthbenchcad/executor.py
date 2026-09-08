"""Real CAD execution adapter.

CadQuery is optional at install time. A worker fails loudly when the pinned CAD
environment is unavailable; it never invents an audit label.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .schema import AuditRecord, EditState, GenerationRecord, Template
from .judge import checks_to_jsonable, judge_geometry


WORKER_SOURCE = r"""
import hashlib
import importlib.util
import json
import math
import sys

module_path, params_path, output_path = sys.argv[1:]
params = json.load(open(params_path, encoding="utf-8"))
spec = importlib.util.spec_from_file_location("cad_program", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if not hasattr(module, "build"):
    raise RuntimeError("CAD program must define build(params)")
result = module.build(params)
if result is None:
    raise RuntimeError("build(params) returned None")
shape = result.val() if hasattr(result, "val") else result
metrics = {}
try:
    metrics["volume"] = float(shape.Volume())
except Exception:
    pass
try:
    metrics["surface_area"] = float(shape.Area())
except Exception:
    pass
try:
    metrics["solid_count"] = len(shape.Solids())
except Exception:
    pass
try:
    metrics["face_count"] = len(shape.Faces())
except Exception:
    pass
try:
    metrics["edge_count"] = len(shape.Edges())
except Exception:
    pass
try:
    metrics["vertex_count"] = len(shape.Vertices())
except Exception:
    pass
try:
    box = shape.BoundingBox()
    metrics.update({
        "bbox_x": float(box.xlen), "bbox_y": float(box.ylen), "bbox_z": float(box.zlen),
        "bbox_xmin": float(box.xmin), "bbox_xmax": float(box.xmax),
        "bbox_ymin": float(box.ymin), "bbox_ymax": float(box.ymax),
        "bbox_zmin": float(box.zmin), "bbox_zmax": float(box.zmax),
    })
except Exception:
    pass
try:
    center = shape.Center()
    metrics["center_x"] = float(center.x)
    metrics["center_y"] = float(center.y)
    metrics["center_z"] = float(center.z)
except Exception:
    pass
try:
    metrics["is_valid"] = bool(shape.isValid())
except Exception:
    pass
try:
    face_types = {}
    for face in shape.Faces():
        kind = str(face.geomType())
        face_types[kind] = face_types.get(kind, 0) + 1
    metrics["face_type_counts"] = face_types
except Exception:
    pass
try:
    circle_edges = []
    for edge in shape.Edges():
        if str(edge.geomType()) != "CIRCLE":
            continue
        center = edge.arcCenter()
        box = edge.BoundingBox()
        spans = [float(box.xlen), float(box.ylen), float(box.zlen)]
        axis = "xyz"[min(range(3), key=lambda i: spans[i])]
        circle_edges.append({
            "radius": float(edge.radius()),
            "center_x": float(center.x),
            "center_y": float(center.y),
            "center_z": float(center.z),
            "axis": axis,
        })
    metrics["circle_edges"] = circle_edges
except Exception:
    metrics["circle_edges"] = []
try:
    face_signature = []
    face_probes = []
    for face in shape.Faces():
        center = face.Center()
        box = face.BoundingBox()
        row = [
            round(float(face.Area()), 7),
            round(float(center.x), 7),
            round(float(center.y), 7),
            round(float(center.z), 7),
            round(float(box.xlen), 7),
            round(float(box.ylen), 7),
            round(float(box.zlen), 7),
        ]
        face_signature.append(row)
        probe = {
            "geom_type": str(face.geomType()),
            "area": float(face.Area()),
            "center_x": float(center.x), "center_y": float(center.y), "center_z": float(center.z),
            "bbox_x": float(box.xlen), "bbox_y": float(box.ylen), "bbox_z": float(box.zlen),
        }
        try:
            normal = face.normalAt()
            probe.update({"normal_x": float(normal.x), "normal_y": float(normal.y), "normal_z": float(normal.z)})
        except Exception:
            pass
        face_probes.append(probe)
    metrics["face_probes"] = face_probes
    face_signature.sort()
    payload = json.dumps(face_signature, separators=(",", ":")).encode("utf-8")
    metrics["geometry_signature"] = hashlib.sha256(payload).hexdigest()
except Exception:
    pass
if "volume" not in metrics or "solid_count" not in metrics:
    raise RuntimeError("build(params) did not return a measurable CadQuery shape")
json.dump({"ok": True, "metrics": metrics}, open(output_path, "w", encoding="utf-8"))
"""


class CadExecutionError(RuntimeError):
    pass


def run_cad_program_detailed(
    program_path: str | Path, parameters: dict[str, Any], timeout_seconds: float = 60.0,
    infrastructure_retries: int = 1,
) -> tuple[bool, str | None, float, str, dict[str, Any]]:
    """Execute a real program in a fresh subprocess.

    Only infrastructure failures are retried, matching the paper protocol;
    model/code/geometry failures return immediately and are never relabeled.
    """
    if not isinstance(infrastructure_retries, int) or isinstance(infrastructure_retries, bool) or infrastructure_retries < 0:
        raise ValueError("infrastructure_retries must be a non-negative integer")
    started = time.perf_counter()
    attempts = infrastructure_retries + 1
    last: tuple[bool, str | None, float, str, dict[str, Any]] | None = None
    for attempt in range(attempts):
        with tempfile.TemporaryDirectory(prefix="depthbenchcad-worker-") as tmp:
            params_path = Path(tmp) / "params.json"
            output_path = Path(tmp) / "result.json"
            params_path.write_text(json.dumps(parameters), encoding="utf-8")
            try:
                completed = subprocess.run(
                    [sys.executable, "-c", WORKER_SOURCE, str(Path(program_path).resolve()), str(params_path), str(output_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
            except subprocess.TimeoutExpired as exc:
                return False, "timeout", time.perf_counter() - started, str(exc), {}
            except OSError as exc:
                last = (False, "worker_error", time.perf_counter() - started, str(exc), {})
                if attempt + 1 < attempts:
                    continue
                return last
            elapsed = time.perf_counter() - started
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                stage = "environment" if "No module named 'cadquery'" in detail else "build"
                if stage == "environment":
                    last = (False, stage, elapsed, detail, {})
                    if attempt + 1 < attempts:
                        continue
                return False, stage, elapsed, detail, {}
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                last = (False, "worker_protocol", elapsed, str(exc), {})
                if attempt + 1 < attempts:
                    continue
                return last
            return True, None, elapsed, completed.stdout.strip(), dict(result.get("metrics", {}))
    assert last is not None
    return last


def run_cad_program(
    program_path: str | Path, parameters: dict[str, Any], timeout_seconds: float = 60.0
) -> tuple[bool, str | None, float, str]:
    """Compatibility wrapper that omits the geometry summary."""
    ok, stage, elapsed, detail, _ = run_cad_program_detailed(program_path, parameters, timeout_seconds)
    return ok, stage, elapsed, detail


def _validate_geometry(
    template: Template,
    state: EditState,
    baseline: dict[str, Any],
    observed: dict[str, Any],
) -> str | None:
    """Compatibility wrapper around the ordered Section 4.2 judge."""
    decision = judge_geometry(template, state, observed, baseline=baseline)
    return decision.failure_stage


def audit_generation(template: Template, generation: GenerationRecord, state: EditState, timeout_seconds: float = 30.0) -> AuditRecord:
    if generation.metadata.get("nominal_review_required"):
        return AuditRecord(
            generation.system_id, generation.template_id, generation.generation_id,
            state.state_id, state.edit_type, None, True,
            failure_stage="nominal_gray_zone_review", automatic_label=False,
            metadata={
                "review_required": True,
                "judge_status": "review",
                "nominal_judge": generation.metadata.get("nominal_judge", []),
            },
        )
    if not generation.initial_valid:
        if generation.failure_stage in {"environment", "worker_error", "worker_protocol"}:
            return AuditRecord(
                generation.system_id,
                generation.template_id,
                generation.generation_id,
                state.state_id,
                state.edit_type,
                None,
                False,
                failure_stage=generation.failure_stage,
                automatic_label=False,
                metadata={"worker_detail": generation.metadata.get("worker_detail", "")},
            )
        # Paper protocol: an invalid nominal program contributes failure on all
        # sixteen counterfactual states in the primary analysis.
        return AuditRecord(
            generation.system_id,
            generation.template_id,
            generation.generation_id,
            state.state_id,
            state.edit_type,
            True,
            False,
            failure_stage=(generation.failure_stage if generation.metadata.get("nominal_judge") else "initial_build"),
            metadata={"nominal_judge": generation.metadata.get("nominal_judge", [])},
        )
    program_path = generation.metadata.get("program_path") or generation.program or template.program_path
    if not program_path:
        raise CadExecutionError(f"no candidate program path for {generation.template_id}/{generation.generation_id}")
    ok, stage, elapsed, detail, metrics = run_cad_program_detailed(program_path, state.parameters, timeout_seconds)
    if not ok:
        infrastructure_gap = stage in {"environment", "worker_error", "worker_protocol"}
        return AuditRecord(
            system_id=generation.system_id,
            template_id=generation.template_id,
            generation_id=generation.generation_id,
            state_id=state.state_id,
            edit_type=state.edit_type,
            failed=None if infrastructure_gap else True,
            initial_valid=generation.initial_valid,
            execution_seconds=elapsed,
            failure_stage=stage,
            automatic_label=not infrastructure_gap,
            metadata={"worker_detail": detail, "metrics": metrics},
        )

    decision = judge_geometry(
        template,
        state,
        metrics,
        baseline=dict(generation.metadata.get("baseline_metrics", {})),
    )
    review = decision.status == "review"
    return AuditRecord(
        system_id=generation.system_id,
        template_id=generation.template_id,
        generation_id=generation.generation_id,
        state_id=state.state_id,
        edit_type=state.edit_type,
        failed=decision.failed,
        initial_valid=generation.initial_valid,
        execution_seconds=elapsed,
        failure_stage=decision.failure_stage,
        automatic_label=not review,
        metadata={
            "worker_detail": detail,
            "metrics": metrics,
            "judge_status": decision.status,
            "review_required": review,
            "judge_checks": checks_to_jsonable(decision),
        },
    )

