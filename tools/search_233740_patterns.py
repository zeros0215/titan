"""Post-hoc one-day pattern research, using only past bars at each fill."""
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path

SOURCE = Path('output/paper_grid/replay_20260907')
OUT = SOURCE / 'pattern_search'


def entries(bars, family, volume_ratio):
    found = {}
    for i in range(3, len(bars)):
        b, p = bars[i], bars[i-1]
        bullish = b['close'] > b['open']
        if family == 'rebound_break':
            hit = bullish and b['close'] > p['high'] and any(
                bars[j]['close'] < bars[j-1]['close'] for j in range(i-2, i))
        elif family == 'higher_low':
            hit = bullish and b['low'] > p['low'] and b['close'] > p['close'] and (
                p['low'] <= min(x['low'] for x in bars[i-3:i]))
        else:
            n = int(family.split('_')[-1])
            if i < n:
                continue
            avg = sum(x['close'] for x in bars[i-n+1:i+1])/n
            prior = sum(x['close'] for x in bars[i-n:i])/n
            hit = bullish and b['close'] > avg and p['close'] <= prior
        mean_volume = sum(x['volume'] for x in bars[i-3:i])/3
        if hit and (not volume_ratio or b['volume'] >= mean_volume*volume_ratio):
            found[i] = dict(signal_time=b['time'], close=b['close'],
                            prior_high=p['high'], low=b['low'], prior_low=p['low'],
                            volume_ratio=round(b['volume']/mean_volume, 3) if mean_volume else None)
    return found


def replay(bars, minutes, signals, stop, exit_kind, distance, slip=5, bar_minutes=5):
    orders = {bars[i+1]['time']+'00': s for i,s in signals.items() if i+1<len(bars)}
    endings = {b['time'][:2]+f"{int(b['time'][2:])+bar_minutes-1:02d}00":b for b in bars}
    trades, pos = [], None
    equity = peak = dd = 0.
    for m in minutes:
        t = m['time']
        if pos is None and t in orders and t < '152000':
            fill = math.ceil(m['open']/5)*5+slip
            pos = dict(entry_time=t, entry=fill, stop=fill-stop, initial_stop=fill-stop,
                       highest=fill, signal=orders[t])
        if pos:
            price = reason = None
            if m['low'] <= pos['stop']:
                price, reason = min(m['open'], pos['stop']), 'STOP_OR_TRAIL'
            elif exit_kind == 'fixed' and m['high'] >= pos['entry']+distance:
                price, reason = pos['entry']+distance, 'TARGET'
            elif t == '153000':
                price, reason = m['close'], 'CLOSE'
            if reason:
                fill = math.floor(price/5)*5-slip
                net = (fill-pos['entry'])*100-(fill+pos['entry'])*100*.00015
                trades.append(dict(**pos, exit_time=t, exit=fill, reason=reason, net=net))
                equity += net
                pos = None
            elif exit_kind == 'trailing' and t in endings:
                # Only completed signal-bar highs update the next minute's stop.
                pos['highest'] = max(pos['highest'], endings[t]['high'])
                if pos['highest'] >= pos['entry']+40:
                    pos['stop'] = max(pos['stop'], math.floor((pos['highest']-distance)/5)*5)
        marked = equity if pos is None else equity+(m['close']-pos['entry'])*100-(m['close']+pos['entry'])*100*.00015
        peak = max(peak, marked)
        dd = max(dd, peak-marked)
    assert pos is None
    return dict(net=round(equity, 3), drawdown=round(dd, 3), count=len(trades),
                wins=sum(t['net']>0 for t in trades), trades=trades)


