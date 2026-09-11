"""运行全部模型与对照实验。输入原始附件目录，输出可核验的NPZ与JSON。"""
import argparse,json,sys,platform
from pathlib import Path
from time import perf_counter
import numpy as np
import scipy
from model import load_data,forecast_all,optimize,run_case,summarize,DT,EINIT

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'results')
    parser.add_argument('--cases',nargs='*')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    start=perf_counter()
    data=load_data(args.data)
    forecast,scores,selected=forecast_all(data)
    np.savez_compressed(args.out/'inputs_processed.npz',**{k:v for k,v in data.items() if k!='dates'},**{'forecast_'+k:v for k,v in forecast.items()})
    metadata={'dates':data['dates'],'selected_forecasts':selected,'january_validation':scores,'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__}
    metadata['forecast_feb_dec']={}
    for key in ('load','pv','price'):
        diff=forecast[key][31:]-data[key][31:]
        metadata['forecast_feb_dec'][key]={'mae':float(abs(diff).mean()),'rmse':float(np.sqrt((diff**2).mean())),'wape':float(abs(diff).sum()/data[key][31:].sum())}
    solution=optimize((data['one'][:,1]-data['one'][:,2])[None,:],data['one'][:,0],EINIT,cyclic=True)
    np.savez_compressed(args.out/'q1.npz',**solution,price=data['one'][:,0],load=data['one'][:,1],pv=data['one'][:,2])
    metadata['q1']={k:float(v) for k,v in solution.items() if np.isscalar(v)}
    metadata['q1'].update(grid_kwh=float(solution['grid'].sum()*DT),ch_kwh=float(solution['ch'].sum()*DT),dis_kwh=float(solution['dis'].sum()*DT),end_energy=float(solution['energy'][-1]),net_cost=float(np.maximum(data['one'][:,1]-data['one'][:,2],0)@data['one'][:,0]*DT))
    configs={
      'q2':{},
      'q2_nominal':{'history_days':0},
      'q3':{'kind':3},
      'q3_daily':{'kind':3,'updates':(0,)},
      'q3_noon':{'kind':3,'updates':(0,12)},
      # 预报时刻消融：固定0时基准，逐一识别6、12、18时的独立及组合贡献。
      'q3_06':{'kind':3,'updates':(0,6)},
      'q3_018':{'kind':3,'updates':(0,18)},
      'q3_0612':{'kind':3,'updates':(0,6,12)},
      'q3_01218':{'kind':3,'updates':(0,12,18)},
      'q3_0618':{'kind':3,'updates':(0,6,18)},
      'q3_refund':{'kind':3,'settlement':'refund'},
      'q4_2':{'price_mode':'forecast'},
      'q4_3':{'kind':3,'price_mode':'forecast'},
      'q4_2_known':{'price_mode':'known'},
      'q4_3_known':{'kind':3,'price_mode':'known'},
      'q4_3_refund':{'kind':3,'price_mode':'forecast','settlement':'refund'},
      'q3_history7':{'kind':3,'history_days':7},
      'q3_history28':{'kind':3,'history_days':28},
    }
    summaries={}
    existing=args.out/'summary.json'
    if existing.exists():
        summaries=json.loads(existing.read_text(encoding='utf-8')).get('cases',{})
    for name,config in configs.items():
        if args.cases and name not in args.cases:
            continue
        arrays,info=run_case(data,forecast,**config)
        np.savez_compressed(args.out/(name+'.npz'),**arrays)
        summaries[name]=summarize(arrays,info)
        print(name,json.dumps(summaries[name],ensure_ascii=False),flush=True)
        metadata['cases']=summaries
        metadata['experiment_seconds']=perf_counter()-start
        existing.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Completed',selected,flush=True)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
