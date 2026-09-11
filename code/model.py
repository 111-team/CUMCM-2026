"""C题：仅使用决策时刻可获得信息的预测、线性规划与执行反馈。"""
from pathlib import Path
from time import perf_counter
import numpy as np
from openpyxl import load_workbook
from scipy.optimize import linprog
from scipy.sparse import eye, diags, hstack, vstack, csr_matrix

DT = 1 / 6
ETA = 0.9
EMIN, EMAX, EINIT, PMAX = 1200., 10800., 6000., 5000.
N = 144
METHODS = ('last', 'mean3', 'mean7', 'ewma14', 'weekday')


def read_rows(path, sheet=0):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
    rows = list(ws.values)
    wb.close()
    return rows


def load_data(root):
    root = Path(root)
    r = read_rows(root / '附件1.xlsx')
    one = np.asarray([row[1:] for row in r[1:]], float)
    actual = []
    for sheet in ('小区负载', '光伏发电实际功率'):
        rows = read_rows(root / '附件2.xlsx', sheet)
        actual.append(np.asarray([row[1:145] for row in rows[1:]], float))
    dates = [row[0].strftime('%Y-%m-%d') for row in rows[1:]]
    price = np.asarray([row[1:145] for row in read_rows(root/'附件4.xlsx')[1:]], float)
    pv_hour = np.asarray([row[2:26] for row in read_rows(root/'附件3.xlsx')[1:]], float).reshape(365, 4, 24)
    data = dict(one=one, load=actual[0], pv=actual[1], price=price, pv_hour=pv_hour, dates=dates)
    for key in ('one', 'load', 'pv', 'price', 'pv_hour'):
        assert np.isfinite(data[key]).all(), key + ': missing/nonfinite data'
        assert (data[key] >= 0).all(), key + ': negative data'
    assert one.shape == (144, 3)
    assert all(data[k].shape == (365, 144) for k in ('load', 'pv', 'price'))
    assert len(set(dates)) == 365
    return data


def predict(history, fallback, method):
    k = len(history)
    if k == 0:
        return np.asarray(fallback).copy()
    if method == 'last':
        return history[-1].copy()
    if method == 'weekday':
        idx = [k-lag for lag in (7, 14, 21, 28) if k >= lag]
        if idx:
            return np.mean(history[idx], axis=0)
        return np.mean(history[-min(k, 7):], axis=0)
    if method.startswith('mean'):
        return np.mean(history[-min(k, int(method[4:])):], axis=0)
    block = history[-min(k, 14):]
    weights = np.exp(-np.arange(len(block)-1, -1, -1)/5)
    return np.average(block, weights=weights, axis=0)


def forecast_all(data):
    """1月15—31日选择方法；1月份实际热启动统一用持久性方法。"""
    forecasts, scores, selected = {}, {}, {}
    for key, fallback in [('load', data['one'][:, 1]), ('pv', data['one'][:, 2]), ('price', data['one'][:, 0])]:
        values = data[key]
        scores[key] = {}
        for method in METHODS:
            errors = np.asarray([predict(values[:d], fallback, method)-values[d] for d in range(14, 31)])
            scores[key][method] = dict(mae=float(np.mean(abs(errors))), rmse=float(np.sqrt(np.mean(errors**2))))
        chosen = min(METHODS, key=lambda m: scores[key][m]['mae'])
        selected[key] = chosen
        forecasts[key] = np.asarray([predict(values[:d], fallback, 'last' if d < 31 else chosen) for d in range(365)])
    # 每次预测只连接已观测到的发布时刻端点和该次发布的未来24个整点预报。
    issued = np.zeros((365, 4, 144))
    for day in range(365):
        for issue in range(4):
            start = issue * 36
            current = data['pv'][day, start-1] if start else (data['pv'][day-1, -1] if day else 0.)
            x = (np.arange(start, 144)+1-start)/6
            issued[day, issue, start:] = np.interp(x, np.arange(25), np.r_[current, data['pv_hour'][day, issue]])
    forecasts['issued'] = issued
    return forecasts, scores, selected


def residual_scenarios(data, forecast, day, start, issue=None, history_days=14):
    """当前净负荷预测 + 最近14天在相同发布时刻产生的整条误差轨迹。"""
    pv_forecast = forecast['pv'] if issue is None else forecast['issued'][:, issue]
    nominal = forecast['load'][day, start:] - pv_forecast[day, start:]
    if history_days == 0 or day == 0:
        return nominal[None, :]
    left = max(0, day-history_days)
    errors = data['load'][left:day, start:]-data['pv'][left:day, start:] \
             -(forecast['load'][left:day, start:]-pv_forecast[left:day, start:])
    return np.vstack((nominal, nominal+errors))


