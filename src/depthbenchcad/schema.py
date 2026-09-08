"""Portable records used by the benchmark.

The JSONL representation is deliberately dependency free so logs produced in a
CAD worker can be moved into the statistical analysis environment unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Iterable


EDIT_TYPES = ("local", "boundary", "linked", "semantic")


@dataclass(frozen=True)
class EditState:
    state_id: str
    edit_type: str
    parameters: dict[str, float]
    units: dict[str, str] = field(default_factory=dict)
    legal_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    expected_relations: dict[str, Any] = field(default_factory=dict)
    tolerance: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.edit_type not in EDIT_TYPES:
            raise ValueError(f"unknown edit type: {self.edit_type}")


@dataclass(frozen=True)
class Template:
    template_id: str
    task_family: str
    description: str
    parameters: dict[str, float]
    parameter_ranges: dict[str, tuple[float, float]]
    constraints: dict[str, Any]
    states: tuple[EditState, ...]
    program_path: str | None = None

    def __post_init__(self) -> None:
        if not self.states:
            raise ValueError("a template needs at least one frozen edit state")
        if len({s.state_id for s in self.states}) != len(self.states):
            raise ValueError("edit state ids must be unique within a template")


@dataclass
class GenerationRecord:
    system_id: str
    template_id: str
    generation_id: int
    seed: int
    program: str
    initial_valid: bool
    generation_seconds: float = 0.0
    build_seconds: float = 0.0
    failure_stage: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditRecord:
    system_id: str
    template_id: str
    generation_id: int
    state_id: str
    edit_type: str
    failed: bool | None
    initial_valid: bool
    execution_seconds: float = 0.0
    failure_stage: str | None = None
    automatic_label: bool = True
    expert_label: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_observed(self) -> bool:
        """Whether this row has a model outcome rather than an infrastructure gap."""
        return self.failed is not None


def to_jsonable(record: Any) -> Any:
    """Convert dataclasses, tuples and mappings to JSON-compatible values."""
    if is_dataclass(record):
        return {f.name: to_jsonable(getattr(record, f.name)) for f in fields(record)}
    if isinstance(record, tuple):
        return [to_jsonable(v) for v in record]
    if isinstance(record, list):
        return [to_jsonable(v) for v in record]
    if isinstance(record, dict):
        return {str(k): to_jsonable(v) for k, v in record.items()}
    return record


def template_from_dict(value: dict[str, Any]) -> Template:
    states = tuple(
        EditState(
            state_id=s["state_id"],
            edit_type=s["edit_type"],
            parameters=dict(s.get("parameters", {})),
            units=dict(s.get("units", {})),
            legal_ranges={k: tuple(v) for k, v in s.get("legal_ranges", {}).items()},
            expected_relations=dict(s.get("expected_relations", {})),
            tolerance=dict(s.get("tolerance", {})),
        )
        for s in value["states"]
    )
    return Template(
        template_id=value["template_id"],
        task_family=value["task_family"],
        description=value.get("description", ""),
        parameters=dict(value.get("parameters", {})),
        parameter_ranges={k: tuple(v) for k, v in value.get("parameter_ranges", {}).items()},
        constraints=dict(value.get("constraints", {})),
        states=states,
        program_path=value.get("program_path"),
    )


def group_audits(records: Iterable[AuditRecord]) -> dict[tuple[str, str, int], list[AuditRecord]]:
    grouped: dict[tuple[str, str, int], list[AuditRecord]] = {}
    for record in records:
        grouped.setdefault((record.system_id, record.template_id, record.generation_id), []).append(record)
    return grouped
