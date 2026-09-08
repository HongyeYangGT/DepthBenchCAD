"""Render the numeric tables transcribed from the paper into CSV files.

This utility is a formatting/export tool.  It does not claim to recompute the
historical measurements; use ``reproduce_tables.py`` for record-level analysis.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from depthbenchcad.io import read_json


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="data/paper_results.json")
    p.add_argument("--out-dir", default="results/paper_reference")
    args = p.parse_args()
    data = read_json(args.source)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    t3 = []
    for system, values in data["table_3_environment_a_fixed_depth"]["systems"].items():
        row = {"system": system}
        for key, cell in values.items():
            row.update({f"{key}_{field}": value for field, value in cell.items()})
        t3.append(row)
    write_csv(out / "table3.csv", t3)

    t4 = []
    for system, values in data["table_4_environment_a_candidate_allocations"].items():
        row = {"system": system}
        for method, cell in values.items():
            row.update({f"{method}_{field}": value for field, value in cell.items()})
        t4.append(row)
    write_csv(out / "table4.csv", t4)

    write_csv(out / "table5.csv", [{"system": s, **v} for s, v in data["table_5_calibration_costs"].items() if isinstance(v, dict)])
    write_csv(out / "table6.csv", [{"system": s, **v} for s, v in data["table_6_split_stability"].items()])
    write_csv(out / "table7.csv", [{"method": m, **v} for m, v in data["table_7_environment_b_efficiency"].items()])
    write_csv(out / "table8.csv", [{"system": s, **v} for s, v in data["table_8_automatic_and_expert_risk"].items()])

    table9 = []
    for method, values in data["table_9_pairwise_decision_accuracy_percent"].items():
        row = {"method": method}
        if isinstance(values, dict):
            row.update(values)
        else:
            row["value"] = values
        table9.append(row)
    write_csv(out / "table9.csv", table9)
    print(f"Rendered paper-reference CSVs to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
