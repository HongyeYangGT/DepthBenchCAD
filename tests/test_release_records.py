import json
from collections import Counter
from pathlib import Path


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line.strip()]


def test_released_generation_cardinalities():
    a = _jsonl('data/generations/depthbenchcad_A_generations.jsonl')
    b = _jsonl('data/generations/depthbenchcad_B_generations.jsonl')
    assert len(a) == 1800
    assert len(b) == 960
    assert Counter(r['system_id'] for r in a) == Counter({f'S{i}': 360 for i in range(1, 6)})
    assert Counter(r['system_id'] for r in b) == Counter({f'S{i}': 192 for i in range(1, 6)})
    assert all(r['record_type'] == 'generation_record' for r in a + b)
    assert all(r['audited_state_count'] == 16 for r in a + b)


def test_released_state_cardinalities():
    a = _jsonl('data/records/depthbenchcad_A_audits.jsonl')
    b = _jsonl('data/records/depthbenchcad_B_audits.jsonl')
    assert len(a) == 28800
    assert len(b) == 15360
    assert len({(r['system_id'], r['template_id'], r['generation_id'], r['state_id']) for r in a + b}) == 44160


def test_generation_state_failure_identity():
    for env in ('A', 'B'):
        gens = _jsonl(f'data/generations/depthbenchcad_{env}_generations.jsonl')
        audits = _jsonl(f'data/records/depthbenchcad_{env}_audits.jsonl')
        counts = Counter((r['system_id'], r['template_id'], r['generation_id']) for r in audits if r['failed'])
        for g in gens:
            key = (g['system_id'], g['template_id'], g['generation_id'])
            assert counts[key] == g['failure_count']


def test_expert_sample_size():
    expert = _jsonl('data/records/depthbenchcad_A_expert_annotations.jsonl')
    assert len(expert) == 800
