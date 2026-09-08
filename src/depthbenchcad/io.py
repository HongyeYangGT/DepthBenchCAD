"""JSON and JSONL readers/writers for benchmark artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, TypeVar

from .schema import AuditRecord, GenerationRecord, Template, template_from_dict, to_jsonable

T = TypeVar("T")


def write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path: str | Path, records: Iterable[Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        for record in records:
            value = to_jsonable(record) if hasattr(record, "__dataclass_fields__") else record
            f.write(json.dumps(value, ensure_ascii=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def load_templates(path: str | Path) -> list[Template]:
    source = Path(path)
    payload = read_json(source)
    values = payload["templates"] if isinstance(payload, dict) and "templates" in payload else payload
    resolved: list[Template] = []
    for value in values:
        item = dict(value)
        program_path = item.get("program_path")
        if program_path and not Path(program_path).is_absolute():
            item["program_path"] = str((source.parent / program_path).resolve())
        resolved.append(template_from_dict(item))
    return resolved


def load_audits(path: str | Path) -> list[AuditRecord]:
    return [AuditRecord(**v) for v in read_jsonl(path)]


def load_generations(path: str | Path) -> list[GenerationRecord]:
    return [GenerationRecord(**v) for v in read_jsonl(path)]
