"""第二轮审稿实验：信息参照、终端库存价值、经济性门控与费用驱动选型。

主结果保持为事先定义的四套基准。新增策略均从同一主策略的1月实际
状态启动；参数只用1月15—31日选择，2—12月仅检验，不反选参数。
"""
import argparse, json
from pathlib import Path
from time import perf_counter
import numpy as np
from model import (DT, ETA, EMIN, EMAX, EINIT, PMAX, METHODS, load_data,
                   forecast_all, predict, residual_scenarios, optimize,
                   execute, settlement_cost, audit, summarize)

ROOT = Path(__file__).resolve().parents[1]
R = ROOT/'results'


def next_value(data, forecast, day, price_mode, gamma):
    """日前估计的次日均价；当天尚未观测的价格不参与次日预测。"""
    if price_mode == 'fixed':
        prices = data['one'][:, 0]
    else:
        idx = [day+1-lag for lag in (7, 14, 21, 28) if 0 <= day+1-lag < day]
        prices = np.mean(data['price'][idx], axis=0) if idx else forecast['price'][day]
    return float(gamma*ETA*np.mean(prices))


def policy_value(grid, base, scenarios, prices, initial, terminal_value=0.):
    """在相同净负荷场景下，按实际反馈规则评估剩余现金费用减期末库存价值。

    一条误差轨迹内部按时间连续推进SOC；只计算未执行部分。
    """
    state = np.full(len(scenarios), initial)
    emergency_bill = np.zeros(len(scenarios))
    for t in range(len(grid)):
        residual = grid[t]-scenarios[:, t]
        charge = np.minimum(np.maximum(residual, 0), np.minimum(PMAX, (EMAX-state)/(ETA*DT)))
        discharge = np.minimum(np.maximum(-residual, 0), np.minimum(PMAX, (state-EMIN)*ETA/DT))
        emergency = np.maximum(-residual-discharge, 0)
        state += ETA*DT*charge-DT/ETA*discharge
        emergency_bill += 5*prices[t]*emergency*DT
    ordinary = settlement_cost(base, grid, np.zeros(len(grid)), prices)[-1]
    return float(ordinary+emergency_bill.mean()-terminal_value*state.mean())


def choose_adjustment(candidate, incumbent, base, scenarios, prices, state, value=0.):
    old = policy_value(incumbent, base, scenarios, prices, state, value)
    new = policy_value(candidate, base, scenarios, prices, state, value)
    accepted = bool(old-new > 1e-6)  # 仅为数值容差，无额外未给定的固定调整费。
    return (candidate if accepted else incumbent).copy(), dict(
        keep_value=old, candidate_value=new, expected_saving=old-new, accepted=accepted)


def alternative_forecast(data, forecast, method):
    fc = dict(forecast)
    fc['pv'] = forecast['pv'].copy()
    # 1月15日开始对候选方法逐日回放；预测每一天仍只用此前真实数据。
    for day in range(14, 365):
        fc['pv'][day] = predict(data['pv'][:day], data['one'][:, 2], method)
    return fc