def optimize(scenarios, prices, initial, base=None, settlement='additive', cyclic=False, eta=ETA, pmax=PMAX):
    """稀疏LP。紧急量为场景中的缺额补救变量，实际费用由execute重新核算。"""
    start_time = perf_counter()
    s, n = scenarios.shape
    ident = eye(n, format='csr')
    zero = csr_matrix((n, n))
    delta = ident - diags(np.ones(n-1), -1, shape=(n, n), format='csr')
    extra = 2*n if base is not None else 0
    eq = hstack([zero, -eta*DT*ident, DT/eta*ident, delta, csr_matrix((n, s*n+extra))], format='csr')
    eq_rhs = np.zeros(n)
    eq_rhs[0] = initial
    tile = vstack([ident]*s, format='csr')
    ub = hstack([-tile, tile, -tile, csr_matrix((s*n,n)), -eye(s*n,format='csr'), csr_matrix((s*n,extra))],format='csr')
    c = np.r_[prices*DT if base is None else np.zeros(n), np.zeros(3*n), np.tile(5*prices*DT/s,s)]
    bounds = [(0,None)]*n + [(0,pmax)]*(2*n) + [(EMIN,EMAX)]*n + [(0,None)]*(s*n)
    if cyclic:
        bounds[4*n-1] = (initial,initial)
    if base is not None:
        adjust_eq = hstack([ident,csr_matrix((n,3*n+s*n)),-ident,ident],format='csr')
        eq = vstack([eq,adjust_eq],format='csr')
        eq_rhs = np.r_[eq_rhs,base]
        c = np.r_[c,1.5*prices*DT,(0.5 if settlement=='additive' else -0.5)*prices*DT]
        bounds += [(0,None)]*(2*n)
    # 单日确定性问题必须由常规购电满足负荷，不使用场景紧急量。
    if cyclic:
        for idx in range(4*n,4*n+s*n):
            bounds[idx]=(0,0)
    result=linprog(c,A_ub=ub,b_ub=-scenarios.ravel(),A_eq=eq,b_eq=eq_rhs,bounds=bounds,method='highs')
    if not result.success:
        raise RuntimeError(result.message)
    g,ch,dis,energy=np.split(result.x[:4*n],4)
    # 精确消除同时充放电：状态增量不变，供给裕量增加，由弃电变量吸收。
    amount=np.minimum(ch,dis/eta**2)
    ch=ch-amount
    dis=dis-eta**2*amount
    assert np.max(np.minimum(ch,dis)) < 1e-6
    return dict(grid=g,ch=ch,dis=dis,energy=energy,objective=float(result.fun),seconds=perf_counter()-start_time,
                residual_eq=float(np.max(np.abs(eq@result.x-eq_rhs))),residual_ub=float(np.max(ub@result.x+scenarios.ravel())))


def execute(grid, load, pv, initial, eta=ETA, pmax=PMAX):
    """电网侧功率跟随控制，先用盈余充电；有缺额时放电，再紧急购电。"""
    n=len(grid)
    ch,dis,emergency,spill=np.zeros((4,n))
    energy=np.zeros(n+1)
    energy[0]=initial
    for t in range(n):
        residual=grid[t]+pv[t]-load[t]
        if residual >= 0:
            ch[t]=min(residual,pmax,max(0,(EMAX-energy[t])/(eta*DT)))
            spill[t]=residual-ch[t]
        else:
            dis[t]=min(-residual,pmax,max(0,(energy[t]-EMIN)*eta/DT))
            emergency[t]=-residual-dis[t]
        energy[t+1]=energy[t]+eta*DT*ch[t]-DT/eta*dis[t]
    return dict(ch=ch,dis=dis,emergency=emergency,spill=spill,energy=energy)


