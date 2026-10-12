"""3.7复核补充：独立LP、计划风险权重、能量守恒与库存估值。

只写 review_* 结果，不修改原27组主模型与对照。权重扫描从相同的
问题2 1月末实际SOC开始；历史预测不变，真实紧急电始终按5倍价结算。
"""
from pathlib import Path
import json, sys, platform
from time import perf_counter
import numpy as np
import scipy
from scipy.optimize import linprog
from scipy.sparse import eye, diags, hstack, vstack, csr_matrix
from model import DT, EMIN, EMAX, EINIT, PMAX, execute, residual_scenarios, settlement_cost, audit

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results'

def solve(scenarios,price,initial,rho=5.,eta_c=.9,eta_d=.9,cyclic=False):
    s,n=scenarios.shape
    ident=eye(n,format='csr');zero=csr_matrix((n,n))
    delta=ident-diags(np.ones(n-1),-1,shape=(n,n),format='csr')
    eq=hstack([zero,-eta_c*DT*ident,DT/eta_d*ident,delta,csr_matrix((n,s*n))],format='csr')
    rhs=np.zeros(n);rhs[0]=initial
    tile=vstack([ident]*s,format='csr')
    ub=hstack([-tile,tile,-tile,csr_matrix((s*n,n)),-eye(s*n,format='csr')],format='csr')
    obj=np.r_[price*DT,np.zeros(3*n),np.tile(rho*price*DT/s,s)]
    bounds=[(0,None)]*n+[(0,PMAX)]*(2*n)+[(EMIN,EMAX)]*n+[(0,None)]*(s*n)
    if cyclic:
        bounds[4*n-1]=(initial,initial)
        bounds[4*n:]=[(0,0)]*(s*n)
    fit=linprog(obj,A_eq=eq,b_eq=rhs,A_ub=ub,b_ub=-scenarios.ravel(),bounds=bounds,method='highs')
    if not fit.success:raise RuntimeError(fit.message)
    grid,ch,dis,energy=np.split(fit.x[:4*n],4)
    amount=np.minimum(ch,dis/(eta_c*eta_d));ch=ch-amount;dis=dis-eta_c*eta_d*amount
    assert np.max(abs(eq@fit.x-rhs))<1e-6
    assert np.max(ub@fit.x+scenarios.ravel())<1e-6
    assert np.max(np.minimum(ch,dis))<1e-6
    return dict(grid=grid,ch=ch,dis=dis,energy=energy,objective=float(fit.fun))