def run_refined(data, forecast, baseline, kind=2, price_mode='fixed', gamma=0.,
                gate=False, start_day=31, stop_day=365, daily_oracle=False):
    started = perf_counter()
    arrays = {k: v.copy() for k, v in baseline.items()}
    state = float(arrays['energy'][start_day, 0])
    decisions = []
    lp_seconds = 0.; solves = 0
    for day in range(start_day, stop_day):
        prices = data['one'][:, 0] if price_mode == 'fixed' else forecast['price'][day]
        realized = data['one'][:, 0] if price_mode == 'fixed' else data['price'][day]
        if daily_oracle:
            prices = realized
        value = next_value(data, forecast, day, price_mode, gamma)
        committed = None
        for issue in ([0] if kind == 2 else range(4)):
            start = issue*36
            end = min(start+36, 144) if kind == 3 else 144
            scenarios = (data['load'][day]-data['pv'][day])[None, :] if daily_oracle else residual_scenarios(
                data, forecast, day, start, None if kind == 2 else issue)
            base = arrays['plan'][day, start:].copy() if issue else None
            sol = optimize(scenarios, prices[start:], state, base=base, terminal_value=value)
            lp_seconds += sol['seconds']; solves += 1
            if issue == 0:
                arrays['plan'][day] = sol['grid']
                committed = sol['grid'].copy()
            elif gate:
                chosen, record = choose_adjustment(sol['grid'], committed[start:], base,
                                                   scenarios, prices[start:], state, value)
                record.update(day=day, hour=issue*6)
                decisions.append(record)
                committed[start:] = chosen
            else:
                committed[start:] = sol['grid']
            g = committed[start:end]
            arrays['grid'][day, start:end] = g
            actual = execute(g, data['load'][day, start:end], data['pv'][day, start:end], state)
            for key in ('ch', 'dis', 'emergency', 'spill'):
                arrays[key][day, start:end] = actual[key]
            arrays['energy'][day, start:end+1] = actual['energy']
            state = float(actual['energy'][-1])
        arrays['costs'][day] = settlement_cost(arrays['plan'][day], arrays['grid'][day],
                                               arrays['emergency'][day], realized)
    info = dict(kind=kind, price_mode=price_mode, eta=ETA, settlement='refund', gamma=gamma,
                gate=gate, start_day=start_day, stop_day=stop_day, daily_oracle=daily_oracle,
                seconds=perf_counter()-started, lp_seconds=lp_seconds, solves=solves,
                accepted=sum(r['accepted'] for r in decisions), rejected=sum(not r['accepted'] for r in decisions))
    if stop_day == 365:
        audit(data, arrays)
    return arrays, info, decisions


def validation_score(arrays, price_ref):
    """同一1月15日初值；按统一估价扣回候选间不同期末库存。"""
    cash = float(arrays['costs'][14:31, 4].sum())
    final = float(arrays['energy'][30, -1])
    return dict(cash_cost=cash, final_energy=final, adjusted_cost=cash-price_ref*final)


def oracle_full(data, baseline, price_mode):
    """报告期全部未来量已知的稀疏LP，期初和期末SOC与主策略完全一致。"""
    n = 334*144
    prices = np.tile(data['one'][:, 0], 334) if price_mode == 'fixed' else data['price'][31:].ravel()
    net = (data['load'][31:]-data['pv'][31:]).reshape(1, n)
    sol = optimize(net, prices, float(baseline['energy'][31, 0]),
                   final_energy=float(baseline['energy'][-1, -1]))
    arrays = {k: v.copy() for k, v in baseline.items()}
    for k in ('grid', 'ch', 'dis'):
        arrays[k][31:] = sol[k].reshape(334, 144)
    arrays['plan'][31:] = arrays['grid'][31:]
    arrays['emergency'][31:] = 0.
    arrays['spill'][31:] = (sol['grid']+sol['dis']-sol['ch']-net[0]).reshape(334, 144)
    states = np.r_[baseline['energy'][31, 0], sol['energy']]
    for d in range(334):
        arrays['energy'][31+d] = states[d*144:(d+1)*144+1]
    arrays['costs'][31:] = 0.
    costs = (prices*sol['grid']).reshape(334, 144).sum(axis=1)*DT
    arrays['costs'][31:, 0] = costs
    arrays['costs'][31:, 4] = costs
    assert abs(costs.sum()-sol['objective']) < 1e-4
    assert np.min(arrays['spill'][31:]) >= -1e-6
    audit(data, arrays)
    info = dict(kind=2, price_mode=price_mode, eta=ETA, settlement='refund',
                information='all report-period future actuals', seconds=sol['seconds'], solves=1)
    return arrays, info


