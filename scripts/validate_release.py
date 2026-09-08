"""Validate the canonical DepthBenchCAD release."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from depthbenchcad.io import load_audits, load_templates, read_jsonl
from depthbenchcad.schema import EDIT_TYPES


def validate_record_pool(path: str, expected_records: int, expected_generations: int) -> dict[str, object]:
    records = load_audits(path)
    assert len(records) == expected_records
    assert all(r.failed is not None for r in records)
    keys = {(r.system_id, r.template_id, r.generation_id, r.state_id) for r in records}
    assert len(keys) == len(records)
    systems = sorted({r.system_id for r in records})
    assert systems == ["S1", "S2", "S3", "S4", "S5"]
    by_program = Counter((r.system_id, r.template_id, r.generation_id) for r in records)
    assert set(by_program.values()) == {16}
    by_template_system = Counter((r.system_id, r.template_id) for r in records)
    assert set(by_template_system.values()) == {16 * expected_generations}
    edit_counts = Counter(r.edit_type for r in records)
    assert set(edit_counts) == set(EDIT_TYPES)
    return {
        "records": len(records),
        "systems": systems,
        "programs": len(by_program),
        "edit_counts": dict(edit_counts),
    }


def validate_generation_pool(path: str, audit_path: str, expected_records: int, expected_generations: int) -> dict[str, object]:
    rows = read_jsonl(path)
    audits = load_audits(audit_path)
    assert len(rows) == expected_records
    assert all(r.get("record_type") == "generation_record" for r in rows)
    assert all(r.get("candidate_program_available") is False for r in rows)
    keys = {(r["system_id"], r["template_id"], int(r["generation_id"])) for r in rows}
    assert len(keys) == len(rows)
    systems = sorted({r["system_id"] for r in rows})
    assert systems == ["S1", "S2", "S3", "S4", "S5"]
    by_template_system = Counter((r["system_id"], r["template_id"]) for r in rows)
    assert set(by_template_system.values()) == {expected_generations}
    assert all(int(r["audited_state_count"]) == 16 for r in rows)
    assert all(sum(int(v) for v in r["failure_count_by_edit_type"].values()) == int(r["failure_count"]) for r in rows)

    audit_groups: dict[tuple[str, str, int], list] = defaultdict(list)
    for a in audits:
        audit_groups[(a.system_id, a.template_id, int(a.generation_id))].append(a)
    assert set(audit_groups) == keys
    for r in rows:
        key = (r["system_id"], r["template_id"], int(r["generation_id"]))
        ar = audit_groups[key]
        assert len(ar) == 16
        failed = [x for x in ar if x.failed]
        assert len(failed) == int(r["failure_count"])
        assert {x.state_id for x in failed} == set(r["failed_state_ids"])
        by_type = Counter(x.edit_type for x in failed)
        assert {k: by_type.get(k, 0) for k in EDIT_TYPES} == {k: int(r["failure_count_by_edit_type"].get(k, 0)) for k in EDIT_TYPES}
    return {"records": len(rows), "systems": systems}


def main() -> int:
    templates = load_templates("data/templates/depthbenchcad_tasks.json")
    assert len(templates) == 120
    env = Counter(t.constraints["environment"] for t in templates)
    split = Counter((t.constraints["environment"], t.constraints["split"]) for t in templates)
    families = {e: len({t.task_family for t in templates if t.constraints["environment"] == e}) for e in ("A", "B")}
    assert env == Counter({"A": 72, "B": 48})
    assert split[("A", "calibration")] == 24 and split[("A", "test")] == 48
    assert split[("B", "calibration")] == 12 and split[("B", "test")] == 36
    assert families == {"A": 8, "B": 6}
    assert all(len(t.states) == 16 for t in templates)
    assert all(Counter(s.edit_type for s in t.states) == Counter({k: 4 for k in EDIT_TYPES}) for t in templates)

    pool_a = validate_record_pool("data/records/depthbenchcad_A_audits.jsonl", 28800, 5)
    pool_b = validate_record_pool("data/records/depthbenchcad_B_audits.jsonl", 15360, 4)
    generations_a = validate_generation_pool("data/generations/depthbenchcad_A_generations.jsonl", "data/records/depthbenchcad_A_audits.jsonl", 1800, 5)
    generations_b = validate_generation_pool("data/generations/depthbenchcad_B_generations.jsonl", "data/records/depthbenchcad_B_audits.jsonl", 960, 4)
    experts = read_jsonl("data/records/depthbenchcad_A_expert_annotations.jsonl")
    assert len(experts) == 800
    assert len({(r["system_id"], r["template_id"], int(r["generation_id"]), r["state_id"]) for r in experts}) == 800

    report = {
        "templates": len(templates),
        "families": families,
        "splits": {f"{e}_{s}": n for (e, s), n in split.items()},
        "record_pool_A": pool_a,
        "record_pool_B": pool_b,
        "generation_pool_A": generations_a,
        "generation_pool_B": generations_b,
        "expert_record_rows": len(experts),
        "status": "ok",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