def main():
    OUT.mkdir(exist_ok=True)
    minutes = json.loads((SOURCE/'today_minutes.json').read_text())
    bars = json.loads((SOURCE/'five_minutes.json').read_text())
    for b in bars:
        b['volume'] = sum(m['volume'] for m in minutes if b['time']+'00' <= m['time'] <= b['time'][:2]+f"{int(b['time'][2:])+4:02d}00")
    trials=[]
    families=('rebound_break','higher_low','ma_3','ma_5','ma_10')
    for family, ratio in itertools.product(families,(0,1,1.3)):
        signals = entries(bars, family, ratio)
        for n in range(1,len(bars)+1):
            assert entries(bars[:n],family,ratio)=={i:s for i,s in signals.items() if i<n}
        for stop, kind, distance in itertools.product((30,50,80),('fixed','trailing'),(30,50,80,130)):
            params=dict(family=family,volume_ratio=ratio,stop=stop,exit_kind=kind,distance=distance)
            result=replay(bars,minutes,signals,stop,kind,distance)
            trials.append(dict(params=params,result=result))
    ranked=sorted(trials,key=lambda x:(x['result']['net'],-x['result']['drawdown']),reverse=True)
    best=ranked[0]
    best_trailing=next(r for r in ranked if r['params']['exit_kind']=='trailing')
    p=best['params']
    signals=entries(bars,p['family'],p['volume_ratio'])
    stress={str(s):replay(bars,minutes,signals,p['stop'],p['exit_kind'],p['distance'],s) for s in (0,5,10)}
    family_best={f:next(r for r in ranked if r['params']['family']==f) for f in families}
    # Descriptive forward return for ALL signals, including failed signals, not a filter.
    signal_audit=[]
    for i,s in signals.items():
        if i+1>=len(bars):
            continue
        future=bars[i+1:min(i+7,len(bars))]
        opening=bars[i+1]['open']
        signal_audit.append(dict(**s,next_open=opening,forward_bars=len(future),
            next_30m_max_up=max(b['high'] for b in future)-opening,
            next_30m_max_down=min(b['low'] for b in future)-opening,
            next_30m_close_change=future[-1]['close']-opening))
    result=dict(status='POST_HOC_SINGLE_DAY_UNVERIFIED_DATA',trial_count=len(trials),
        positive=sum(t['result']['net']>0 for t in trials),best=best,best_trailing=best_trailing,family_best=family_best,
        stress=stress,signals=signal_audit,top20=ranked[:20],
        source_sha256=hashlib.sha256((SOURCE/'today_minutes.json').read_bytes()).hexdigest())
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
    with (OUT/'trials.csv').open('w',newline='',encoding='utf-8-sig') as h:
        fields=list(p)+['net','drawdown','count','wins']
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        for t in ranked:
            w.writerow(dict(**t['params'],**{k:t['result'][k] for k in fields if k not in p}))
    for trial in trials:
        r=trial['result']
        assert abs(sum(t['net'] for t in r['trades'])-r['net'])<.001
        for t in r['trades']:
            assert t['signal']['signal_time']+'00'<t['entry_time']<=t['exit_time']
            assert t['entry']%5==0 and t['exit']%5==0
    make_plot(bars,best['result']['trades'])
    print(json.dumps({k:v for k,v in result.items() if k not in ('top20','family_best')},indent=2))


def make_plot(bars,trades,output_path=None,title=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    def x(t):
        return (int(t[:2])*60+int(t[2:4])-540)/5
    fig,ax=plt.subplots(figsize=(13,5))
    for b in bars:
        col='#d64b42' if b['close']>=b['open'] else '#2580ca'
        k=x(b['time'])
        ax.plot([k,k],[b['low'],b['high']],color=col,linewidth=.8)
        ax.add_patch(Rectangle((k-.3,min(b['open'],b['close'])),.6,
                              max(abs(b['close']-b['open']),1),color=col))
    for j,t in enumerate(trades,1):
        ax.scatter(x(t['entry_time']),t['entry'],marker='^',c='green',s=70,zorder=5)
        ax.scatter(x(t['exit_time']),t['exit'],marker='v',c='black',s=70,zorder=5)
        ax.plot([x(t['entry_time']),x(t['exit_time'])],[t['entry'],t['exit']],
                color='green',linestyle='--',alpha=.7)
        ax.annotate(f'B{j}',(x(t['entry_time']),t['entry']),xytext=(0,-18),
                    textcoords='offset points',ha='center',color='green')
        ax.annotate(f'S{j}',(x(t['exit_time']),t['exit']),xytext=(0,10),
                    textcoords='offset points',ha='center')
    ax.set_xticks(list(range(0,79,6)),[f'{(540+k*5)//60:02d}:{(540+k*5)%60:02d}' for k in range(0,79,6)])
    ax.set_ylabel('KRW'); ax.grid(alpha=.2)
    ax.set_title(title or '233740 | 2026-09-07 | Post-hoc best of 360 variants | 100 shares per trade')
    fig.text(.5,.01,'UNVERIFIED VIRTUAL QUOTES — hypothetical fills, fees + adverse 5 KRW per side; source prices are not repaired.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1)); fig.savefig(output_path or OUT/'trades.png',dpi=160); plt.close(fig)


if __name__ == '__main__':
    main()