def check(data, forecast, bases, output):
    # 功率/能量单位与单程效率的独立数值例证。
    charged = execute(np.array([600.]), np.array([0.]), np.array([0.]), 6000.)
    discharged = execute(np.array([0.]), np.array([600.]), np.array([0.]), 6090.)
    assert abs(charged['energy'][-1]-6090.) < 1e-9
    assert abs(discharged['energy'][-1]-(6090.-100/.9)) < 1e-9
    # 独立费用与门控检查；过去原计划不被日内覆盖。
    report = {'energy_example': {'grid_side_charge_kwh': 100., 'internal_increment_kwh': 90.,
                                 'grid_side_discharge_kwh': 100., 'internal_decrement_kwh': 100/.9}}
    # 用逐场景标量反馈独立复算向量化门控评分，涵盖SOC上下限与充放电切换。
    grid=np.array([500.,0.,3000.,0.]);base=np.array([600.,100.,2800.,20.])
    scenes=np.array([[0.,4000.,100.,6000.],[1000.,0.,3500.,500.]])
    price=np.array([.4,1.2,.6,1.4])
    for initial in (EMIN,EINIT,EMAX):
        values=[]
        for net in scenes:
            feedback=execute(grid,net,np.zeros(4),initial)
            values.append(settlement_cost(base,grid,feedback['emergency'],price)[-1])
        assert abs(policy_value(grid,base,scenes,price,initial)-np.mean(values))<1e-9
    report['gate_scoring_independent'] = 'passed: scalar scene replay at three SOC boundaries'
    for key, item in output['cases'].items():
        a = dict(np.load(R/(key+'.npz')))
        audit(data, a)
        price = np.broadcast_to(data['one'][:,0], (365,144)) if item['price_mode']=='fixed' else data['price']
        up = np.maximum(a['grid']-a['plan'], 0)
        down = np.maximum(a['plan']-a['grid'], 0)
        direct = (price*np.minimum(a['plan'],a['grid'])+.5*price*down+1.5*price*up+5*price*a['emergency']).sum(axis=1)*DT
        assert np.max(abs(direct-a['costs'][:,4])) < 1e-6
        report[key] = {'max_cost_error': float(np.max(abs(direct-a['costs'][:,4]))),
                       'max_cross_day_error': float(np.max(abs(a['energy'][:-1,-1]-a['energy'][1:,0])))}
    # 修改某次决策之后的实际量及尚未发布预报，应保持候选解、门控评分与决定一致。
    day, issue = 100, 2
    changed = {k: (v.copy() if isinstance(v,np.ndarray) else v) for k,v in data.items()}
    for key in ('load','pv','price'):
        changed[key][day,issue*36:] *= 1.8
        changed[key][day+1:] *= 1.4
    changed['pv_hour'][day,issue+1:] *= .3
    changed['pv_hour'][day+1:] *= .2
    altered,_,_ = forecast_all(changed)
    outcomes = []
    b = bases['q4_3']; start=issue*36
    for dd, ff in ((data,forecast),(changed,altered)):
        scenarios=residual_scenarios(dd,ff,day,start,issue)
        value=next_value(dd,ff,day,'forecast',1.)
        sol=optimize(scenarios,ff['price'][day,start:],b['energy'][day,start],base=b['plan'][day,start:],terminal_value=value)
        g,r=choose_adjustment(sol['grid'],b['plan'][day,start:],b['plan'][day,start:],scenarios,ff['price'][day,start:],b['energy'][day,start],value)
        outcomes.append((g,r,value))
    assert np.array_equal(outcomes[0][0],outcomes[1][0]) and outcomes[0][1:] == outcomes[1][1:]
    report['new_decision_causality'] = 'passed: candidate, gate scores/decision and next-day value unchanged'
    # 与前稿完全相同的已运行基准复算若干决策，核查新增可选参数未改变默认模型。
    for day in (31,100,364):
        b=bases['q2'];sc=residual_scenarios(data,forecast,day,0)
        sol=optimize(sc,data['one'][:,0],b['energy'][day,0])
        assert np.max(abs(sol['grid']-b['plan'][day])) < 1e-7
    report['baseline_regression'] = 'passed: 3 dates; defaults unchanged'
    output['verification'] = report


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);args=p.parse_args()
    data=load_data(args.data);forecast,_,selected=forecast_all(data)
    bases={k:dict(np.load(R/(k+'.npz'))) for k in ('q2','q3','q4_2','q4_3')}
    output={'protocol':'Jan 15-31 calibration; Feb 1-Dec 31 frozen holdout; shared January actual warmup',
            'cases':{},'validation':{},'gate_decisions':{}}
    def save(name, a, info, decisions=None):
        np.savez_compressed(R/(name+'.npz'),**a)
        output['cases'][name]=summarize(a,info)
        if decisions is not None: output['gate_decisions'][name]=decisions
        (R/'refinements.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,json.dumps(output['cases'][name],ensure_ascii=False),flush=True)
    # 不同价格条件各自仅在一月份选择终端价值强度和光伏预测方法。
    for mode, basekey in (('fixed','q2'),('forecast','q4_2')):
        baseline=bases[basekey]
        price_ref=ETA*float(data['one'][:36,0].mean())
        terminal={}
        for gamma in (0., .5, 1., 1.5):
            a,_,_=run_refined(data,forecast,baseline,price_mode=mode,gamma=gamma,start_day=14,stop_day=31)
            terminal[str(gamma)]=validation_score(a,price_ref)
        chosen_gamma=float(min(terminal,key=lambda x:terminal[x]['adjusted_cost']))
        output['validation'][basekey+'_terminal']={'scores':terminal,'selected':chosen_gamma,'inventory_price':price_ref}
        a,info,_=run_refined(data,forecast,baseline,price_mode=mode,gamma=chosen_gamma)
        save(basekey+'_terminal',a,info)
        economic={}
        for method in METHODS:
            fc=alternative_forecast(data,forecast,method)
            a,_,_=run_refined(data,fc,baseline,price_mode=mode,start_day=14,stop_day=31)
            score=validation_score(a,price_ref)
            error=fc['pv'][14:31]-data['pv'][14:31]
            score['mae']=float(np.mean(abs(error)));score['rmse']=float(np.sqrt(np.mean(error**2)))
            economic[method]=score
        chosen_method=min(economic,key=lambda x:economic[x]['adjusted_cost'])
        output['validation'][basekey+'_economic']={'scores':economic,'selected':chosen_method,'mae_selected':selected['pv'],'inventory_price':price_ref}
        fc=alternative_forecast(data,forecast,chosen_method)
        a,info,_=run_refined(data,fc,baseline,price_mode=mode);info['pv_method']=chosen_method
        save(basekey+'_economic',a,info)
        # MAE选型也使用同样的候选历史回放，避免1月底误差缓存不同造成混杂。
        fc=alternative_forecast(data,forecast,selected['pv'])
        a,info,_=run_refined(data,fc,baseline,price_mode=mode);info['pv_method']=selected['pv']
        save(basekey+'_mae_control',a,info)
        # 从完全相同1月末SOC出发的逐日先知参照，日内全曲线已知，但仍只优化当天。
        a,info,_=run_refined(data,forecast,baseline,price_mode=mode,daily_oracle=True)
        save(basekey+'_daily_oracle',a,info)
        a,info=oracle_full(data,baseline,mode)
        save(basekey+'_full_oracle',a,info)
    for mode, basekey in (('fixed','q3'),('forecast','q4_3')):
        a,info,decisions=run_refined(data,forecast,bases[basekey],kind=3,price_mode=mode,gate=True)
        assert all((r['expected_saving']>1e-6)==r['accepted'] for r in decisions)
        save(basekey+'_gate',a,info,decisions)
    check(data,forecast,bases,output)
    (R/'refinements.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print('All refinement experiments and independent checks passed.',flush=True)


if __name__=='__main__':main()
