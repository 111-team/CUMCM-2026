"""对关键物理约束、费用、时间因果性与导出数据做独立检查。"""
import argparse,json
from pathlib import Path
import numpy as np
from model import load_data,forecast_all,run_case,audit,execute,plan_at_issue,settlement_cost,EMIN,EMAX,PMAX,DT,ETA,EINIT

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);args=p.parse_args()
    root=Path(__file__).resolve().parents[1]/'results';data=load_data(args.data)
    meta=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    metrics={}
    for name,info in meta['cases'].items():
        a=dict(np.load(root/(name+'.npz')));audit(data,a,info['eta'])
        prices=np.broadcast_to(data['one'][:,0],(365,144)) if info['price_mode']=='fixed' else data['price']
        diff=a['grid']-a['plan']
        # 使用“履行量+取消罚金+新增量”独立复算，避免只重复实现中的净退费表达。
        ordinary = (prices*np.minimum(a['plan'],a['grid'])+.5*prices*np.maximum(-diff,0)+1.5*prices*np.maximum(diff,0)) if info['settlement']=='refund' else (prices*a['plan']+.5*prices*np.maximum(-diff,0)+1.5*prices*np.maximum(diff,0))
        direct=(ordinary+5*prices*a['emergency']).sum(axis=1)*DT
        assert np.max(abs(direct-a['costs'][:,4]))<1e-6
        metrics[name]={'max_power_residual':float(abs(a['grid']+data['pv']+a['dis']+a['emergency']-data['load']-a['ch']-a['spill']).max()),'max_cost_residual':float(abs(direct-a['costs'][:,4]).max()),'min_energy':float(a['energy'].min()),'max_energy':float(a['energy'].max()),'simultaneous_periods':int((np.minimum(a['ch'],a['dis'])>1e-6).sum())}
    q=dict(np.load(root/'q1.npz'));energy=np.r_[EINIT,q['energy']]
    assert abs(energy[-1]-EINIT)<1e-6
    assert np.max(abs(np.diff(energy)-ETA*q['ch']*DT+q['dis']*DT/ETA))<1e-6
    assert np.min(q['grid']+q['pv']+q['dis']-q['load']-q['ch'])>=-1e-6
    assert abs(np.dot(q['price'],q['grid'])*DT-float(q['objective']))<1e-6
    # 未来实际数据扰动不应改变此前已发布的预测及方法选择。
    original,_,selected=forecast_all(data)
    changed={k:(v.copy() if isinstance(v,np.ndarray) else v) for k,v in data.items()}
    for key in ('load','pv','price'):changed[key][180:]*=1.5
    changed['pv_hour'][180:]*=.5
    altered,_,selected2=forecast_all(changed)
    assert selected==selected2
    for key in ('load','pv','price','issued'):assert np.array_equal(original[key][:180],altered[key][:180])
    # 进一步重跑日前决策：报告期后数据扰动不能改变此前已形成的计划。
    original_q2 = dict(np.load(root/'q2.npz'))
    altered_q2, _ = run_case(changed, altered, kind=2)
    assert np.array_equal(original_q2['plan'][:180], altered_q2['plan'][:180])
    assert np.array_equal(original_q2['grid'][:180], altered_q2['grid'][:180])
    # 改动当天未来实际量和尚未发布的预报，当前同一决策入口的解应不变。
    q3 = dict(np.load(root/'q3.npz')); day=100
    decision_checks=[]
    for issue in range(4):
        start=issue*36
        mutated={k:(v.copy() if isinstance(v,np.ndarray) else list(v)) for k,v in data.items()}
        for key in ('load','pv','price'):
            mutated[key][day,start:] *= 1.7
        mutated['pv_hour'][day,issue+1:] *= .2
        future_fc,_,future_selected=forecast_all(mutated)
        assert selected == future_selected
        base=q3['plan'][day,start:] if issue else None
        state=float(q3['energy'][day,start])
        for mode in ('issued','blend'):
            f0=original if mode=='issued' else dict(original,issued=original['issued_blend'])
            f1=future_fc if mode=='issued' else dict(future_fc,issued=future_fc['issued_blend'])
            before=plan_at_issue(data,f0,day,issue,state,base,price_mode='forecast')
            after=plan_at_issue(mutated,f1,day,issue,state,base,price_mode='forecast')
            delta=float(np.max(abs(before['grid']-after['grid'])))
            assert delta<1e-8
            decision_checks.append({'hour':issue*6,'pv_mode':mode,'max_grid_difference':delta})
    # 计划5kWh，下调为4、保持5、上调为6、全取消，应分别支付4.5、5、6.5、2.5元。
    for actual, expected in ((4.,4.5),(5.,5.),(6.,6.5),(0.,2.5)):
        bill=settlement_cost(np.array([5./DT]),np.array([actual/DT]),np.zeros(1),np.ones(1))
        assert abs(bill[-1]-expected)<1e-10
    # 缺电且SOC下限、盈余且SOC上限两种边界。
    low=execute(np.array([0.]),np.array([100.]),np.array([0.]),EMIN)
    high=execute(np.array([100.]),np.array([0.]),np.array([0.]),EMAX)
    assert low['emergency'][0]==100 and low['dis'][0]==0
    assert high['spill'][0]==100 and high['ch'][0]==0
    output={'cases':metrics,'causality_future_perturbation':'passed (forecasts and q2 decisions through day 180)',
            'unpublished_information_decisions':decision_checks,'settlement_examples':'passed: 4.5, 5, 6.5, 2.5 yuan',
            'input_date_time_publication_order':'passed','physical_boundary_checks':'passed','q1_checks':'passed'}
    (root/'verification.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))
if __name__=='__main__':main()
