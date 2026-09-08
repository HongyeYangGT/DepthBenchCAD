# Minimal audit example

The sample manifest points the audit runner at one checked-in reference program so the complete execution path can be inspected without a model API.

```powershell
python scripts/run_audit.py `
  --templates data/templates/depthbenchcad_tasks.json `
  --generations examples/sample_generation.jsonl `
  --output examples/sample_audits.jsonl `
  --states 1
```

Remove `--states 1` to audit all 16 frozen states. The command also writes `examples/sample_audits_generations.jsonl`.
