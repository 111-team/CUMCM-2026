"""从已核对的轨迹绘制论文图组；白底、细框、多线型，采用 MATLAB 常用配色。
只生成图和描述统计，不重新求解，不改写主结果。先运行原复现流程获得 NPZ。
"""
from pathlib import Path
import json, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle, FancyArrowPatch, Polygon
from matplotlib.ticker import AutoMinorLocator

ROOT=Path(__file__).resolve().parents[1];R=ROOT/'results';F=ROOT/'figures'
F.mkdir(exist_ok=True);P=F/'previews';P.mkdir(exist_ok=True)
S=json.loads((R/'summary.json').read_text(encoding='utf-8'))
D=json.loads((R/'diagnostics.json').read_text(encoding='utf-8'))
RF=json.loads((R/'refinements.json').read_text(encoding='utf-8'))
Q=dict(np.load(R/'q1.npz'));I=dict(np.load(R/'inputs_processed.npz'))
keys=('q2','q3','q4_2','q4_3','q3_daily','q3_noon','q4_3_known')
A={k:dict(np.load(R/(k+'.npz'))) for k in keys}
DT=1/6;start=31;h=np.arange(144)/6;edges=np.arange(145)/6
dates=np.array(S['dates']);months=np.array([int(d[5:7]) for d in dates]);ms=np.arange(2,13)
for k,a in A.items():
    assert abs(a['costs'][start:,4].sum()-S['cases'][k]['total_cost'])<1e-5,k
    assert abs(a['emergency'][start:].sum()*DT-S['cases'][k]['emergency_kwh'])<1e-5,k
    assert np.max(abs(a['energy'][:-1,-1]-a['energy'][1:,0]))<1e-7,k
for font in ('simsun.ttc','times.ttf'):
    p=Path('C:/Windows/Fonts')/font
    if p.exists():font_manager.fontManager.addfont(str(p))
plt.rcParams.update({'font.family':['Times New Roman','SimSun','DejaVu Sans'],'font.size':10,
 'axes.labelsize':10,'axes.titlesize':10,'axes.linewidth':.7,'lines.linewidth':1.25,
 'xtick.direction':'in','ytick.direction':'in','xtick.major.size':3,'ytick.major.size':3,
 'axes.unicode_minus':False,'pdf.fonttype':42,'ps.fonttype':42,'savefig.facecolor':'white',
 'axes.facecolor':'white','figure.facecolor':'white','legend.frameon':True,'legend.fancybox':False,
 'legend.edgecolor':'0.65','legend.framealpha':.95,'legend.fontsize':9,'grid.linewidth':.45,
 'axes.spines.top':True,'axes.spines.right':True,'savefig.bbox':'tight'})
BLUE='#0072BD';ORANGE='#D95319';YELLOW='#EDB120';PURPLE='#7E2F8E';GREEN='#77AC30';CYAN='#4DBEEE';RED='#A2142F';GRAY='#606060'
colors=[BLUE,ORANGE,YELLOW,PURPLE,GREEN,CYAN,RED]
metrics={'source':'Existing trajectories; 2025-02-01 to 2025-12-31 unless stated otherwise',
 'plot_style':'White background, fine boxed axes, restrained grid, differentiated lines and markers; MATLAB palette',
 'main_result_checks':'passed','figures':[]}

def axes_style(ax,grid=True):
    if grid:ax.grid(True,color='#D9D9D9',alpha=.75)
    ax.set_axisbelow(True)
    for s in ax.spines.values():s.set_color('#555555')

def sub(ax,title):ax.set_title(title,pad=8)

def save(fig,name,source):
    fig.savefig(F/(name+'.pdf'));fig.savefig(P/(name+'.png'),dpi=175);plt.close(fig)
    metrics['figures'].append({'file':name+'.pdf','data_or_definition':source})

def box(ax,xy,w,hh,text,face='white',size=10,style='-'):
    x,y=xy;ax.add_patch(Rectangle((x,y),w,hh,facecolor=face,edgecolor='#444444',lw=.8,ls=style))
    ax.text(x+w/2,y+hh/2,text,ha='center',va='center',fontsize=size)

def arrow(ax,a,b,label=None,offset=(0,0),style='->',color='#444444'):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle=style,mutation_scale=10,lw=.85,color=color))
    if label:ax.text((a[0]+b[0])/2+offset[0],(a[1]+b[1])/2+offset[1],label,ha='center',va='center',fontsize=9,bbox={'fc':'white','ec':'none','pad':1})

