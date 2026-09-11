"""从计算结果自动生成论文数值宏、表格、图形和典型日分析数据。"""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from model import DT,EINIT,ETA,EMAX,EMIN
from export_results import events

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results';T=ROOT/'tables';F=ROOT/'figures'
T.mkdir(exist_ok=True);F.mkdir(exist_ok=True)
S=json.loads((R/'summary.json').read_text(encoding='utf-8'))
CASES={k:dict(np.load(R/(k+'.npz'))) for k in S['cases']}
Q=dict(np.load(R/'q1.npz'));I=dict(np.load(R/'inputs_processed.npz'))
DATES=['2025-03-20','2025-06-21','2025-09-23','2025-12-21']
INDEX=[S['dates'].index(d) for d in DATES]
LABELS={'q2':'问题2','q3':'问题3','q4_2':'问题4-2','q4_3':'问题4-3','q2_nominal':'点预测基准','q3_daily':'仅0时','q3_noon':'0、12时','q3_refund':'退费口径','q4_2_known':'价格已知：日前','q4_3_known':'价格已知：滚动','q4_3_refund':'波动电价退费口径','q3_history7':'7天窗口','q3_history28':'28天窗口'}
def num(x):return f'{float(x):.2f}'
def save_table(name,caption,headers,rows,label=None):
    text='\\begin{table}[H]\n\\centering\\small\n\\caption{'+caption+'}\n'
    if label:text+='\\label{'+label+'}\n'
    text+='\\begin{tabular}{'+'l'+'r'*(len(headers)-1)+'}\\toprule\n'
    text+=' & '.join(headers)+' \\\\\\midrule\n'
    text+='\n'.join(' & '.join(map(str,row))+' \\\\' for row in rows)
    text+='\n\\bottomrule\\end{tabular}\n\\end{table}\n'
    (T/(name+'.tex')).write_text(text,encoding='utf-8')

def purchase(name,caption,g,cost):
    hours=[10,12,14,16,18,20]
    rows=[]
    for line in range(2):
        row=[]
        for h in hours[line*3:line*3+3]:row += [f'{h}:00--{h}:10',num(g[h*6]*DT)]
        rows.append(row)
    text='\\begin{table}[H]\\centering\\small\n\\caption{'+caption+'}\n\\label{tab:'+name+'}\n\\begin{tabular}{lrlrlr}\\toprule\n'
    text+='时段 & 购电量 & 时段 & 购电量 & 时段 & 购电量 \\\\\\midrule\n'
    text+='\n'.join(' & '.join(row)+' \\\\' for row in rows)
    text+='\n\\midrule\n\\multicolumn{3}{l}{全天常规购电量：'+num(g.sum()*DT)+' kWh} & \\multicolumn{3}{r}{全天总费用：'+num(cost)+' 元}\\\\\n\\bottomrule\\end{tabular}\\end{table}\n'
    (T/(name+'.tex')).write_text(text,encoding='utf-8')

def storage(name,caption,ch,dis,e0,e1):
    text='\\begin{table}[H]\\centering\\small\n\\caption{'+caption+'}\n\\label{tab:'+name+'}\n\\begin{tabular}{lrrlrr}\\toprule\n时段 & 充电量 & 放电量 & 时段 & 充电量 & 放电量\\\\\\midrule\n'
    for pair in range(3):
        row=[]
        for b in [pair*2,pair*2+1]:
            sl=slice(b*24,(b+1)*24)
            row += [f'{b*4}:00--{(b+1)*4}:00',num(ch[sl].sum()*DT),num(dis[sl].sum()*DT)]
        text+=' & '.join(row)+' \\\\\n'
    text+='\\midrule\\multicolumn{3}{l}{0:00储电量：'+num(e0)+'} & \\multicolumn{3}{r}{24:00储电量：'+num(e1)+'}\\\\\n\\bottomrule\\end{tabular}\\end{table}\n'
    (T/(name+'.tex')).write_text(text,encoding='utf-8')