def main():
    begin=perf_counter();data=dict(np.load(R/'inputs_processed.npz'))
    forecast={k[9:]:v for k,v in data.items() if k.startswith('forecast_')}
    base=dict(np.load(R/'q2.npz'));price=data['one'][:,0]
    report={'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,
            'report_period':'2025-02-01 to 2025-12-31','efficiency':[], 'risk_scan':[], 'inventory':{}}
    for label,ec,ed in [('both_0.9',.9,.9),('round_trip_0.9',np.sqrt(.9),np.sqrt(.9)),('charging_loss_only',.9,1.),('discharging_loss_only',1.,.9)]:
        a=solve((data['one'][:,1]-data['one'][:,2])[None,:],price,EINIT,eta_c=ec,eta_d=ed,cyclic=True)
        q=dict(label=label,eta_c=float(ec),eta_d=float(ed),cost=a['objective'],grid_kwh=float(a['grid'].sum()*DT))
        report['efficiency'].append(q)
    assert abs(report['efficiency'][0]['cost']-float(np.load(R/'q1.npz')['objective']))<1e-6
    reuse='--reuse-scan' in sys.argv
    if reuse:
        previous=json.loads((R/'review_diagnostics.json').read_text(encoding='utf-8'))
        report['risk_scan']=previous['risk_scan'];report['risk5_baseline_max_difference']=previous['risk5_baseline_max_difference']
    for rho in ([] if reuse else [2,3,5,8]):
        tick=perf_counter();a={k:v.copy() for k,v in base.items()};state=base['energy'][31,0]
        for day in range(31,365):
            scene=residual_scenarios(data,forecast,day,0,history_days=14)
            plan=solve(scene,price,state,rho=rho)['grid']
            actual=execute(plan,data['load'][day],data['pv'][day],state)
            a['grid'][day]=plan;a['plan'][day]=plan
            for k in actual:a[k][day]=actual[k]
            a['costs'][day]=settlement_cost(plan,plan,actual['emergency'],price)
            state=actual['energy'][-1]
        audit(data,a)
        if rho==5:
            diff=max(float(np.max(abs(a[k]-base[k]))) for k in base)
            assert diff<1e-6,diff
            report['risk5_baseline_max_difference']=diff
        np.savez_compressed(R/f'review_risk{rho}.npz',**a)
        row=dict(rho=rho,cost=float(a['costs'][31:,4].sum()),emergency_kwh=float(a['emergency'][31:].sum()*DT),
                 spill_kwh=float(a['spill'][31:].sum()*DT),start_energy=float(a['energy'][31,0]),end_energy=float(state),seconds=perf_counter()-tick)
        report['risk_scan'].append(row);print(json.dumps(row),flush=True)
    sl=slice(31,None);a=base;pv=data['pv'][sl];load=data['load'][sl]
    # 来源归属约定：光伏优先承担实际负荷与实际充电；其余未利用供给归为已购电。
    # 这是固定轨迹下的归属，不是“即使重新优化也不可避免”的弃光下界。
    pv_spill=np.maximum(pv-load-a['ch'][sl],0)
    purchased_spill=np.maximum(a['spill'][sl]-pv_spill,0)
    assert np.max(abs(pv_spill+purchased_spill-a['spill'][sl]))<1e-6
    loss=((1-.9)*a['ch'][sl]+(1/.9-1)*a['dis'][sl]).sum()*DT
    stock=float(a['energy'][-1,-1]-a['energy'][31,0])
    grid=float((a['grid'][sl]+a['emergency'][sl]).sum()*DT);net=float((load-pv).sum()*DT)
    spill=float(a['spill'][sl].sum()*DT)
    assert abs((grid-net)-(spill+loss+stock))<1e-6
    report['q2_energy']=dict(net_kwh=net,purchased_kwh=grid,excess_percent=(grid/net-1)*100,loss_kwh=float(loss),
        stock_change_kwh=stock,spill_kwh=spill,pv_spill_kwh=float(pv_spill.sum()*DT),
        paid_spill_kwh=float(purchased_spill.sum()*DT),paid_spill_cost=float((purchased_spill*price).sum()*DT),
        spill_emergency_ratio=spill/(a['emergency'][sl].sum()*DT),peak_regular_kw=float(a['grid'][sl].max()),
        peak_load_kw=float(load.max()),days_with_spill=int((a['spill'][sl].sum(axis=1)>1e-6).sum()))
    # 光伏优先满足负荷后，剩余光伏与外购电的充电来源分配仍非唯一。
    # 两端分别优先用外购电/剩余光伏充电；这不是概率置信区间。
    paid_min=np.maximum(a['spill'][sl]-np.maximum(pv-load,0),0)
    paid_max=np.minimum(a['spill'][sl],a['grid'][sl])
    assert np.max(abs(paid_max-purchased_spill))<1e-6
    report['q2_energy'].update(regular_kwh=float(a['grid'][sl].sum()*DT),
        paid_spill_kwh_interval=[float(paid_min.sum()*DT),float(paid_max.sum()*DT)],
        paid_spill_cost_interval=[float((paid_min*price).sum()*DT),float((paid_max*price).sum()*DT)])
    # 一律使用同一内部库存估值区间，包含原稿参考值；端点检查可确定线性差的排序。
    vlo=.9*float(data['price'].min());vhi=.9*float(data['price'].max());vref=.9*.4248
    for case in ['q2','q3','q4_2','q4_3','q4_2_known','q4_3_known']:
        c=dict(np.load(R/(case+'.npz')));delta=float(c['energy'][31,0]-c['energy'][-1,-1]);cost=float(c['costs'][31:,4].sum())
        report['inventory'][case]=dict(cash_cost=cost,start_energy=float(c['energy'][31,0]),end_energy=float(c['energy'][-1,-1]),
            consumed_kwh=delta,reference_adjustment=vref*delta,adjustment_interval=sorted([vlo*delta,vhi*delta]))
    main_cases=['q2','q3','q4_2','q4_3']
    ranks=[[k for k in sorted(main_cases,key=lambda k:report['inventory'][k]['cash_cost']+v*report['inventory'][k]['consumed_kwh'])] for v in [0,vlo,vhi]]
    assert ranks[0]==ranks[1]==ranks[2]
    report['inventory_value_interval']=[vlo,vhi];report['main_cost_order']=ranks[0]
    report['seconds']=perf_counter()-begin
    (R/'review_diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['q2_energy'],ensure_ascii=False),flush=True)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