# 1. 微网物理结构；上下箭头分别显示充放电方向。
fig,ax=plt.subplots(figsize=(6.8,2.65));ax.set(xlim=(0,10),ylim=(0,4.4));ax.axis('off')
box(ax,(.25,2.55),2,1,'外部电网\n常规 / 紧急购电','#F7E2CD')
box(ax,(.25,.55),2,1,'光伏发电\n实际出力','#E8F1D8')
box(ax,(4.15,1.75),1.6,1,'交流母线','#EFF3F8')
box(ax,(7.8,2.55),1.9,1,'小区负载\n功率需求')
box(ax,(7.8,.55),1.9,1,'储能电池\n1200–10800 kWh','#E8F1D8')
arrow(ax,(2.25,3.05),(4.15,2.45));arrow(ax,(2.25,1.05),(4.15,2.05))
arrow(ax,(5.75,2.45),(7.8,3.05));arrow(ax,(5.75,2.1),(7.8,1.25),'入库 × 0.9',(0,.18))
arrow(ax,(7.8,.72),(5.45,1.75),'耗库 ÷ 0.9',(0,-.15))
ax.text(4.9,.47,'盈余供给可弃置；不设售电',ha='center',fontsize=9)
ax.text(4.9,3.85,'功率平衡在母线侧计量，电量状态在电池内部递推',ha='center',fontsize=10)
save(fig,'energy_network','Equipment parameters and balance/SOC equations; conceptual diagram, not measured data')

# 2. 分层流程借鉴范文的浅色分组与细线边框。
fig,ax=plt.subplots(figsize=(6.8,3.3));ax.set(xlim=(0,13.4),ylim=(0,6));ax.axis('off')
groups=[(.1,2.25,'信息输入','#FBF5E9'),(2.9,2.25,'基础模型','#F7E2CD'),(5.7,3.4,'分问决策','#EDF4E3'),(9.65,3.55,'执行与评价','#EFF3F8')]
for x,w,title,c in groups:
    box(ax,(x,.45),w,5.25,'',c,style='--');ax.text(x+w/2,5.38,title,ha='center',fontsize=10)
for y,t in [(3.9,'历史负荷\n历史光伏'),(2.65,'当前实际\n储电量'),(1.4,'已知电价\n已发布预报')]:box(ax,(.28,y),1.9,.85,t,size=8.7)
for y,t in [(3.9,'功率平衡'),(2.65,'储能动态'),(1.4,'容量与\n功率边界')]:box(ax,(3.08,y),1.9,.85,t,size=9)
for y,t in [(4.05,'问题1：确定性LP'),(2.85,'问题2：历史场景日前'),(1.65,'问题3：日内滚动调整'),(.65,'问题4：替换价格信息')]:box(ax,(5.9,y),3,.7,t,size=9)
box(ax,(9.9,3.65),3.05,1.1,'实际反馈执行\n补电、盈余与SOC',size=9)
box(ax,(9.9,1.75),3.05,1.1,'分项结算与结果核验\n图表、敏感性与对照',size=9)
arrow(ax,(2.35,3.1),(2.9,3.1));arrow(ax,(5.15,3.1),(5.7,3.1));arrow(ax,(9.1,3.1),(9.65,3.1))
arrow(ax,(11.42,3.65),(11.42,2.85));ax.text(11.42,1.05,'实际SOC传递至下一日',ha='center',fontsize=9)
save(fig,'study_flow','Four-problem modeling architecture and information boundary')