purchase('q1_purchase','问题1指定时段常规购电量（电量单位：kWh）',Q['grid'],Q['objective'])
storage('q1_storage','问题1储能充放电量与边界电量（单位：kWh）',Q['ch'],Q['dis'],EINIT,Q['energy'][-1])
typical={}
for key in ['q2','q3','q4_2','q4_3']:
    a=CASES[key];typical[key]=[]
    for day,idx in zip(DATES,INDEX):
        token=day[5:].replace('-','')
        purchase(key+'_'+token+'_purchase',LABELS[key]+'：'+day+'指定时段常规购电量（kWh）',a['grid'][idx],a['costs'][idx,4])
        storage(key+'_'+token+'_storage',LABELS[key]+'：'+day+'实际充放电量（kWh）',a['ch'][idx],a['dis'][idx],a['energy'][idx,0],a['energy'][idx,-1])
        typical[key].append(dict(date=day,plan=float(a['plan'][idx].sum()*DT),grid=float(a['grid'][idx].sum()*DT),emergency=float(a['emergency'][idx].sum()*DT),cost=a['costs'][idx].tolist(),start=float(a['energy'][idx,0]),end=float(a['energy'][idx,-1]),events=events(a['emergency'][idx])))
    groups=[events(a['emergency'][idx]) or [('无',0.)] for idx in INDEX]
    text='\\begin{table}[H]\\centering\\scriptsize\n\\caption{'+LABELS[key]+'四个指定日期的连续紧急购电事件（kWh）}\\label{tab:'+key+'_emergency}\n\\begin{tabular}{lrlrlrlr}\\toprule\n'
    text+=' & '.join('\\multicolumn{2}{c}{'+d[5:]+'}' for d in DATES)+' \\\\\n'
    text+=' & '.join(['时段 & 电量']*4)+' \\\\\\midrule\n'
    for r in range(max(map(len,groups))):
        row=[]
        for g in groups:row += [g[r][0].replace('-','--'),num(g[r][1])] if r<len(g) else ['--','--']
        text+=' & '.join(row)+' \\\\\n'
    text+='\\bottomrule\\end{tabular}\\end{table}\n'
    (T/(key+'_emergency.tex')).write_text(text,encoding='utf-8')
    save_table(key+'_daily_summary',LABELS[key]+'典型日购电与费用汇总',['日期','原计划/kWh','调整后/kWh','紧急/kWh','总费用/元'],[[r['date'][5:],num(r['plan']),num(r['grid']),num(r['emergency']),num(r['cost'][4])] for r in typical[key]],'tab:'+key+'_daily_summary')

save_table('annual','2--12月主模型费用分解（单位：万元）',['模型','计划费','上调费','下调净费','紧急费','总费用'],[[LABELS[k]]+[num(S['cases'][k][field]/10000) for field in ['plan_cost','up_cost','down_cost','emergency_cost','total_cost']] for k in ['q2','q3','q4_2','q4_3']],'tab:annual')
save_table('risk_compare','问题2是否纳入历史误差风险的比较',['方案','计划电量/万kWh','紧急电量/kWh','紧急天数','总费用/万元'],[[LABELS[k],num(S['cases'][k]['plan_kwh']/1e4),num(S['cases'][k]['emergency_kwh']),S['cases'][k]['emergency_days'],num(S['cases'][k]['total_cost']/1e4)] for k in ['q2_nominal','q2']],'tab:risk')
save_table('frequency','问题3不同预报更新频率的比较',['使用的预报时刻','上调费用/元','紧急电量/kWh','总费用/元'],[[('0、6、12、18时' if k=='q3' else LABELS[k]),num(S['cases'][k]['up_cost']),num(S['cases'][k]['emergency_kwh']),num(S['cases'][k]['total_cost'])] for k in ['q3_daily','q3_noon','q3']],'tab:frequency')
save_table('settlement','两种结算口径的敏感性比较',['价格条件与口径','下调电量/kWh','下调净费/元','总费用/元'],[[label,num(S['cases'][k]['down_kwh']),num(S['cases'][k]['down_cost']),num(S['cases'][k]['total_cost'])] for k,label in [('q3','重复日内价，主口径'),('q3_refund','重复日内价，退费'),('q4_3','波动电价，主口径'),('q4_3_refund','波动电价，退费')]],'tab:settlement')
save_table('price_information','波动电价下价格信息的作用',['模型与信息','计划费/万元','紧急电量/kWh','总费用/万元','等效循环'],[[label,num(S['cases'][k]['plan_cost']/1e4),num(S['cases'][k]['emergency_kwh']),num(S['cases'][k]['total_cost']/1e4),num(S['cases'][k]['equivalent_cycles'])] for k,label in [('q4_2','日前，价格预测'),('q4_2_known','日前，价格已知'),('q4_3','滚动，价格预测'),('q4_3_known','滚动，价格已知')]],'tab:price_information')
save_table('window','问题3历史误差窗口的敏感性比较',['历史窗口/天','紧急电量/kWh','总费用/元','2月初SOC/kWh','年底SOC/kWh'],[[w,num(S['cases'][k]['emergency_kwh']),num(S['cases'][k]['total_cost']),num(S['cases'][k]['start_energy']),num(S['cases'][k]['end_energy'])] for w,k in [(7,'q3_history7'),(14,'q3'),(28,'q3_history28')]],'tab:window')
save_table('runtime','主模型的实测运行时间（含全年初始化）',['模型','LP次数','LP耗时/s','全年仿真/s'],[[LABELS[k],S['cases'][k]['solves'],num(S['cases'][k]['lp_seconds']),num(S['cases'][k]['seconds'])] for k in ['q2','q3','q4_2','q4_3']],'tab:runtime')
save_table('forecast','历史预测方法的验证与测试误差',['变量','选定方法','1月验证MAE','2--12月MAE','2--12月WAPE'],[[label,method,num(S['january_validation'][k][S['selected_forecasts'][k]]['mae']),num(S['forecast_feb_dec'][k]['mae']) if k!='price' else f"{S['forecast_feb_dec'][k]['mae']:.4f}",f"{100*S['forecast_feb_dec'][k]['wape']:.2f}\\%"] for k,label,method in [('load','负载/kW','同星期均值'),('pv','光伏/kW','7日移动均值'),('price','电价/(元/kWh)','同星期均值')]],'tab:forecast')

plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':9,'axes.unicode_minus':False,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'savefig.bbox':'tight'})
BLUE='#245e8c';ORANGE='#c57639';GREEN='#37776b';GRAY='#6a727b'
hours=np.arange(144)/6
fig,ax=plt.subplots(3,1,figsize=(7.0,6.4),sharex=True,layout='constrained')
ax[0].plot(hours,Q['load']/1000,label='负载',color=GRAY);ax[0].plot(hours,Q['pv']/1000,label='光伏',color=ORANGE);ax[0].step(hours,Q['grid']/1000,label='计划购电',color=BLUE,where='post');ax[0].set_ylabel('功率 / MW');ax[0].legend(ncol=3,loc='upper center',fontsize=8)
ax[1].step(hours,Q['ch']/1000,color=GREEN,label='充电',where='post');ax[1].step(hours,-Q['dis']/1000,color=ORANGE,label='放电（负向）',where='post');ax[1].set_ylabel('功率 / MW');ax[1].legend(ncol=2,fontsize=8)
ax[2].plot(np.arange(145)/6,np.r_[EINIT,Q['energy']]/1000,color=BLUE,label='储电量');ax[2].axhline(1.2,color=GRAY,ls='--',lw=.8);ax[2].axhline(10.8,color=GRAY,ls='--',lw=.8);ax[2].set_ylabel('储电量 / MWh');ax[2].set_xlabel('时刻 / h');right=ax[2].twinx();right.plot(hours,Q['price'],color=ORANGE,alpha=.7,label='电价');right.set_ylabel('电价 / (元/kWh)');ax[2].set_xlim(0,24);ax[2].set_xticks(np.arange(0,25,4));fig.savefig(F/'q1_dispatch.pdf');plt.close(fig)

fig,ax=plt.subplots(2,1,figsize=(7,4.8),sharex=True,layout='constrained')
months=np.array([int(d[5:7]) for d in S['dates']]);monthly={}
for k,color in [('q2',BLUE),('q3',GREEN)]:
    em=[CASES[k]['emergency'][months==m].sum()*DT/1000 for m in range(2,13)]
    cost=[CASES[k]['costs'][months==m,4].sum()/10000 for m in range(2,13)]
    ax[0].plot(range(2,13),em,'o-',color=color,label=LABELS[k]);ax[1].plot(range(2,13),cost,'o-',color=color,label=LABELS[k]);monthly[k]={'emergency_mwh':em,'cost_10k':cost}
