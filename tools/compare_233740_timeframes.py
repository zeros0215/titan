"""Same-parameter comparison and separately labeled intraday timeframe search."""
import argparse
import csv
import itertools
import json
from tools.search_233740_patterns import SOURCE, entries, replay


def aggregate(minutes, interval):
    groups={}
    for m in minutes:
        if not '090000' <= m['time'] < '152000':
            continue
        elapsed=int(m['time'][:2])*60+int(m['time'][2:4])-540
        start=540+elapsed//interval*interval
        groups.setdefault(start,[]).append(m)
    bars=[]
    for start,rows in sorted(groups.items()):
        if start+interval>920:
            continue  # Exclude incomplete bar at the start of the closing auction.
        expected=[f'{t//60:02d}{t%60:02d}00' for t in range(start,start+interval)]
        assert [m['time'] for m in rows]==expected
        bars.append(dict(time=f'{start//60:02d}{start%60:02d}',open=rows[0]['open'],
            high=max(m['high'] for m in rows),low=min(m['low'] for m in rows),
            close=rows[-1]['close'],volume=sum(m['volume'] for m in rows)))
    return bars


def main(interval=1):
    label={1:'one',3:'three',5:'five'}[interval]
    out=SOURCE/f'{label}_minute_comparison'
    out.mkdir(exist_ok=True)
    minutes=json.loads((SOURCE/'today_minutes.json').read_text())
    bars=aggregate(minutes,interval)
    (out/'bars.json').write_text(json.dumps(bars,indent=2))
    original=json.loads((SOURCE/'pattern_search/results.json').read_text())['best']
    params=original['params']
    def run(p,slip=5):
        return replay(bars,minutes,entries(bars,p['family'],p['volume_ratio']),
                      p['stop'],p['exit_kind'],p['distance'],slip,bar_minutes=interval)
    same=run(params)
    trials=[]
    for family,ratio in itertools.product(('rebound_break','higher_low','ma_3','ma_5','ma_10'),(0,1,1.3)):
        signals=entries(bars,family,ratio)
        for n in range(1,len(bars)+1):
            assert entries(bars[:n],family,ratio)=={i:s for i,s in signals.items() if i<n}
        for stop,kind,distance in itertools.product((30,50,80),('fixed','trailing'),(30,50,80,130)):
            p=dict(family=family,volume_ratio=ratio,stop=stop,exit_kind=kind,distance=distance)
            r=replay(bars,minutes,signals,stop,kind,distance,bar_minutes=interval)
            assert abs(sum(t['net'] for t in r['trades'])-r['net'])<.001
            assert all(t['signal']['signal_time']+'00'<t['entry_time']<=t['exit_time'] for t in r['trades'])
            trials.append(dict(params=p,result=r))
    ranked=sorted(trials,key=lambda r:(r['result']['net'],-r['result']['drawdown']),reverse=True)
    best=ranked[0]
    report=dict(status='POST_HOC_UNVERIFIED_SOURCE',bar_count=len(bars),interval_minutes=interval,
                note=f'Same bar counts do not mean same clock horizon: 3 bars becomes {3*interval} minutes instead of 15. '
                     'Both use one-minute OHLC for exits; stop first on ambiguous same-minute touches. '
                     'Completed signal-bar stop updates apply only to the following minute. '
                     'No source repairs; adverse tick rounding and 5-won slippage each side, 100 shares, fees 0.015% each side, no taxes.',
                five_minute=original,one_minute_same_params=dict(params=params,result=same),
                same_params_signal_count=len(entries(bars,params['family'],params['volume_ratio'])),
                trial_count=len(trials),positive_count=sum(r['result']['net']>0 for r in trials),
                best_one_minute=best,
                stress_same_params={str(s):run(params,s) for s in (0,5,10)},
                stress_one_minute_best={str(s):run(best['params'],s) for s in (0,5,10)},
                top10=ranked[:10])
    if interval!=1:
        for key in ('one_minute_same_params','best_one_minute','stress_one_minute_best'):
            report[key.replace('one_minute',f'{label}_minute')]=report.pop(key)
    (out/'results.json').write_text(json.dumps(report,indent=2))
    with (out/'trials.csv').open('w',newline='',encoding='utf-8-sig') as h:
        w=csv.writer(h); w.writerow(['family','volume_ratio','stop','exit','distance','net','count','wins','drawdown'])
        for r in ranked:
            p,v=r['params'],r['result']
            w.writerow([p['family'],p['volume_ratio'],p['stop'],p['exit_kind'],p['distance'],v['net'],v['count'],v['wins'],v['drawdown']])
    print(json.dumps(dict(interval=interval,bars=len(bars),same_params=same,
        signals=report['same_params_signal_count'],best=best,positive=report['positive_count'],
        stress={s:v['net'] for s,v in report[f'stress_{label}_minute_best'].items()}),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--minutes',type=int,choices=(1,3,5),default=1)
    main(parser.parse_args().minutes)