# 3. 单日调度，真实阶梯功率；图中阴影仅代表低价时段。
fig,ax=plt.subplots(3,1,figsize=(6.8,5.7),sharex=True,layout='constrained')
ax[0].plot(h,Q['load']/1000,color=BLUE,label='负载');ax[0].plot(h,Q['pv']/1000,color=GREEN,label='光伏')
ax[0].step(h,Q['grid']/1000,where='post',color=ORANGE,label='常规购电');ax[0].set_ylabel('功率 / MW');ax[0].legend(ncol=3,loc='upper center')
sub(ax[0],'(a) 供需与购电')
ax[1].step(h,Q['ch']/1000,where='post',color=BLUE,label='充电');ax[1].step(h,-Q['dis']/1000,where='post',color=ORANGE,label='放电（负向）')
ax[1].axhline(0,color=GRAY,lw=.65);ax[1].set_ylabel('功率 / MW');ax[1].legend(ncol=2,loc='upper center');sub(ax[1],'(b) 充放电切换')
ax[2].plot(edges,np.r_[6000,Q['energy']]/1000,color=BLUE,label='储电量');ax[2].axhline(1.2,color=GRAY,ls='--',lw=.8);ax[2].axhline(10.8,color=GRAY,ls='--',lw=.8)
ax[2].set_ylabel('储电量 / MWh');rt=ax[2].twinx();rt.step(h,Q['price'],color=ORANGE,where='post',ls='--',lw=1,label='电价');rt.set_ylabel('电价 / (元/kWh)')
ax[2].legend(loc='upper left');rt.legend(loc='upper right');sub(ax[2],'(c) 库存与价格');ax[2].set(xlim=(0,24),xticks=np.arange(0,25,4),xlabel='时刻 / h')
for aa in ax:axes_style(aa)
save(fig,'q1_dispatch','q1.npz: 144 period bus-side power, 145 SOC boundaries')

# 4. 输入样本结构，均值曲线不作为零时已知输入。
fig,ax=plt.subplots(1,2,figsize=(6.8,2.65),layout='constrained')
for j,m in enumerate((3,6,9,12)):
    mask=months==m
    ax[0].plot(h,I['load'][mask].mean(axis=0)/1000,color=colors[j],ls=['-','--','-.',':'][j],label=f'{m}月')
    ax[1].plot(h,I['pv'][mask].mean(axis=0)/1000,color=colors[j],ls=['-','--','-.',':'][j],label=f'{m}月')
for aa,t in zip(ax,('(a) 负荷月内平均曲线','(b) 光伏月内平均曲线')):
    axes_style(aa);sub(aa,t);aa.set(xlim=(0,24),xticks=np.arange(0,25,6),xlabel='时刻 / h',ylabel='平均功率 / MW');aa.legend(ncol=2,fontsize=8)
save(fig,'input_profiles','inputs_processed.npz: ex-post monthly mean power; descriptive only')

# 5. 日前预测误差分布，不构造虚假的误差带。
fig,ax=plt.subplots(1,2,figsize=(6.8,2.65),layout='constrained')
for aa,key,label,c in zip(ax,('load','pv'),('负荷','光伏'),(BLUE,ORANGE)):
    err=(I['forecast_'+key][start:]-I[key][start:]).ravel()/1000
    aa.hist(err,bins=55,color=c,alpha=.65,edgecolor='white',linewidth=.3,weights=np.ones(len(err))*100/len(err))
    aa.axvline(0,color=GRAY,lw=.85,ls='--');axes_style(aa);aa.set(xlabel='预测 − 实际 / MW',ylabel='时段比例 / %');sub(aa,f'{label}日前预测误差')
    mae=np.mean(abs(err))*1000;rmse=np.sqrt(np.mean(err**2))*1000
    aa.text(.97,.96,f'MAE = {mae:.1f} kW\nRMSE = {rmse:.1f} kW',ha='right',va='top',transform=aa.transAxes,fontsize=8.5,bbox={'fc':'white','ec':'.8','pad':3})
    metrics[key+'_forecast']={'n':len(err),'mae_kw':mae,'rmse_kw':rmse,'mean_error_kw':float(err.mean()*1000)}
save(fig,'forecast_errors','inputs_processed.npz: all 48096 holdout periods, prediction minus actual; histogram percentages')

# 6. 发布时间/执行窗口示意，灰色条为已执行或未采用的时域。
fig,ax=plt.subplots(figsize=(6.8,2.4),layout='constrained')
for j,k in enumerate((0,6,12,18)):
    y=3-j;ax.barh(y,24-k,left=k,height=.5,color=colors[j],alpha=.23,edgecolor=colors[j]);ax.barh(y,6,left=k,height=.5,color=colors[j],alpha=.9)
    ax.plot(k,y,'|',color='black',markersize=14);ax.text(k+3,y,'本轮执行',ha='center',va='center',fontsize=8,color='white' if j in (0,3) else 'black')
