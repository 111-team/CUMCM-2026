"""绘制3.7复核补充图表；只使用实际计算记录，沿用论文 MATLAB 配色。"""
from pathlib import Path
import json,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[1];R=ROOT/'results';F=ROOT/'figures';T=ROOT/'tables'
D=json.loads((R/'review_diagnostics.json').read_text(encoding='utf-8'))
X=json.loads((R/'diagnostics.json').read_text(encoding='utf-8'))
RF=json.loads((R/'refinements.json').read_text(encoding='utf-8'))
for name in ['simsun.ttc','times.ttf']:
    p=Path('C:/Windows/Fonts')/name
    if p.exists():font_manager.fontManager.addfont(str(p))
plt.rcParams.update({'font.family':['Times New Roman','SimSun','DejaVu Sans'],'font.size':10,'axes.labelsize':10,
 'axes.linewidth':.7,'xtick.direction':'in','ytick.direction':'in','axes.unicode_minus':False,
 'pdf.fonttype':42,'savefig.bbox':'tight','figure.facecolor':'white','axes.facecolor':'white',
 'legend.fancybox':False,'legend.edgecolor':'.65','legend.fontsize':9,'grid.linewidth':.45})
B='#0072BD';O='#D95319';Y='#EDB120';P='#7E2F8E';G='#77AC30';C='#4DBEEE'
manifest=[]
def tidy(ax):
    ax.grid(True,color='#D9D9D9',alpha=.75);ax.set_axisbelow(True)
    for s in ax.spines.values():s.set_color('#555555')
def save(fig,name,source):
    fig.savefig(F/(name+'.pdf'));fig.savefig(F/'previews'/(name+'.png'),dpi=175);plt.close(fig)
    manifest.append({'file':name+'.pdf','source':source})
def table(name,caption,label,head,rows,spec):
    lines=[r'\begin{table}[H]\centering\small',r'\caption{'+caption+'}'+r'\label{tab:'+label+'}',r'\begin{tabular}{'+spec+r'}\toprule', ' & '.join(head)+r'\\\midrule']
    lines+=[' & '.join(map(str,row))+r'\\' for row in rows]
    lines += [r'\bottomrule\end{tabular}\end{table}']
    (T/(name+'.tex')).write_text('\n'.join(lines)+'\n',encoding='utf-8')

e=D['q2_energy'];fig,axs=plt.subplots(1,2,figsize=(6.8,2.75),layout='constrained')
ax=axs[0];vals=[e['spill_kwh']/1e4,e['loss_kwh']/1e4,e['stock_change_kwh']/1e4]
ax.bar([0,1,2],vals,color=[O,B,G],width=.6,edgecolor='white')
for i,v in enumerate(vals):ax.annotate(f'{v:.2f}',(i,v),xytext=(0,4 if v>=0 else -12),textcoords='offset points',ha='center',fontsize=9)
ax.axhline(0,color='.4',lw=.7);ax.set(xticks=[0,1,2],xticklabels=['未利用供给','储能损耗','库存净增加'],ylabel='电量 / 万kWh',ylim=(-30,320),title='(a) 总购电超过净负荷的构成');tidy(ax)
ax=axs[1];paid=np.array(e['paid_spill_kwh_interval'])/1e4;pv=e['spill_kwh']/1e4-paid
ax.barh([0,1],pv,color=Y,label='光伏来源');ax.barh([0,1],paid,left=pv,color=B,label='外购来源')
for i in [0,1]:
    ax.text(pv[i]/2,i,f'{pv[i]:.1f}',ha='center',va='center');ax.text(pv[i]+paid[i]/2,i,f'{paid[i]:.1f}',ha='center',va='center',color='white')
ax.set(yticks=[0,1],yticklabels=['外购优先充电','光伏优先充电'],xlabel='未利用电量 / 万kWh',xlim=(0,300),ylim=(-.7,1.8),title='(b) 光伏先供负荷后的两种来源归属');ax.legend(loc='upper right',ncol=2,fontsize=8);tidy(ax)
save(fig,'unused_energy','review_diagnostics.json q2_energy; source attribution conditional on PV-first load; no new cash fee')

