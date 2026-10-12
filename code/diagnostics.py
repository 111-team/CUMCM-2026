"""补充诊断：预报误差、场景配对和储能反馈保留规则。"""
import json
from pathlib import Path
import numpy as np

from model import (DT, EINIT, ETA, load_data, forecast_all, residual_scenarios,
                   optimize, execute, execute_reserve)


def metrics(error, truth):
    error = np.asarray(error, float); truth = np.asarray(truth, float)
    return {
        'mae': float(np.mean(np.abs(error))),
        'rmse': float(np.sqrt(np.mean(error**2))),
        'wape': float(np.sum(np.abs(error)) / max(np.sum(np.abs(truth)), 1e-12)),
    }


def run(data_root, out_root):
    out_root = Path(out_root); out_root.mkdir(parents=True, exist_ok=True)
    data = load_data(data_root); fc, _, selected = forecast_all(data)
    report = {'selected_forecasts': selected, 'historical': {}, 'issued_pv': {},
              'scenario_shuffle': {}, 'feedback_benchmark': {}}
    sl = slice(31, 365)
    for key in ('load', 'pv', 'price'):
        report['historical'][key] = metrics(fc[key][sl] - data[key][sl], data[key][sl])
    # 同一目标6小时块和从发布时间起的剩余全天，均按论文插值方法评价。
    for issue in range(4):
        start = issue * 36
        block = slice(start, min(start + 36, 144))
        rest = slice(start, 144)
        truth_block, truth_rest = data['pv'][sl, block], data['pv'][sl, rest]
        pred = fc['issued'][sl, issue]
        report['issued_pv'][str(issue * 6)] = {
            'target_hours': [issue*6, issue*6+6],
            'historical_same_block': metrics(fc['pv'][sl,block]-truth_block,truth_block),
            'zero_same_block': metrics(fc['issued'][sl,0,block]-truth_block,truth_block),
            'six_hour': metrics(pred[:, block] - truth_block, truth_block),
            'remaining_day': metrics(pred[:, rest] - truth_rest, truth_rest),
            'blend_weight': selected['pv_blend_weights'][issue],
            'blend_same_block': metrics(fc['issued_blend'][sl,issue,block]-truth_block,truth_block),
        }
    report['issued_pv']['historical_full_day'] = metrics(
        fc['pv'][sl] - data['pv'][sl], data['pv'][sl])
    report['issued_pv']['zero_full_day'] = metrics(
        fc['issued'][sl, 0] - data['pv'][sl], data['pv'][sl])

    # 指定日期上独立打乱每个时间列，检验目标是否只使用边际分布。
    day = data['dates'].index('2025-09-23')
    scenarios = residual_scenarios(data, fc, day, 0, issue=0)
    rng = np.random.default_rng(20260911)
    shuffled = np.column_stack([rng.permutation(col) for col in scenarios.T])
    q3_for_diag = np.load(out_root / 'q3.npz')
    initial = float(q3_for_diag['energy'][day, 0])
    s1, s2 = optimize(scenarios, data['one'][:, 0], initial), optimize(shuffled, data['one'][:, 0], initial)
    f1 = execute(s1['grid'], data['load'][day], data['pv'][day], initial)
    f2 = execute(s2['grid'], data['load'][day], data['pv'][day], initial)
    report['scenario_shuffle'] = {
        'date': data['dates'][day], 'seed': 20260911,
        'original_objective': s1['objective'], 'permuted_objective': s2['objective'],
        'objective_difference': s2['objective'] - s1['objective'],
        'max_grid_difference': float(np.max(np.abs(s2['grid'] - s1['grid']))),
        'original_feedback_cost': float(DT*np.dot(data['one'][:, 0], s1['grid'] + 5*f1['emergency'])),
        'permuted_feedback_cost': float(DT*np.dot(data['one'][:, 0], s2['grid'] + 5*f2['emergency'])),
    }

    # 连续全年回测：固定 q2 常规购电计划，只替换实际储能反馈规则。
    q2 = np.load(out_root / 'q2.npz')
    q3 = np.load(out_root / 'q3.npz'); q3_daily = np.load(out_root / 'q3_daily.npz')
    delta = q3_daily['costs'][31:, 4] - q3['costs'][31:, 4]
    report['update_cost_by_month'] = {
        str(m): float(delta[[int(x[5:7]) == m for x in data['dates'][31:]]].sum()) for m in range(2, 13)
    }
    report['update_emergency_by_month'] = {
        str(m): float((q3_daily['emergency'][31:][[int(x[5:7]) == m for x in data['dates'][31:]]].sum()
                       - q3['emergency'][31:][[int(x[5:7]) == m for x in data['dates'][31:]]].sum()) * DT)
        for m in range(2, 13)
    }
    report['update_days'] = {
        'cheaper': int(np.sum(delta > 1e-8)),
        'more_expensive': int(np.sum(delta < -1e-8)),
        'same': int(np.sum(np.abs(delta) <= 1e-8)),
    }
    state_g, state_r = EINIT, EINIT
    rows = []
    for d in range(365):
        base = execute(q2['plan'][d], data['load'][d], data['pv'][d], state_g)
        reserve = execute_reserve(q2['plan'][d], data['load'][d], data['pv'][d], state_r,
                                  fc['load'][d], fc['pv'][d])
        p = data['one'][:, 0]
        c_base = DT*np.dot(p, q2['plan'][d] + 5*base['emergency'])
        c_res = DT*np.dot(p, q2['plan'][d] + 5*reserve['emergency'])
        rows.append((d, c_base, c_res, DT*base['emergency'].sum(), DT*reserve['emergency'].sum(),
                     base['energy'][-1], reserve['energy'][-1]))
        state_g, state_r = base['energy'][-1], reserve['energy'][-1]
    rows = np.asarray(rows)
    rr = rows[31:]
    report['feedback_benchmark'] = {
        'rule': '预留未来36个10分钟时段日前预测缺额所需电量',
        'horizon_periods': 36,
        'base_total_cost': float(rr[:, 1].sum()), 'reserve_total_cost': float(rr[:, 2].sum()),
        'cost_difference_reserve_minus_base': float(rr[:, 2].sum()-rr[:, 1].sum()),
        'base_emergency_kwh': float(rr[:, 3].sum()), 'reserve_emergency_kwh': float(rr[:, 4].sum()),
        'emergency_difference_kwh': float(rr[:, 4].sum()-rr[:, 3].sum()),
        'cheaper_days': int(np.sum(rr[:, 2] < rr[:, 1]-1e-8)),
        'more_expensive_days': int(np.sum(rr[:, 2] > rr[:, 1]+1e-8)),
        'same_days': int(np.sum(np.abs(rr[:, 2]-rr[:, 1]) <= 1e-8)),
        'base_end_soc': float(state_g), 'reserve_end_soc': float(state_r),
    }
    # 重新计算两条连续轨迹的全程SOC边界，避免只报告末态。
    state_g, state_r = EINIT, EINIT; mins = [1e9, 1e9]; maxs = [-1e9, -1e9]
    for d in range(365):
        b = execute(q2['plan'][d], data['load'][d], data['pv'][d], state_g)
        r = execute_reserve(q2['plan'][d], data['load'][d], data['pv'][d], state_r, fc['load'][d], fc['pv'][d])
        mins = [min(mins[0], b['energy'].min()), min(mins[1], r['energy'].min())]
        maxs = [max(maxs[0], b['energy'].max()), max(maxs[1], r['energy'].max())]
        state_g, state_r = b['energy'][-1], r['energy'][-1]
    report['feedback_benchmark'].update({'base_min_soc': mins[0], 'reserve_min_soc': mins[1],
                                          'base_max_soc': maxs[0], 'reserve_max_soc': maxs[1]})
    (out_root / 'diagnostics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('--data', required=True); ap.add_argument('--out', default=Path(__file__).resolve().parents[1]/'results')
    a = ap.parse_args(); run(a.data, a.out)