ax.set(yticks=[3,2,1,0],yticklabels=['0时发布','6时发布','12时发布','18时发布'],xlim=(0,24),xticks=np.arange(0,25,6),xlabel='当日时刻 / h')
axes_style(ax);ax.set_title('深色：执行到下一更新；浅色：当日剩余优化范围',fontsize=9)
save(fig,'information_timeline','Rolling algorithm: schematic publication time and action horizon, not result intervals')

# 7. 连续三日实际状态，不将日初重置为6000。
days=[list(dates).index(d) for d in ('2025-09-22','2025-09-23','2025-09-24')]
e=np.r_[A['q2']['energy'][days[0],0],A['q2']['energy'][days,1:].ravel()]/1000
fig,ax=plt.subplots(figsize=(6.8,2.5),layout='constrained');ax.plot(np.arange(len(e))/6,e,color=BLUE,lw=1.2)
for x in (24,48):ax.axvline(x,color=GRAY,ls='--',lw=.85);ax.plot(x,e[int(x*6)],'o',color=ORANGE,ms=4)
ax.axhline(1.2,color=RED,ls=':',lw=.85);ax.axhline(10.8,color=RED,ls=':',lw=.85)
ax.set(xlim=(0,72),ylim=(.65,11.35),xticks=np.arange(0,73,12),xticklabels=['9/22\n0时','12时','9/23\n0时','12时','9/24\n0时','12时','9/25\n0时'],ylabel='实际储电量 / MWh')
axes_style(ax);save(fig,'soc_continuity','q2.npz: actual SOC, 2025-09-22 00:00 to 2025-09-25 00:00')

# 8. 紧急电量按日、时段分布；同一色标，不截断最大值。
fig,ax=plt.subplots(1,2,figsize=(6.8,3.4),sharey=True,layout='constrained')
vmax=max(A[k]['emergency'][start:].max()*DT for k in ('q2','q3'))
for aa,k,t in zip(ax,('q2','q3'),('(a) 问题2','(b) 问题3')):
    vals=A[k]['emergency'][start:]*DT
    im=aa.imshow(vals,origin='upper',aspect='auto',extent=(0,24,334,0),cmap='YlOrRd',vmin=0,vmax=vmax,interpolation='nearest')
    aa.set(xticks=np.arange(0,25,6),xlabel='时刻 / h');sub(aa,t)
    ticks=[list(dates[start:]).index(f'2025-{m:02}-01') for m in (2,4,6,8,10,12)]
    aa.set_yticks(ticks,[f'{m}月1日' for m in (2,4,6,8,10,12)])
fig.colorbar(im,ax=ax,label='每10分钟紧急电量 / kWh',shrink=.92)
save(fig,'emergency_heatmap','q2/q3.npz: bus-side emergency power times 1/6 h; all report dates and shared linear scale')

# 9. 月度电量、费用分别显示。
fig,ax=plt.subplots(2,1,figsize=(6.8,3.8),sharex=True,layout='constrained')
for k,c,marker in (('q2',BLUE,'o'),('q3',ORANGE,'s')):
    em=[A[k]['emergency'][months==m].sum()*DT/1000 for m in ms];cost=[A[k]['costs'][months==m,4].sum()/10000 for m in ms]
    ax[0].plot(ms,em,marker+'-',color=c,label='问题2' if k=='q2' else '问题3',ms=4);ax[1].plot(ms,cost,marker+'-',color=c,ms=4)
ax[0].set_ylabel('紧急电量 / MWh');ax[0].legend(ncol=2);sub(ax[0],'(a) 紧急购电量')
ax[1].set(ylabel='总费用 / 万元',xlabel='月份',xticks=ms);sub(ax[1],'(b) 实际结算费用')
for aa in ax:axes_style(aa)
save(fig,'monthly_comparison','q2/q3.npz: sum by calendar month, February to December')