rows=D['risk_scan'];xx=np.arange(4);fig,axs=plt.subplots(1,2,figsize=(6.8,2.7),layout='constrained')
ax=axs[0];cost=np.array([r['cost'] for r in rows])/1e4;ax.plot(xx,cost,'o-',color=B,lw=1.3)
for i,v in enumerate(cost):ax.annotate(f'{v:.2f}',(i,v),xytext=(0,9),textcoords='offset points',ha='center',fontsize=8)
ax.set(xticks=xx,xticklabels=[r['rho'] for r in rows],xlabel='计划阶段惩罚权重 ρ',ylabel='实际总费用 / 万元',xlim=(-.3,3.35),ylim=(1370,1510),title='(a) 实际费用在四组中以ρ=5最低');tidy(ax)
ax=axs[1];spill=np.array([r['spill_kwh'] for r in rows])/1e4;em=np.array([r['emergency_kwh'] for r in rows])/1e4
ax.plot(spill,em,'s--',color=O,lw=1.2)
for row,x,y in zip(rows,spill,em):ax.annotate('ρ='+str(row['rho']),(x,y),xytext=(6,5),textcoords='offset points',fontsize=9)
ax.set(xlabel='未利用电量 / 万kWh',ylabel='紧急电量 / 万kWh',xlim=(140,380),ylim=(0,51),title='(b) 更保守的计划减少缺额、增加弃电');tidy(ax)
save(fig,'risk_tradeoff','review_risk{2,3,5,8}.npz; common 2025-02-01 initial SOC; actual emergency price remains 5 times')
table('review_risk','仅改变计划惩罚权重的连续回测（实际紧急电仍按5倍价）','review_risk',
 ['计划权重','总费用/万元','未利用电量/万kWh','紧急电量/万kWh'],
 [[r['rho'],f"{r['cost']/1e4:.2f}",f"{r['spill_kwh']/1e4:.2f}",f"{r['emergency_kwh']/1e4:.2f}"] for r in rows],'rrrr')

eff=D['efficiency'];labels=['单程均0.9（主设定）','回路0.9，对称分配','仅充电有损耗','仅放电有损耗']
fig,ax=plt.subplots(figsize=(6.8,2.35),layout='constrained');yy=np.arange(4);vals=[r['cost']/1e4 for r in eff]
ax.barh(yy,vals,color=[B,O,G,P],height=.57,edgecolor='white')
for i,(r,v) in enumerate(zip(eff,vals)):ax.text(v+.035,i,f"{r['cost']:.2f} 元",va='center',fontsize=9)
ax.set(yticks=yy,yticklabels=labels,xlabel='附件1单日购电费用 / 万元',xlim=(0,4.5));ax.invert_yaxis();tidy(ax)
save(fig,'efficiency_interpretation','Independent LP in review_experiments.py, same attachment1 and same capacity and endpoints; different efficiencies')
table('review_efficiency','效率解释改变问题1费用，主设定维持两侧各0.9','review_efficiency',
 ['效率解释',r'$\eta_c$',r'$\eta_d$','费用/元','较主设定变化'],
 [[l,f"{r['eta_c']:.4f}",f"{r['eta_d']:.4f}",f"{r['cost']:.2f}",f"{(r['cost']/eff[0]['cost']-1)*100:.2f}"+r'\%'] for l,r in zip(labels,eff)],'lrrrr')

sh=X['scenario_shuffle'];fig,axs=plt.subplots(1,2,figsize=(6.8,2.55),layout='constrained')
ax=axs[0];delta=[sh['objective_difference'],sh['permuted_feedback_cost']-sh['original_feedback_cost']]
ax.bar([0,1],delta,color=[B,O],width=.5)
for i,v in enumerate(delta):ax.text(i,v+8,'约0' if i==0 else f'{v:.2f}',ha='center',fontsize=9)
ax.set(xticks=[0,1],xticklabels=['代理目标变化','实际反馈费用变化'],ylabel='打乱后减去原场景 / 元',ylim=(-10,260),title='(a) 9月23日时间配对诊断');tidy(ax)
ax=axs[1];gate=RF['cases']['q3_gate'];acc=gate['accepted'];rej=gate['rejected']
ax.barh([0,1],[acc,rej],color=[B,Y],height=.55)
for i,v in enumerate([acc,rej]):ax.text(v+10,i,str(v),va='center',fontsize=9)
ax.set(yticks=[0,1],yticklabels=['采纳候选','保留原安排'],xlabel='更新机会数',xlim=(0,750),title='(b) 重复电价下门控决策（1002次）');ax.invert_yaxis();tidy(ax)
save(fig,'proxy_and_gate','diagnostics.json scenario_shuffle and refinements.json q3_gate; separate diagnostics, not causal relation')

report={'figures':manifest,'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'review_diagnostics.json',R/'diagnostics.json',R/'refinements.json']}}
(R/'review_figure_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Generated 4 supplementary figure groups and 2 tables.')
