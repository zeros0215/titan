"""One-day exploratory replay; read-only quotes, no order submission."""
import csv
import json
from datetime import date, datetime
from pathlib import Path
from broker.kis.client import KisReadOnlyClient
from broker.kis.session import KisSession
from broker.kis.intraday import KisIntradayProvider

OUT = Path('output/paper_grid/replay_20260907')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'today_minutes.json'
    if path.exists():
        minutes = json.loads(path.read_text())
    else:
        client = KisReadOnlyClient()
        client.minimum_interval_seconds = 1
        provider = KisIntradayProvider(KisSession(client))
        rows = {}
        try:
            for minute in range(9*60, 15*60+31, 30):
                end = f'{minute//60:02d}{minute%60:02d}00'
                payload = provider.session.get(
                    '/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice',
                    'FHKST03010200', dict(FID_COND_MRKT_DIV_CODE='J',
                    FID_INPUT_ISCD='233740', FID_INPUT_HOUR_1=end,
                    FID_PW_DATA_INCU_YN='Y', FID_ETC_CLS_CODE='')).json()
                if payload.get('rt_cd') != '0':
                    raise ValueError(payload.get('msg1'))
                (OUT/f'raw_{end}.json').write_text(json.dumps(payload, indent=2))
                for raw in payload.get('output2', []):
                    if raw['stck_bsop_date'] != '20260907':
                        continue
                    row = dict(date=raw['stck_bsop_date'], time=raw['stck_cntg_hour'])
                    for key, field in dict(open='stck_oprc', high='stck_hgpr',
                            low='stck_lwpr', close='stck_prpr', volume='cntg_vol').items():
                        row[key] = float(raw[field])
                    rows[row['time']] = row
        finally:
            provider.session.close()
        minutes = sorted(rows.values(), key=lambda r: r['time'])
        path.write_text(json.dumps(minutes, indent=2))
    invalid_ticks = [r for r in minutes if any(r[k] % 5 for k in ('open', 'high', 'low', 'close'))]
    if invalid_ticks:
        report = dict(status='UNVERIFIED_DATA_QUALITY', minute_count=len(minutes),
                      invalid_tick_rows=len(invalid_ticks), examples=invalid_ticks[:3],
                      reason='OHLC prices violate the configured five-won ETF tick. Do not interpret as market backtest.')
        (OUT/'validation.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    expected = {f'{m//60:02d}{m%60:02d}00' for m in range(540, 931)}
    if {r['time'] for r in minutes} != expected:
        raise ValueError('Missing or unexpected minute timestamps')
    if any(not (0 < r['low'] <= min(r['open'], r['close']) <= max(r['open'], r['close']) <= r['high']) for r in minutes):
        raise ValueError('Invalid OHLC ordering')
    groups = {}
    for r in minutes:
        t = r['time']
        if '090000' <= t < '152000':
            key = t[:2] + f'{int(t[2:4]) // 5 * 5:02d}'
            groups.setdefault(key, []).append(r)
    bars = []
    for t, rs in sorted(groups.items()):
        if len(rs) != 5:
            raise ValueError(f'Incomplete five-minute bar: {t}, {len(rs)}')
        bars.append(dict(time=t, open=rs[0]['open'], high=max(r['high'] for r in rs),
                         low=min(r['low'] for r in rs), close=rs[-1]['close']))
    # A pivot needs one completed bar on each side. Only known pivots are used.
    # Require a lower low followed by a higher low, then close above intervening high.
    results = []
    for slip in (0, 5):
        lows, trades, position, pending = [], [], None, None
        used = set()
        for i, bar in enumerate(bars):
            if pending and position is None:
                entry = bar['open'] + slip
                position = dict(entry_time=bar['time'], entry=entry,
                                stop=pending['stop'], target=entry+130,
                                signal_time=pending['signal_time'])
                pending = None
            if position:
                # Resolve exits with minute bars; if both hit in one minute, stop first.
                for m in groups[bar['time']]:
                    reason, fill = None, None
                    if m['low'] <= position['stop']:
                        reason, fill = 'STOP', min(m['open'], position['stop'])-slip
                    elif m['high'] >= position['target']:
                        reason, fill = 'TARGET', position['target']-slip
                    if reason:
                        finish(trades, position, m['time'], fill, reason)
                        position = None
                        break
            if i >= 2:
                k = i-1
                if bars[k]['low'] < bars[k-1]['low'] and bars[k]['low'] < bar['low']:
                    lows.append(k)
            if position is None and len(lows) >= 3:
                a, b, c = lows[-3:]
                level = max(x['high'] for x in bars[b+1:c]) if c > b+1 else float('inf')
                if (bars[b]['low'] < bars[a]['low'] and bars[c]['low'] > bars[b]['low']
                        and min(x['low'] for x in bars[c+1:i+1]) >= bars[c]['low']
                        and bar['close'] > level and c not in used):
                    pending = dict(stop=bars[c]['low']-5, signal_time=bar['time'])
                    used.add(c)
        if position:
            last = minutes[-1]
            finish(trades, position, last['time'], last['close']-slip, 'END_OF_DATA')
        results.append(dict(slippage_per_side=slip, trades=trades,
                            net=sum(t['net'] for t in trades)))
    (OUT/'five_minutes.json').write_text(json.dumps(bars, indent=2))
    with (OUT/'five_minutes.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(bars[0]))
        writer.writeheader()
        writer.writerows(bars)
    result = dict(generated_at=datetime.now().astimezone().isoformat(),
                  data_quality='UNVERIFIED_VIRTUAL_QUOTES' if invalid_ticks else 'TICK_CHECK_PASSED',
                  invalid_tick_rows=len(invalid_ticks),
                  day_high=max(r['high'] for r in minutes),
                  day_low=min(r['low'] for r in minutes),
                  assumptions=dict(quantity=100, target_won=130, stop='higher low minus 5 won',
                    pivot='strict low with one completed bar on each side; lower low then higher low',
                    entry='next 5-minute open after close exceeds intervening high',
                    fee_each_side=0.00015, taxes='excluded',
                    session='09:00-15:19 signals, remaining position liquidated at 15:30',
                    same_minute_exit='stop first', bar_labels='start time'),
                  first=minutes[0], last=minutes[-1], minute_count=len(minutes),
                  five_minute_count=len(bars), results=results)
    (OUT/'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

def finish(trades, p, time, fill, reason):
    gross = (fill-p['entry'])*100
    fees = (fill+p['entry'])*100*0.00015
    trades.append(dict(**p, exit_time=time, exit=fill, reason=reason,
                       gross=gross, fees=fees, net=gross-fees))

if __name__ == '__main__':
    main()