# 10. 分段结算曲线，由论文公式直接计算。
x=np.linspace(0,9,181);cb=np.minimum(x,5)+.5*np.maximum(5-x,0)+1.5*np.maximum(x-5,0);ca=5+.5*np.maximum(5-x,0)+1.5*np.maximum(x-5,0)
fig,ax=plt.subplots(figsize=(6.8,2.65),layout='constrained');ax.plot(x,cb,color=BLUE,label='主口径：取消量仅付50%');ax.plot(x,ca,'--',color=ORANGE,label='对照：原费不退、另收50%')
for y,c,txt in ((4.5,BLUE,'(4, 4.5)'),(5.5,ORANGE,'(4, 5.5)')):ax.plot(4,y,'o',ms=4,color=c);ax.annotate(txt,(4,y),xytext=(2.0,y+(.6 if y>5 else -.7)),arrowprops={'arrowstyle':'-','color':c,'lw':.7},fontsize=9)
ax.plot(5,5,'ks',ms=4);ax.set(xlim=(0,9),ylim=(0,12),xlabel='正式调整后的常规电量 / kWh',ylabel='常规交易费用 / 元');axes_style(ax);ax.legend(loc='upper left',fontsize=9)
save(fig,'settlement_curve','Piecewise contract equations: original plan 5 kWh, price 1 yuan/kWh; emergency excluded')

# 11. 经济门控流程。图内概念对应公式，不借用迭代收敛曲线。
fig,ax=plt.subplots(figsize=(6.8,2.8));ax.set(xlim=(0,13),ylim=(0,5));ax.axis('off')
box(ax,(.1,2.05),2.3,1.15,'最新预报\n当前实际SOC','#EFF3F8',9)
box(ax,(3.0,3.15),2.5,.95,'优化候选安排 g*','#F7E2CD',9)
box(ax,(3.0,1.05),2.5,.95,'保留原执行安排',size=9)
diamond=np.array([[7.3,3.6],[8.7,2.55],[7.3,1.5],[5.9,2.55]])
ax.add_patch(Polygon(diamond,fc='#EDF4E3',ec='#444444',lw=.8));ax.text(7.3,2.55,'同场景评分\n预计节省\n大于容差？',ha='center',va='center',fontsize=8.5)
box(ax,(10,3.15),2.5,.95,'采纳候选','#EDF4E3',9);box(ax,(10,1.05),2.5,.95,'继续现行安排',size=9)
arrow(ax,(2.4,2.85),(3,3.62));arrow(ax,(2.4,2.35),(3,1.52));arrow(ax,(5.5,3.62),(6.35,2.9));arrow(ax,(5.5,1.52),(6.35,2.2));arrow(ax,(8.4,2.78),(10,3.62),'是');arrow(ax,(8.4,2.3),(10,1.52),'否')
ax.text(6.5,.3,'原始零时合同不改；评分已含调整费；仅更新未来执行段',ha='center',fontsize=10)
save(fig,'gate_flow','Same-information candidate gate defined in paper; no extra adjustment-fee subtraction')

# 12. 典型日计划、状态及操作区间，末层借鉴范文的时间区间图。
d=list(dates).index('2025-03-20');a=A['q3']
fig,ax=plt.subplots(3,1,figsize=(6.8,5.15),sharex=True,gridspec_kw={'height_ratios':[1.3,1.2,.55]},layout='constrained')
ax[0].step(h,a['plan'][d]/1000,where='post',color=GRAY,ls='--',label='零时计划');ax[0].step(h,a['grid'][d]/1000,where='post',color=BLUE,label='最终常规');ax[0].plot(h,a['emergency'][d]/1000,color=ORANGE,label='紧急')
ax[0].set_ylabel('购电功率 / MW');ax[0].legend(ncol=3,fontsize=8.5);sub(ax[0],'(a) 原计划与最终执行')
ax[1].plot(edges,a['energy'][d]/1000,color=BLUE);ax[1].set_ylabel('储电量 / MWh');sub(ax[1],'(b) 实际储能状态')
for row,key,c in ((2,'ch',BLUE),(1,'dis',ORANGE),(0,'emergency',RED)):
    ids=np.flatnonzero(a[key][d]>1e-7)
    ax[2].broken_barh([(v/6,DT) for v in ids],(row-.25,.5),facecolors=c,edgecolors='none')
ax[2].set(yticks=[0,1,2],yticklabels=['紧急','放电','充电'],xlabel='时刻 / h',xlim=(0,24),xticks=np.arange(0,25,6),ylim=(-.55,2.6));sub(ax[2],'(c) 实际操作区间')
for aa in ax:
    axes_style(aa)
    for xx in (6,12,18):aa.axvline(xx,color=GRAY,lw=.65,ls=':')
save(fig,'q3_typical','q3.npz: 2025-03-20; active intervals use bus-side power > 1e-7 kW')

