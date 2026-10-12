"""编辑层处理：分析表标题及描述统计；不更改优化模型或原始结果。"""
from pathlib import Path
import json,re,statistics

ROOT=Path(__file__).resolve().parents[1]
CAPTIONS={
    'risk_compare':'计入缺额风险后，常规购电增加而总费用下降（本算例）',
    'information_benchmark':'先知参照费用更低，比较仍须区分信息与库存边界（费用/元，电量/kWh）',
    'terminal_validation':'1月验证未支持重复电价下的正终端奖励（库存修正费用/元）',
    'terminal_results':'所选终端价值仅在波动电价日前方案中降低报告期费用',
    'gate_results':'计费后筛选调整小幅节省总费，紧急电量略增（采纳、保留以次计）',
    'frequency':'相同零时预报下，四次更新的报告期费用最低',
    'issued_forecast':'6时与12时更新改善对应白天时段的预报误差（误差单位：kW）',
    'update_robustness':'11个月均节省费用，5月的紧急电量仍有增加',
    'price_information':'提前获知价格降低回测费用，并增加储能循环强度',
    'annual':'本样本中，波动电价下两套主方案的费用均高于重复电价基准',
    'scenario_diagnostic':'打乱时间配对未改变LP代理目标，却改变了反馈费用',
    'feedback_benchmark':'本算例的36时段保留规则增加了紧急购电与总费',
    'settlement':'是否退回取消电量原费，会改变下调行为及总费',
    'window':'7天窗口回测费用较低，尚不能据此认定全年最优窗口',
    'blend_results':'预报融合降低了总费，但紧急电量并未同步下降',
    'economic_validation':'1月库存修正费用选型偏好3日均值，误差选型偏好7日均值',
    'economic_results':'相同历史回放下，费用选型未优于MAE选型（2--12月）',
}

def main():
    for stem,title in CAPTIONS.items():
        p=ROOT/'tables'/(stem+'.tex');s=p.read_text(encoding='utf-8')
        s,n=re.subn(r'\\caption\{[^{}]*\}',lambda _:r'\caption{'+title+'}',s,count=1)
        assert n==1,stem
        p.write_text(s,encoding='utf-8')
    d=json.loads((ROOT/'results/diagnostics.json').read_text(encoding='utf-8'))
    months=d['update_cost_by_month']
    values=[float(months[str(m)]) for m in range(2,13)]
    stats={'source':'results/diagnostics.json:update_cost_by_month',
           'definition':'monthly cost: q3_daily minus q3, yuan',
           'n':len(values),'ddof':1,'values_yuan':values,
           'mean_yuan':statistics.mean(values),'sd_yuan':statistics.stdev(values),
           'min_yuan':min(values),'max_yuan':max(values),
           'interpretation':'descriptive month-to-month spread; not a confidence or prediction interval'}
    assert all(x>0 for x in values) and len(values)==11
    (ROOT/'results/editorial_statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=json.loads((ROOT/'results/summary.json').read_text(encoding='utf-8'))['cases']
    groups={}
    for key in ('q2','q3','q4_2','q4_3'):
        groups[key+'_cost_wan']=summary[key]['total_cost']/10000
    groups.update(monthly_mean_wan=stats['mean_yuan']/10000,monthly_sd_wan=stats['sd_yuan']/10000,
                  monthly_min_wan=stats['min_yuan']/10000,monthly_max_wan=stats['max_yuan']/10000)
    lines=['% Presentation precision and descriptive statistics; source arrays are unchanged.']
    for k,v in groups.items():
        lines.append('\\expandafter\\def\\csname resulteditorial'+k+'\\endcsname{'+f'{v:.2f}'+'}')
    (ROOT/'tables/editorial_metrics.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