def run_case(data,forecast,kind=2,price_mode='fixed',updates=(0,6,12,18),settlement='additive',history_days=14,eta=ETA):
    begin=perf_counter()
    arrays={key:np.zeros((365,144)) for key in ('plan','grid','ch','dis','emergency','spill')}
    arrays['energy']=np.zeros((365,145))
    costs=np.zeros((365,5))  # 计划、上调、下调、紧急、合计
    state=EINIT
    lp_seconds=0.; max_eq=0.; max_ub=0.; solves=0
    issue_numbers=[0] if kind==2 else [h//6 for h in updates]
    for day in range(365):
        realized_price=data['one'][:,0] if price_mode=='fixed' else data['price'][day]
        planning_price=forecast['price'][day] if price_mode=='forecast' else realized_price
        arrays['energy'][day,0]=state
        for i,issue in enumerate(issue_numbers):
            start=issue*36
            end=issue_numbers[i+1]*36 if i+1<len(issue_numbers) else 144
            scenarios=residual_scenarios(data,forecast,day,start,None if kind==2 else issue,history_days)
            base=arrays['plan'][day,start:] if start else None
            solution=optimize(scenarios,planning_price[start:],state,base,settlement,eta=eta)
            lp_seconds+=solution['seconds']; solves+=1
            max_eq=max(max_eq,solution['residual_eq']);max_ub=max(max_ub,solution['residual_ub'])
            if start==0:
                arrays['plan'][day]=solution['grid']
            g=solution['grid'][:end-start]
            arrays['grid'][day,start:end]=g
            actual=execute(g,data['load'][day,start:end],data['pv'][day,start:end],state,eta=eta)
            for key in ('ch','dis','emergency','spill'):
                arrays[key][day,start:end]=actual[key]
            arrays['energy'][day,start:end+1]=actual['energy']
            state=actual['energy'][-1]
        diff=arrays['grid'][day]-arrays['plan'][day]
        costs[day,0]=DT*np.dot(realized_price,arrays['plan'][day])
        costs[day,1]=DT*np.dot(1.5*realized_price,np.maximum(diff,0))
        costs[day,2]=DT*np.dot((.5 if settlement=='additive' else -.5)*realized_price,np.maximum(-diff,0))
        costs[day,3]=DT*np.dot(5*realized_price,arrays['emergency'][day])
        costs[day,4]=np.sum(costs[day,:4])
    arrays['costs']=costs
    info=dict(kind=kind,price_mode=price_mode,updates=updates,settlement=settlement,history_days=history_days,eta=eta,
              seconds=perf_counter()-begin,lp_seconds=lp_seconds,solves=solves,max_eq_residual=max_eq,max_ub_violation=max_ub)
    audit(data,arrays,eta)
    return arrays,info


def audit(data,arrays,eta=ETA):
    g,ch,dis,em,spill=[arrays[k] for k in ('grid','ch','dis','emergency','spill')]
    e=arrays['energy']
    residual=g+data['pv']+dis+em-data['load']-ch-spill
    assert np.max(abs(residual))<1e-6
    assert np.min(e)>=EMIN-1e-6 and np.max(e)<=EMAX+1e-6
    assert np.max(np.minimum(ch,dis))<1e-6
    assert np.max(ch)<=PMAX+1e-6 and np.max(dis)<=PMAX+1e-6
    assert np.max(abs(np.diff(e,axis=1)-eta*DT*ch+DT/eta*dis))<1e-6
    assert np.max(abs(e[:-1,-1]-e[1:,0]))<1e-6
    assert abs(e[0,0]-EINIT)<1e-6
    assert (em>=-1e-6).all() and (g>=-1e-6).all()


def summarize(arrays,info):
    section=slice(31,365)
    c=arrays['costs'][section].sum(axis=0)
    out=dict(info)
    for name,val in zip(('plan_cost','up_cost','down_cost','emergency_cost','total_cost'),c):
        out[name]=float(val)
    for name in ('plan','grid','ch','dis','emergency','spill'):
        out[name+'_kwh']=float(arrays[name][section].sum()*DT)
    out['emergency_periods']=int(np.sum(arrays['emergency'][section]>1e-6))
    out['emergency_days']=int(np.sum(np.any(arrays['emergency'][section]>1e-6,axis=1)))
    out['start_energy']=float(arrays['energy'][31,0]);out['end_energy']=float(arrays['energy'][-1,-1])
    out['up_kwh']=float(np.maximum(arrays['grid'][section]-arrays['plan'][section],0).sum()*DT)
    out['down_kwh']=float(np.maximum(arrays['plan'][section]-arrays['grid'][section],0).sum()*DT)
    out['equivalent_cycles']=float((info['eta']*out['ch_kwh']+out['dis_kwh']/info['eta'])/(2*(EMAX-EMIN)))
    return out