# 13. 月度差异与逐日累计；不把累积曲线称为迭代收敛。
delta=A['q3_daily']['costs'][start:,4]-A['q3']['costs'][start:,4]
monthly=np.array([delta[months[start:]==m].sum() for m in ms])
assert np.allclose(monthly,[D['update_cost_by_month'][str(m)] for m in ms])
fig,ax=plt.subplots(1,2,figsize=(6.8,2.6),layout='constrained')
ax[0].bar(ms,monthly/1e4,color=BLUE,width=.65,edgecolor='#333333',lw=.35);ax[0].set(xticks=ms,xlabel='月份',ylabel='月度节省 / 万元');sub(ax[0],'(a) 11个月均有净节省')
ax[1].plot(np.arange(1,335),np.cumsum(delta)/1e4,color=BLUE);ax[1].axhline(0,color=GRAY,lw=.65);ax[1].set(xlabel='报告期累计天数',ylabel='累计节省 / 万元');sub(ax[1],'(b) 逐日累计实际费用差')
for aa in ax:axes_style(aa)
metrics['daily_update_saving']={'total_yuan':float(delta.sum()),'min_yuan':float(delta.min()),'max_yuan':float(delta.max()),'more_expensive_days':int((delta<-1e-6).sum())}
save(fig,'update_robustness','q3_daily minus q3 actual daily fees; monthly sums and sequential cumulative sum')

# 14. 电价信息对照。
d=list(dates).index('2025-06-21');fig,ax=plt.subplots(2,1,figsize=(6.8,3.8),sharex=True,layout='constrained')
for arr,c,ls,l in ((I['price'][d],ORANGE,'-','实际波动价'),(I['forecast_price'][d],BLUE,'--','日前预测价'),(Q['price'],GRAY,':','重复日内价')):ax[0].plot(h,arr,color=c,ls=ls,label=l)
ax[0].set_ylabel('电价 / (元/kWh)');ax[0].legend(ncol=3,fontsize=8.5);sub(ax[0],'(a) 价格输入与实际结算价')
for k,c,ls,l in (('q4_3',BLUE,'-','未来价格未知'),('q4_3_known',ORANGE,'--','当天价格已知')):ax[1].plot(edges,A[k]['energy'][d]/1000,color=c,ls=ls,label=l)
ax[1].set(ylabel='储电量 / MWh',xlabel='时刻 / h',xticks=np.arange(0,25,4),xlim=(0,24));ax[1].legend(ncol=2,fontsize=9);sub(ax[1],'(b) 相应的实际储能轨迹')
for aa in ax:axes_style(aa)
save(fig,'q4_price','inputs_processed, q4_3 and q4_3_known; 2025-06-21')

# 15. 所有分项非负；低比例分项通过右图单独展开。
kk=['q2','q3','q4_2','q4_3'];xx=np.arange(4);labels=['问题2','问题3','问题4-2','问题4-3']
components=[('履行原计划',BLUE,lambda a:a['plan_cost']+2*a['down_cost']),('取消违约',YELLOW,lambda a:-a['down_cost']),('上调购电',ORANGE,lambda a:a['up_cost']),('紧急购电',PURPLE,lambda a:a['emergency_cost'])]
fig,ax=plt.subplots(1,2,figsize=(6.8,2.9),layout='constrained');bottom=np.zeros(4);small=np.zeros(4)
for idx,(label,c,fun) in enumerate(components):
    vals=np.array([fun(S['cases'][k])/1e4 for k in kk]);ax[0].bar(xx,vals,bottom=bottom,label=label,color=c,edgecolor='white',linewidth=.25);bottom+=vals
    if idx:ax[1].bar(xx,vals,bottom=small,color=c,label=label,edgecolor='white',linewidth=.25);small+=vals
assert np.allclose(bottom,[S['cases'][k]['total_cost']/1e4 for k in kk])
for i,v in enumerate(bottom):ax[0].text(i,v+14,f'{v:.1f}',ha='center',fontsize=8)
for aa in ax:axes_style(aa);aa.set_xticks(xx,labels,rotation=15);aa.set_ylabel('费用 / 万元')
ax[0].set_ylim(0,max(bottom)*1.38);ax[0].legend(ncol=2,fontsize=7.5,loc='upper left');sub(ax[0],'(a) 全部实际费用');sub(ax[1],'(b) 偏差与紧急费用展开')
save(fig,'annual_costs','summary.json: four nonnegative settlement components, right panel expands three smaller components')

