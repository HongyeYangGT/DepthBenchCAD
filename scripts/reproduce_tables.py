"""Recompute the paper's analysis families from complete audit records.

This is the canonical analysis entry point.  It separates the calibration and
formal test pools by template metadata, freezes decisions before reading test
outcomes, and writes machine-readable tables plus a compact summary.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from depthbenchcad.io import load_audits, load_templates, read_json, read_jsonl, write_json
from depthbenchcad.paper_analysis import (
    benefit_direction_report,
    confidence_interval_coverage,
    cross_environment_transfer_report,
    expert_validation_report,
    filter_templates,
    fixed_depth_report,
    leave_one_family_out_stability,
    pairwise_decision_report,
    pooled_and_loso_report,
    random_template_split_stability,
    records_by_system,
    stratified_system_report,
    system_calibration_report,
)
from depthbenchcad.strategies import CostModel


def _template_metadata(templates):
    split = {}
    environment = {}
    family = {}
    for t in templates:
        split[t.template_id] = t.constraints.get("split")
        environment[t.template_id] = t.constraints.get("environment")
        family[t.template_id] = t.task_family
    return split, environment, family


def _split_system_records(records, split_map, env_map, environment):
    grouped = records_by_system(records)
    cal_ids = {tid for tid, env in env_map.items() if env == environment and split_map[tid] == "calibration"}
    test_ids = {tid for tid, env in env_map.items() if env == environment and split_map[tid] == "test"}
    full_ids = cal_ids | test_ids
    return (
        {s: filter_templates(rows, cal_ids) for s, rows in grouped.items()},
        {s: filter_templates(rows, test_ids) for s, rows in grouped.items()},
        {s: filter_templates(rows, full_ids) for s, rows in grouped.items()},
    )


def _costs(protocol, environment):
    return {
        system: CostModel(protocol["template_cost"], value, protocol["edit_cost"])
        for system, value in protocol["generation_costs"][environment].items()
    }


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    keys = []
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
    p.add_argument("--templates", default="data/templates/depthbenchcad_tasks.json")
    p.add_argument("--protocol", default="configs/paper_protocol.json")
    p.add_argument("--records-a", required=True)
    p.add_argument("--records-b", required=True)
    p.add_argument("--expert")
    p.add_argument("--out-dir", default="results/recomputed")
    p.add_argument("--replay-scale", type=float, default=1.0,
                   help="Scale Monte Carlo repeat counts; 1.0 is the frozen paper protocol")
    p.add_argument("--program-mse-mc", action="store_true",
                   help="Use the paper's Monte Carlo program-MSE replay instead of the exact SRSWOR expectation")
    args = p.parse_args()
    if args.replay_scale <= 0:
        raise SystemExit("--replay-scale must be positive")

    templates = load_templates(args.templates)
    protocol = read_json(args.protocol)
    split_map, env_map, family_map = _template_metadata(templates)
    a_records = load_audits(args.records_a)
    b_records = load_audits(args.records_b)
    a_cal, a_test, a_full = _split_system_records(a_records, split_map, env_map, "A")
    b_cal, b_test, b_full = _split_system_records(b_records, split_map, env_map, "B")
    costs_a = _costs(protocol, "A")
    costs_b = _costs(protocol, "B")
    budget = float(protocol["main_budget"])
    fixed_depths = tuple(protocol["fixed_audit_depths"])
    transitions = tuple(tuple(x) for x in protocol["prediction_transitions"])

    systems = sorted(a_test)
    if systems != sorted(protocol["systems"]):
        raise SystemExit(f"records name systems {systems}, expected {sorted(protocol['systems'])}")

    # Table 3 + benefit-direction analysis.
    fixed = fixed_depth_report(
        a_cal, a_test, costs_a, budget, fixed_depths,
        program_mse_repeats=(max(1, int(protocol["bootstrap"]["program_mse_repeats"] * args.replay_scale)) if args.program_mse_mc else 0),
        seed=protocol["master_seed"],
    )
    benefit_a = benefit_direction_report(fixed, transitions)
    fixed_b = fixed_depth_report(b_cal, b_test, costs_b, budget, fixed_depths, program_mse_repeats=0)
    benefit_b = benefit_direction_report(fixed_b, transitions)

    # Table 4 allocation families.
    pooled_loso_a = pooled_and_loso_report(a_cal, a_test, costs_a, budget)
    system_a = system_calibration_report(a_cal, a_test, costs_a, budget)
    stratified_a = stratified_system_report(a_cal, a_test, costs_a, budget)

    # Table 5 cost accounting exactly follows q[cT+g(cI+k*cE)].
    full_cal_cost = {
        s: costs_a[s].total(protocol["environments"]["A"]["calibration"], protocol["environments"]["A"]["generations"], 16)
        for s in systems
    }
    pilot_cal_cost = {s: costs_a[s].total(8, 2, 16) for s in systems}

    # Table 6 stability. Random split uses the complete A pool; LOFO holds out one whole family.
    family_a = {tid: fam for tid, fam in family_map.items() if env_map[tid] == "A"}
    random_stability = random_template_split_stability(
        a_full, family_a, costs_a, budget,
        calibration_per_family=3, repeats=40, seed=protocol["master_seed"],
    )
    lofo_stability = leave_one_family_out_stability(a_full, family_a, costs_a, budget)

    # Table 7 transfer.
    transfer = cross_environment_transfer_report(
        a_cal, a_test, b_cal, b_test, costs_a, costs_b, budget,
        tuple(k for k in fixed_depths if k != 1),
        target_template_family={tid: fam for tid, fam in family_map.items() if env_map[tid] == "B"},
    )

    # Interval coverage and Table 9 use the frozen replay counts.
    interval_cfg = protocol["interval_experiment"]
    interval_repeats = max(1, int(interval_cfg["repeats"] * args.replay_scale))
    interval = {}
    for i, system in enumerate(systems):
        interval[system] = {
            name: result.__dict__
            for name, result in confidence_interval_coverage(
                a_test[system], interval_cfg["q"], interval_cfg["g"], interval_cfg["k"],
                repeats=interval_repeats, seed=protocol["master_seed"] + i * 1009,
            ).items()
        }

    pair_repeats = max(1, int(protocol["bootstrap"]["program_mse_repeats"] * args.replay_scale))
    pairwise = pairwise_decision_report(
        a_cal, a_test, costs_a, protocol["budgets"],
        fixed_depths=(8, 9, 10), repeats=pair_repeats, seed=protocol["master_seed"],
    )

    expert = None
    if args.expert:
        expert = expert_validation_report(a_records, read_jsonl(args.expert))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    summary = {
        "analysis_schema_version": 1,
        "records": {"A": args.records_a, "B": args.records_b, "expert": args.expert},
        "replay_scale": args.replay_scale,
        "table3_fixed_depth_A": fixed,
        "benefit_direction_A": benefit_a,
        "benefit_direction_B": benefit_b,
        "table4_pooled_and_loso_A": pooled_loso_a,
        "table4_system_calibration_A": system_a,
        "table4_stratified_A": stratified_a,
        "table5_calibration_costs": {
            s: {"full": full_cal_cost[s], "pilot": pilot_cal_cost[s], "pilot_over_formal": pilot_cal_cost[s] / budget}
            for s in systems
        },
        "table6_random_split": random_stability,
        "table6_leave_one_family_out": lofo_stability,
        "table7_cross_environment": transfer,
        "interval_coverage": interval,
        "table8_expert_validation": expert,
        "table9_pairwise_decisions": pairwise,
    }
    write_json(out / "analysis_summary.json", summary)

    table3_rows = []
    for system in systems:
        row = {"system": system}
        for k in (4, 8, 16):
            cell = fixed[system][k]
            row.update({f"q_k{k}": cell["q"], f"g_k{k}": cell["g"], f"J_k{k}": cell["J"], f"program_MSE_k{k}": cell["program_MSE"]})
        table3_rows.append(row)
    _write_rows(out / "table3_fixed_depth_A.csv", table3_rows)

    table4_rows = []
    for system in systems:
        pooled = pooled_loso_a["pooled"][system]
        sys = system_a[system]
        strat = stratified_a[system]
        table4_rows.append({
            "system": system,
            "pooled_q": pooled["q"], "pooled_g": pooled["g"], "pooled_k": pooled["k"], "pooled_J": pooled["J"],
            "system_q": sys["q"], "system_g": sys["g"], "system_k": sys["k"], "system_J": sys["J"],
            "stratified_q": strat["q"], "stratified_g": strat["g"], "stratified_k": strat["k"], "stratified_J": strat["J"],
        })
    _write_rows(out / "table4_candidate_allocations_A.csv", table4_rows)

    _write_rows(out / "table5_calibration_costs.csv", [
        {"system": s, "full_calibration_cost": full_cal_cost[s], "small_calibration_cost": pilot_cal_cost[s], "pilot_over_formal": pilot_cal_cost[s] / budget}
        for s in systems
    ])
    _write_rows(out / "table6_stability.csv", [
        {"system": s, **{f"random_{k}": v for k, v in random_stability[s].items()}, **{f"lofo_{k}": v for k, v in lofo_stability[s].items()}}
        for s in systems
    ])
    _write_rows(out / "table7_cross_environment.csv", [
        {"method": method, **values} for method, values in transfer.items()
    ])
    if expert:
        _write_rows(out / "table8_expert_validation.csv", [
            {"system": s, **values} for s, values in expert["systems"].items()
        ])
    table9_rows = []
    methods = sorted(next(iter(pairwise.values())))
    for method in methods:
        row = {"method": method}
        for b in protocol["budgets"]:
            row[f"correct_rate_C{b}"] = pairwise[str(b)][method]["correct_rate"]
            row[f"tie_rate_C{b}"] = pairwise[str(b)][method]["tie_rate"]
        table9_rows.append(row)
    _write_rows(out / "table9_pairwise_decisions.csv", table9_rows)

    print(json.dumps({
        "output": str(out),
        "benefit_A_accuracy": benefit_a["accuracy"],
        "benefit_B_accuracy": benefit_b["accuracy"],
        "pooled_A_rule": pooled_loso_a["pooled_rule"],
        "interval_mean_three_level": sum(interval[s]["three_level"]["coverage"] for s in systems) / len(systems),
        "interval_mean_program_independent": sum(interval[s]["program_independent"]["coverage"] for s in systems) / len(systems),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
