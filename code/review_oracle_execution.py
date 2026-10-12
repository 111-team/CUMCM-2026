"""补充：同一计划下的日内执行上界（问题2）。

固定已提交的问题2计划购电量与实际负荷、光伏，把日内储能执行由正文的因果
反馈规则改为"当日完全预知的最优调度"，逐日链式传递实际储电量，用于界定
第10.1.2节"风险代理与执行反馈不一致"这一局限的费用量级。

该上界要求当日负荷与光伏在零时即完全已知，不可实现，只是量级参照，不替换
任何主结果，也不写入五份规定工作簿。
"""
from pathlib import Path
import json, platform
import numpy as np, scipy
from scipy.optimize import linprog
from model import DT, EMIN, EMAX, PMAX

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / 'results'
FIRST, LAST = 31, 365          # 0 基日索引：31 = 2025-02-01，364 = 2025-12-31
INVENTORY_PRICE = 'one_first6h'   # 统一库存估值：附件1零至6时均价乘放电效率


def oracle_day(plan, load, pv, price, initial, eta_c=0.9, eta_d=0.9):
    """给定当日计划购电功率，求最小实际紧急购电费用的日内执行安排。"""
    n = plan.size
    # 变量顺序：[ch, dis, em, sp, E_0..E_n]
    def ix(kind, t):
        return {'ch': 0, 'dis': n, 'em': 2 * n, 'sp': 3 * n, 'E': 4 * n}[kind] + t

    obj = np.zeros(4 * n + n + 1)
    for t in range(n):
        obj[ix('em', t)] = 5.0 * price[t] * DT

    a_eq, b_eq = [], []
    for t in range(n):                      # 母线平衡：计划已定，缺额只能紧急补电
        row = np.zeros(obj.size)
        row[ix('dis', t)] = 1.0
        row[ix('em', t)] = 1.0
        row[ix('ch', t)] = -1.0
        row[ix('sp', t)] = -1.0
        a_eq.append(row)
        b_eq.append(load[t] - pv[t] - plan[t])
    for t in range(1, n + 1):               # 储能动态
        row = np.zeros(obj.size)
        row[ix('E', t)] = 1.0
        row[ix('E', t - 1)] = -1.0
        row[ix('ch', t - 1)] = -eta_c * DT
        row[ix('dis', t - 1)] = DT / eta_d
        a_eq.append(row)
        b_eq.append(0.0)

    bounds = [(0, PMAX)] * (2 * n) + [(0, None)] * (2 * n) + [(EMIN, EMAX)] * (n + 1)
    bounds[ix('E', 0)] = (initial, initial)
    fit = linprog(obj, A_eq=np.array(a_eq), b_eq=np.array(b_eq), bounds=bounds, method='highs')
    if not fit.success:
        raise RuntimeError(fit.message)
    return fit


def main():
    data = dict(np.load(R / 'inputs_processed.npz'))
    base = np.load(R / 'q2.npz')
    one = data['one']
    price = one[:, 0]
    load, pv = data['load'], data['pv']

    initial = float(base['energy'][FIRST, 0])
    cash_emergency = 0.0
    emergency_kwh = 0.0
    spill_kwh = 0.0
    daily = []
    for day in range(FIRST, LAST):
        fit = oracle_day(base['plan'][day], load[day], pv[day], price, initial)
        n = load.shape[1]
        em = fit.x[2 * n:3 * n]
        ch = fit.x[0:n]
        dis = fit.x[n:2 * n]
        sp = fit.x[3 * n:4 * n]
        energy = fit.x[4 * n:5 * n + 1]
        cash_emergency += float((5.0 * price * em * DT).sum())
        emergency_kwh += float(em.sum() * DT)
        spill_kwh += float(sp.sum() * DT)
        initial = float(energy[-1])
        daily.append({'date_index': day, 'emergency_kwh': float(em.sum() * DT),
                      'end_energy': initial})

    plan_cash = float(base['costs'][FIRST:LAST, 0].sum())      # 与主结果一致的计划费
    base_total = float(base['costs'][FIRST:LAST, 4].sum())     # 主结果报告期现金费用
    base_end = float(base['energy'][LAST - 1, 144])
    v = float(np.mean(one[:36, 0])) * 0.9                      # 统一库存参考价值
    oracle_cash = plan_cash + cash_emergency
    adj_oracle = oracle_cash + v * float(base['energy'][FIRST, 0]) - v * initial
    adj_base = base_total + v * float(base['energy'][FIRST, 0]) - v * base_end

    report = {
        'purpose': '同一计划、同一实际负荷与光伏下，日内执行改为当日完全预知的最优调度',
        'report_period': '2025-02-01 to 2025-12-31',
        'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__,
        'inventory_value_yuan_per_kwh': v,
        'base_total_cost': base_total, 'base_end_energy': base_end,
        'oracle_total_cost': oracle_cash, 'oracle_end_energy': initial,
        'cash_saving': base_total - oracle_cash,
        'inventory_adjusted_base': adj_base, 'inventory_adjusted_oracle': adj_oracle,
        'inventory_adjusted_saving': adj_base - adj_oracle,
        'saving_percent_of_base': (base_total - oracle_cash) / base_total * 100.0,
        'oracle_emergency_kwh': emergency_kwh, 'base_emergency_kwh':
            float(base['emergency'][FIRST:LAST].sum() * DT),
        'oracle_spill_kwh': spill_kwh,
        'base_spill_kwh': float(base['spill'][FIRST:LAST].sum() * DT),
        'daily': daily,
    }
    (R / 'review_oracle_execution.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'daily'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