ax[0].set_ylabel('紧急购电量 / MWh');ax[0].legend(ncol=2);ax[1].set_ylabel('总费用 / 万元');ax[1].set_xlabel('月份');ax[1].set_xticks(range(2,13));fig.savefig(F/'monthly_comparison.pdf');plt.close(fig)

idx=INDEX[2];a=CASES['q3'];fig,ax=plt.subplots(2,1,figsize=(7,4.5),sharex=True,layout='constrained')
ax[0].step(hours,a['plan'][idx]/1000,label='0时计划',color=GRAY,where='post');ax[0].step(hours,a['grid'][idx]/1000,label='最终常规购电',color=BLUE,where='post');ax[0].plot(hours,a['emergency'][idx]/1000,label='紧急购电',color=ORANGE);ax[0].set_ylabel('购电功率 / MW');ax[0].legend(ncol=3,fontsize=8)
ax[1].plot(np.arange(145)/6,a['energy'][idx]/1000,color=GREEN,label='实际储电量');ax[1].set_ylabel('储电量 / MWh');ax[1].set_xlabel('时刻 / h');ax[1].legend();ax[1].set_xticks(np.arange(0,25,6));ax[1].set_xlim(0,24)
for axis in ax:
    for x in [6,12,18]:axis.axvline(x,color=GRAY,lw=.7,ls='--')
fig.savefig(F/'q3_typical.pdf');plt.close(fig)

idx=INDEX[1];fig,ax=plt.subplots(2,1,figsize=(7,4.5),sharex=True,layout='constrained')
ax[0].plot(hours,I['price'][idx],color=ORANGE,label='实际波动电价');ax[0].plot(hours,I['forecast_price'][idx],color=BLUE,label='日前价格预测');ax[0].plot(hours,Q['price'],color=GRAY,ls='--',label='重复日内电价');ax[0].set_ylabel('电价 / (元/kWh)');ax[0].legend(ncol=3,fontsize=8)
for k,color in [('q4_3',BLUE),('q4_3_known',GREEN)]:ax[1].plot(np.arange(145)/6,CASES[k]['energy'][idx]/1000,color=color,label='价格预测' if k=='q4_3' else '价格已知')
ax[1].set_ylabel('储电量 / MWh');ax[1].set_xlabel('时刻 / h');ax[1].set_xlim(0,24);ax[1].set_xticks(np.arange(0,25,4));ax[1].legend(ncol=2);fig.savefig(F/'q4_price.pdf');plt.close(fig)

fig,ax=plt.subplots(figsize=(7,3.5),layout='constrained');keys=['q2','q3','q4_2','q4_3'];x=np.arange(4);bottom=np.zeros(4)
for fld,label,color in [('plan_cost','计划费',BLUE),('up_cost','调整上调费',ORANGE),('emergency_cost','紧急费',GREEN)]:
    val=np.array([S['cases'][k][fld]/10000 for k in keys]);ax.bar(x,val,bottom=bottom,label=label,color=color,width=.55);bottom+=val
for xx,yy in zip(x,bottom):ax.text(xx,yy+8,f'{yy:.2f}',ha='center',fontsize=9)
ax.set_xticks(x,[LABELS[k] for k in keys]);ax.set_ylabel('费用 / 万元');ax.set_ylim(0,max(bottom)*1.15);ax.legend(ncol=3,loc='upper left');fig.savefig(F/'annual_costs.pdf');plt.close(fig)

metrics={'typical':typical,'monthly':monthly,'q1_saving_percent':100*(1-float(Q['objective'])/S['q1']['net_cost']),'q2_risk_saving_percent':100*(1-S['cases']['q2']['total_cost']/S['cases']['q2_nominal']['total_cost']),'q3_frequency_saving_percent':100*(1-S['cases']['q3']['total_cost']/S['cases']['q3_daily']['total_cost']),'q3_emergency_reduction_percent':100*(1-S['cases']['q3']['emergency_kwh']/S['cases']['q3_daily']['emergency_kwh'])}
(R/'analysis_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'q1':S['q1'],'metrics':{k:v for k,v in metrics.items() if k not in ['typical','monthly']},'typical':typical},ensure_ascii=False))
