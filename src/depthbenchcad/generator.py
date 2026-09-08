"""Input adapter for model-generated CadQuery programs."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from .executor import run_cad_program_detailed
from .judge import checks_to_jsonable, judge_geometry
from .schema import GenerationRecord, Template


def stable_seed(master_seed: int, system_number: int, template_number: int, generation_number: int) -> int:
    raw = f"{master_seed}:{system_number}:{template_number}:{generation_number}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def validate_generation_input(path: str | Path) -> list[dict[str, Any]]:
    """Read model outputs without changing or fabricating their program text."""
    source = Path(path)
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {lineno}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"line {lineno}: each manifest row must be an object")
        required = {"system_id", "template_id", "generation_id"}
        missing = required - row.keys()
        if missing or not (row.get("program_path") or row.get("program")):
            raise ValueError(f"line {lineno}: missing {sorted(missing)} or program/program_path")
        if not isinstance(row.get("system_id"), str) or not row["system_id"].strip():
            raise ValueError(f"line {lineno}: system_id must be a non-empty string")
        try:
            row["generation_id"] = int(row["generation_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"line {lineno}: generation_id must be an integer") from exc
        if row["generation_id"] < 0:
            raise ValueError(f"line {lineno}: generation_id must be non-negative")
        rows.append(row)
    return rows


def _resolve_program_path(value: str | Path, base_dir: str | Path | None = None) -> Path:
    """Resolve a manifest path while supporting repository-root and manifest paths.

    Historical manifests used both ``data/programs/foo.py`` (relative to the
    repository) and ``../programs/foo.py`` (relative to the manifest).  We
    preserve both conventions, choosing the first existing path.
    """
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    roots: list[Path] = []
    if base_dir is not None:
        base = Path(base_dir).expanduser().resolve()
        roots.append(base)
        roots.extend(base.parents)
    roots.append(Path.cwd().resolve())
    seen: set[Path] = set()
    for root in roots:
        resolved = (root / candidate).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    # Return a deterministic resolved path so the worker records the useful
    # missing-file location rather than a process-dependent relative string.
    return (roots[0] / candidate).resolve()


def execute_generation(
    template: Template,
    row: dict[str, Any],
    materialized_program: str | None = None,
    *,
    manifest_dir: str | Path | None = None,
    materialized_dir: str | Path | None = None,
) -> GenerationRecord:
    program_path = row.get("program_path") or materialized_program
    if not program_path and row.get("program"):
        # Keep inline model output executable for the full audit pass.  A
        # caller-supplied directory makes the source part of the output bundle;
        # otherwise use a private temporary file for library callers.
        if materialized_dir is None:
            handle = tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", prefix="depthbenchcad-generation-", delete=False, encoding="utf-8"
            )
            with handle:
                handle.write(str(row["program"]))
            program_path = handle.name
        else:
            target_dir = Path(materialized_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{row['system_id']}-{template.template_id}-{int(row['generation_id'])}.py"
            # IDs are user-controlled strings; reject separators instead of
            # allowing an inline source to escape the materialization folder.
            if Path(safe_name).name != safe_name or any(char in safe_name for char in ("/", "\\", ":")):
                raise ValueError("manifest identifiers cannot be used as a program filename")
            target = (target_dir / safe_name).resolve()
            if target.parent != target_dir.resolve():
                raise ValueError("materialized program path escaped its output directory")
            target.write_text(str(row["program"]), encoding="utf-8")
            program_path = str(target)
    if not program_path:
        raise ValueError("program path is required")
    program_path = _resolve_program_path(program_path, manifest_dir)
    ok, stage, elapsed, detail, metrics = run_cad_program_detailed(program_path, template.parameters, timeout_seconds=60)
    nominal_judge = None
    if ok:
        nominal_judge = judge_geometry(template, None, metrics)
        if nominal_judge.status == "fail":
            ok = False
            stage = nominal_judge.failure_stage or "nominal_constraint"
    return GenerationRecord(
        system_id=row["system_id"],
        template_id=row["template_id"],
        generation_id=int(row["generation_id"]),
        seed=int(row.get("seed", 0)),
        program=row.get("program", str(program_path)),
        initial_valid=ok,
        generation_seconds=float(row.get("generation_seconds", 0.0)),
        build_seconds=elapsed,
        failure_stage=stage,
        metadata={
            "worker_detail": detail,
            "program_path": str(program_path),
            "baseline_metrics": metrics,
            "nominal_judge_status": nominal_judge.status if nominal_judge is not None else None,
            "nominal_review_required": bool(nominal_judge is not None and nominal_judge.status == "review"),
            "nominal_judge": checks_to_jsonable(nominal_judge) if nominal_judge is not None else [],
            **dict(row.get("metadata", {})),
        },
    )
