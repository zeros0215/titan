"""Apply the previously selected September 7 rule unchanged to another date."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from broker.kis.client import KisReadOnlyClient
from broker.kis.session import KisSession
from config.settings import settings
from tools.compare_233740_timeframes import aggregate
from tools.search_233740_mixed import schedule, clock_minute, direction
from tools.search_233740_patterns import replay, make_plot


def main(target_date):
    stamp=target_date.strftime('%Y%m%d')
    out=Path('output/paper_grid')/f'frozen_validation_{stamp}'
    out.mkdir(exist_ok=True)
    source=Path('output/paper_grid/replay_20260907/mixed_timeframe_search/results.json')
    frozen=json.loads(source.read_text())['winner']['params']
    (out/'frozen_parameters.json').write_text(json.dumps(dict(params=frozen,
        selected_on='2026-09-07',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()),indent=2))
    path=out/'minutes.json'
    if path.exists():
        minutes=json.loads(path.read_text())
    else:
        client=KisReadOnlyClient(); client.minimum_interval_seconds=1
        session=KisSession(client)
        found={}
        try:
            for end in ('090000','110000','130000','150000','153000'):
                payload=session.get('/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice',
                    'FHKST03010230',dict(FID_COND_MRKT_DIV_CODE='J',FID_INPUT_ISCD='233740',
                    FID_INPUT_HOUR_1=end,FID_INPUT_DATE_1=stamp,FID_PW_DATA_INCU_YN='N',
                    FID_FAKE_TICK_INCU_YN='')).json()
                (out/f'raw_{end}.json').write_text(json.dumps(payload,indent=2))
                if payload.get('rt_cd')!='0':
                    raise ValueError(payload.get('msg1'))
                for r in payload.get('output2',[]):
                    if r.get('stck_bsop_date')!=stamp:
                        continue
                    row=dict(date=stamp,time=r['stck_cntg_hour'])
                    for k,v in dict(open='stck_oprc',high='stck_hgpr',low='stck_lwpr',
                                    close='stck_prpr',volume='cntg_vol').items():
                        row[k]=float(r[v])
                    found[row['time']]=row
        finally:
            session.close()
        minutes=sorted(found.values(),key=lambda r:r['time'])
        path.write_text(json.dumps(minutes,indent=2))
    required={f'{m//60:02d}{m%60:02d}00' for m in range(540,920)}|{'153000'}
    missing=sorted(required-{r['time'] for r in minutes})
    if missing:
        raise ValueError(f'Missing required minutes: {missing}')
    assert all(0<r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in minutes)
    invalid=[r for r in minutes if any(r[k]%5 for k in ('open','high','low','close'))]
    bars={tf:aggregate(minutes,tf) for tf in (1,3,5)}
    p=frozen
    sig=schedule(bars,p['entry_tf'],p['family'],p['volume_ratio'],p['filters'],p['filter_mode'])
    for i,s in sig.items():
        at=clock_minute(s['known_at'])
        past={tf:[b for b in bs if clock_minute(b['time'])+tf<=at] for tf,bs in bars.items()}
        assert all(direction(past[f],f,at,p['filter_mode']) for f in p['filters'])
    runs={str(s):replay(bars[1],minutes,sig,p['stop'],p['exit_kind'],p['distance'],s,bar_minutes=1) for s in (0,5,10)}
    for r in runs.values():
        assert abs(sum(t['net'] for t in r['trades'])-r['net'])<.001
    result=dict(date=target_date.isoformat(),status='FIXED_RULE_OTHER_DATE_UNVERIFIED_SOURCE',
        source_mode=settings.kis_mode,params=p,minute_count=len(minutes),invalid_tick_count=len(invalid),
        first=minutes[0],last=minutes[-1],high=max(r['high'] for r in minutes),
        low=min(r['low'] for r in minutes),signal_count=len(sig),signals=sig,
        main=runs['5'],stress=runs,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        validation_kind=('LATER_DATE_FIXED_RULE_REPLAY' if target_date>date(2026,9,7)
                         else 'SELECTION_DATE_REPLAY' if target_date==date(2026,9,7)
                         else 'EARLIER_DATE_TRANSFER_REPLAY'),
        note='No parameter search on this date. Historical replay, not live paper fills. '
             'Dates before selection are retrospective transfer tests. '
             '100 shares, one position, no averaging; fee .015% each side, '
             'adverse tick rounding and 5 won each side, taxes excluded; 15:30 liquidation.')
    (out/'results.json').write_text(json.dumps(result,indent=2))
    (out/'five_minutes.json').write_text(json.dumps(bars[5],indent=2))
    make_plot(bars[5],runs['5']['trades'],out/'trades.png',
              f'233740 | {target_date} | Frozen Sep 7 rule: 5m signal + 1m trend | 100 shares')
    print(json.dumps({k:v for k,v in result.items() if k not in ('stress','signals')},indent=2))
    print('STRESS',json.dumps({k:v['net'] for k,v in runs.items()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--date',required=True,type=date.fromisoformat)
    main(parser.parse_args().date)
