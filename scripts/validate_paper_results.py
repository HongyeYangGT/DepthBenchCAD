"""Validate the released record pool against the paper's core numerical logic.

This validator deliberately checks mechanism-level consistency rather than
requiring every Monte-Carlo percentage to be byte-identical to the paper.
"""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path


def read_csv(path: Path):
    with path.open(newline='',encoding='utf-8') as f:
        return list(csv.DictReader(f))

def relerr(a,b):
    return abs(a-b)/max(abs(b),1e-12)

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--results',default='results/reproduced')
    p.add_argument('--paper',default='data/paper_results.json')
    args=p.parse_args()
    root=Path(args.results); paper=json.load(open(args.paper,encoding='utf-8'))
    errors=[]; notes=[]

    # Table 3: this is the strongest deterministic check because the paper's
    # main mechanism is identified by these finite-pool variance trade-offs.
    t3={r['system']:r for r in read_csv(root/'table3_fixed_depth_A.csv')}
    ref=paper['table_3_environment_a_fixed_depth']['systems']
    for s in sorted(ref):
        for k in (4,8,16):
            row=t3[s]; rr=ref[s][f'k{k}']
            if int(row[f'q_k{k}'])!=rr['q'] or int(row[f'g_k{k}'])!=rr['g']:
                errors.append(f'Table3 {s} k={k}: q/g mismatch')
            if relerr(float(row[f'J_k{k}']),rr['J'])>0.02:
                errors.append(f'Table3 {s} k={k}: J differs by >2%')
            pm=float(row[f'program_MSE_k{k}'])
            if rr['program_MSE']==0:
                if abs(pm)>1e-12: errors.append(f'Table3 {s} k={k}: program MSE should be zero')
            elif relerr(pm,rr['program_MSE'])>0.03:
                errors.append(f'Table3 {s} k={k}: program MSE differs by >3%')

    summary=json.load(open(root/'analysis_summary.json',encoding='utf-8'))
    if summary['benefit_direction_A']['accuracy'] < 0.9:
        errors.append('environment A benefit-direction accuracy below 9/10')

    # Interval logic: three-level intervals should recover nominal coverage and
    # improve on the program-independent approximation.
    cov3=sum(v['three_level']['coverage'] for v in summary['interval_coverage'].values())/5
    cov2=sum(v['program_independent']['coverage'] for v in summary['interval_coverage'].values())/5
    if not (0.90 <= cov3 <= 0.99): errors.append('three-level interval coverage outside [0.90,0.99]')
    if cov3 <= cov2 + 0.03: errors.append('three-level interval does not materially improve coverage')

    # Table 7: the released B pool should preserve the medium-depth optimum and
    # remain close to the reported fixed-depth curve.
    t7={r['method']:r for r in read_csv(root/'table7_cross_environment.csv')}
    fixed=['fixed_k4','fixed_k8','fixed_k9','fixed_k10','fixed_k12','fixed_k16']
    best=min(fixed,key=lambda m:float(t7[m]['mean_J']))
    if best!='fixed_k10': errors.append(f'environment B fixed-depth optimum is {best}, expected fixed_k10')
    pref=paper['table_7_environment_b_efficiency']
    for m in fixed:
        if relerr(float(t7[m]['mean_J']),float(pref[m]['mean_J']))>0.12:
            errors.append(f'Table7 {m}: mean J differs by >12%')
    loso=t7['leave_one_system_out']
    if abs(float(loso['mean_k'])-11.6)>1.0: errors.append('B LOSO mean k too far from paper')
    if relerr(float(loso['mean_J']),0.786)>0.10: errors.append('B LOSO mean J differs by >10%')

    # Stability need not match each percentile, but task-family composition must
    # cause a material tail in at least one held-out-family analysis.
    t6=read_csv(root/'table6_stability.csv')
    if max(float(r['lofo_p90_regret']) for r in t6) < 1.20:
        errors.append('leave-one-family-out tail regret is too weak')

    # Table 8: automatic risks should match the reported A pool and the expert
    # review should preserve ranking plus the stronger S4/S5 underestimation.
    t8={r['system']:r for r in read_csv(root/'table8_expert_validation.csv')}
    for s,rr in paper['table_8_automatic_and_expert_risk'].items():
        if abs(float(t8[s]['automatic_risk'])-rr['automatic'])>0.003:
            errors.append(f'Table8 {s}: automatic risk differs by >0.003')
    er=[float(t8[s]['expert_reference_risk']) for s in ('S1','S2','S3','S4','S5')]
    if er != sorted(er): errors.append('expert-reference system ranking is not monotone')
    if float(t8['S4']['expert_reference_risk']) <= float(t8['S4']['automatic_risk']): errors.append('S4 expert risk should exceed automatic risk')
    if float(t8['S5']['expert_reference_risk']) <= float(t8['S5']['automatic_risk']): errors.append('S5 expert risk should exceed automatic risk')

    # Pairwise decisions should remain high-accuracy at the main budget.  Exact
    # percentages depend on replay count and are intentionally not hard-coded.
    t9=read_csv(root/'table9_pairwise_decisions.csv')
    if min(float(r['correct_rate_C1024']) for r in t9) < 0.95:
        errors.append('pairwise correct-decision rate below 95% at C0=1024')

    if errors:
        print('paper-result validation: FAILED')
        for e in errors: print(' -',e)
        return 1
    print('paper-result validation: OK')
    print(f' - Table 3 q/g and J/program-MSE match within frozen tolerances')
    print(f' - A benefit prediction: {summary["benefit_direction_A"]["correct"]}/{summary["benefit_direction_A"]["total"]}')
    print(f' - interval coverage: three-level={cov3:.3f}, program-independent={cov2:.3f}')
    print(f' - B fixed-depth optimum: {best}')
    print(f' - B LOSO: mean_k={float(loso["mean_k"]):.1f}, mean_J={float(loso["mean_J"]):.3f}')
    print(f' - expert sample: {summary["table8_expert_validation"]["sample_count"]}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
