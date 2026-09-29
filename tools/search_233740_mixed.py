"""Explicitly retrospective search over single and mixed timeframes."""
import bisect
import csv
import hashlib
import itertools
import json
from tools.compare_233740_timeframes import aggregate
from tools.search_233740_patterns import SOURCE, entries, replay

OUT=SOURCE/'mixed_timeframe_search'


def clock_minute(t):
    return int(t[:2])*60+int(t[2:4])


def direction(bars, interval, at, mode):
    """Only bars whose closing boundary has been reached are observable."""
    ends=[clock_minute(b['time'])+interval for b in bars]
    k=bisect.bisect_right(ends,at)-1
    if k<1:
        return False
    if mode=='rising_close':
        return bars[k]['close']>bars[k-1]['close']
    n=int(mode[-1])
    if k<n:
        return False
    avg=sum(b['close'] for b in bars[k-n+1:k+1])/n
    prev=sum(b['close'] for b in bars[k-n:k])/n
    return bars[k]['close']>avg and avg>prev


def schedule(allbars, tf, family, ratio, filters, mode):
    source=allbars[tf]
    result={}
    for i,s in entries(source,family,ratio).items():
        # Match earlier comparison's last-bar exclusion.
        if i+1>=len(source):
            continue
        at=clock_minute(source[i]['time'])+tf
        if all(direction(allbars[f],f,at,mode) for f in filters):
            # Engine indexes one-minute bars; signal is known at this boundary.
            result[at-540-1]=dict(**s,entry_tf=tf,known_at=f'{at//60:02d}{at%60:02d}',
                                 filter_timeframes=filters,filter_mode=mode)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    minutes=json.loads((SOURCE/'today_minutes.json').read_text())
    allbars={tf:aggregate(minutes,tf) for tf in (1,3,5)}
    rows=[]
    best=None
    group_best={}
    for tf,family,ratio in itertools.product((1,3,5),
            ('rebound_break','higher_low','ma_3','ma_5','ma_10'),(0,1,1.3)):
        others=[f for f in (1,3,5) if f!=tf]
        filters=[([], 'none')]+[(fs,mode) for fs in ([others[0]],[others[1]],others)
                               for mode in ('rising_close','ma3','ma5')]
        for fs,mode in filters:
            signals=schedule(allbars,tf,family,ratio,fs,mode)
            # Check every candidate signal against bars truncated at its decision time.
            for idx,s in signals.items():
                at=clock_minute(s['known_at'])
                for f in fs:
                    past=[b for b in allbars[f] if clock_minute(b['time'])+f<=at]
                    assert direction(past,f,at,mode)
            for stop,kind,distance in itertools.product((30,50,80),('fixed','trailing'),(30,50,80,130)):
                p=dict(entry_tf=tf,family=family,volume_ratio=ratio,filters=fs,
                       filter_mode=mode,stop=stop,exit_kind=kind,distance=distance)
                r=replay(allbars[1],minutes,signals,stop,kind,distance,bar_minutes=1)
                assert abs(sum(t['net'] for t in r['trades'])-r['net'])<.001
                assert all(clock_minute(t['entry_time'])>=clock_minute(t['signal']['known_at']) for t in r['trades'])
                item=dict(params=p,result=r,signal_count=len(signals))
                score=(r['net'],-r['drawdown'])
                if best is None or score>best[0]:
                    best=(score,item)
                group=f'{tf}min_'+('mixed' if fs else 'alone')
                if group not in group_best or score>group_best[group][0]:
                    group_best[group]=(score,item)
                rows.append(dict(**{**p,'filters':'+'.join(map(str,fs)) or 'none'},
                                 net=r['net'],drawdown=r['drawdown'],trades=r['count'],wins=r['wins']))
    winner=best[1]
    p=winner['params']
    sig=schedule(allbars,p['entry_tf'],p['family'],p['volume_ratio'],p['filters'],p['filter_mode'])
    stress={str(s):replay(allbars[1],minutes,sig,p['stop'],p['exit_kind'],p['distance'],s,bar_minutes=1) for s in (0,5,10)}
    report=dict(status='RETROSPECTIVE_UNVERIFIED_SOURCE',tested=len(rows),
        positive=sum(r['net']>0 for r in rows),winner=winner,
        group_best={g:v[1] for g,v in group_best.items()},stress=stress,
        input_sha256=hashlib.sha256((SOURCE/'today_minutes.json').read_bytes()).hexdigest(),
        assumptions='100 shares, long only, one position, no averaging. Fees 0.015% each side, '
                    'adverse tick rounding plus 5 won each side, taxes excluded. No live orders. '
                    'Trailing high updates at one-minute closes for ALL candidates, activates at +40 won. '
                    'Only completed higher-timeframe bars are used. 15:20+ no new entries, 15:30 liquidation. '
                    'Future day data used to SELECT the winning rule, not to trigger individual fills. '
                    'Not an exhaustive maximum over all possible strategies; same input has been studied repeatedly.')
    (OUT/'results.json').write_text(json.dumps(report,indent=2))
    with (OUT/'trials.csv').open('w',newline='',encoding='utf-8-sig') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader()
        w.writerows(sorted(rows,key=lambda r:(r['net'],-r['drawdown']),reverse=True))
    print(json.dumps(dict(tested=len(rows),positive=report['positive'],winner=winner,
          groups={g:dict(params=v[1]['params'],net=v[1]['result']['net']) for g,v in group_best.items()},
          stress={s:v['net'] for s,v in stress.items()}),indent=2))


if __name__=='__main__':
    main()