# 16. 参数选择与事后敏感性分栏，以免信息混淆。
fig,ax=plt.subplots(1,2,figsize=(6.8,2.7),layout='constrained')
windows=[7,14,28];cost=[S['cases'][k]['total_cost']/1e4 for k in ('q3_history7','q3','q3_history28')]
ax[0].plot(windows,cost,'o-',color=BLUE,ms=5);ax[0].plot(14,cost[1],'s',mfc='white',mec=ORANGE,ms=8,label='主模型：14天');ax[0].set(xticks=windows,xlabel='误差窗口 / 天',ylabel='报告期总费用 / 万元');ax[0].legend(loc='upper left',fontsize=8);sub(ax[0],'(a) 事后窗口敏感性')
for k,c,l in (('q2',BLUE,'重复电价'),('q4_2',ORANGE,'波动电价')):
    score=RF['validation'][k+'_terminal']['scores'];gammas=np.array([0,.5,1,1.5]);yy=np.array([score[str(g)]['adjusted_cost'] for g in gammas]);yy=(yy-yy[0])/10000
    ax[1].plot(gammas,yy,'o-' if k=='q2' else 's--',color=c,label=l,ms=4)
ax[1].axhline(0,color=GRAY,lw=.6);ax[1].set(xticks=[0,.5,1,1.5],xlabel='终端价值强度 γ',ylabel='相对 γ=0 的验证费用差 / 万元');ax[1].legend(fontsize=8);sub(ax[1],'(b) 仅1月份的参数选型')
for aa in ax:axes_style(aa)
save(fig,'parameter_sensitivity','summary.json holdout window costs; refinements.json January inventory-adjusted terminal validation scores')

# 17. 独立扩展相对各自基准，保留不改善项与负面结果。
rows=[('终端价值','q2','q4_2','terminal'),('调整门控','q3','q4_3','gate'),('预报融合','q3','q4_3','blend'),('费用选型','q2','q4_2','economic')]
fig,ax=plt.subplots(figsize=(6.8,2.75),layout='constrained');ys=np.arange(4)
for offset,c,which,l in ((-.15,BLUE,0,'重复电价'),(.15,ORANGE,1,'波动电价')):
    vals=[]
    for title,b1,b2,suffix in rows:
        base=(b1,b2)[which];alt=base+'_'+suffix;allcases={**S['cases'],**RF['cases']}
        if suffix=='economic':base=base+'_mae_control'
        vals.append((allcases[base]['total_cost']-allcases[alt]['total_cost'])/10000)
    ax.barh(ys+offset,vals,height=.28,color=c,label=l,edgecolor='white',lw=.25)
    for y,v in zip(ys+offset,vals):ax.text(v+(.15 if v>=0 else -.15),y,f'{v:.2f}',ha='left' if v>=0 else 'right',va='center',fontsize=8)
ax.axvline(0,color=GRAY,lw=.8);ax.set(yticks=ys,yticklabels=[r[0] for r in rows],xlabel='相对各自基准节省的费用 / 万元',xlim=(-2.2,23));ax.invert_yaxis();axes_style(ax);ax.legend(loc='lower right',fontsize=9)
save(fig,'strategy_gains','Each independent refinement against its own stated baseline; economic selection versus dedicated MAE control; gains cannot be added')

# 18. 分时预报误差，已发布预报比较在相同目标区间内进行。
fig,ax=plt.subplots(figsize=(6.8,2.5),layout='constrained');xx=np.arange(4)
for j,(field,c,l) in enumerate((('historical_same_block',GRAY,'历史预测'),('zero_same_block',BLUE,'零时发布'),('six_hour',ORANGE,'本次发布'))):
    yy=[D['issued_pv'][str(k)][field]['mae'] for k in (0,6,12,18)];ax.bar(xx+(j-1)*.24,yy,width=.22,color=c,label=l,edgecolor='white',lw=.3)
ax.set(xticks=xx,xticklabels=['0–6时','6–12时','12–18时','18–24时'],xlabel='共同目标时段',ylabel='光伏预测 MAE / kW');axes_style(ax);ax.legend(ncol=3,fontsize=9)
save(fig,'forecast_updates','diagnostics.json issued_pv: historical/zero/current publication compared over identical target six-hour blocks')

metrics['trace_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(R.glob('*.npz'))}
(R/'figure_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
print('Generated',len(metrics['figures']),'verified figure groups.')
