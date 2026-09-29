"""Bounded, explicitly in-sample exit search on unverified saved quotes."""
import csv
import hashlib
import json
import math
from pathlib import Path

SOURCE = Path('output/paper_grid/replay_20260907')
OUT = SOURCE / 'exit_search'
TARGETS = (20, 30, 40, 50, 60, 80, 100, 130)
STOPS = ('pivot', 20, 30, 40, 50, 70, 100)
FEE = .00015
QTY = 100


def signals(bars):
    """Confirmed pivots, no future-bar input and no repeated setup."""
    lows, used, result = [], set(), {}
    for i, bar in enumerate(bars):
        if i >= 2 and bars[i-1]['low'] < min(bars[i-2]['low'], bar['low']):
            lows.append(i-1)
        if len(lows) < 3:
            continue
        a, b, c = lows[-3:]
        level = max(x['high'] for x in bars[b+1:c])
        if (bars[b]['low'] < bars[a]['low'] and bars[c]['low'] > bars[b]['low']
                and min(x['low'] for x in bars[c+1:i+1]) >= bars[c]['low']
                and bar['close'] > level and c not in used):
            result[i] = dict(stop=bars[c]['low']-5, signal=bar['time'])
            used.add(c)
    return result


def simulate(bars, minutes, setups, target, stop, slip=5, tick=True,
             start='090000', end='153000'):
    """Next-open entries; adverse tick rounding is a scenario, not data repair."""
    def buy(x):
        return (math.ceil(x/5)*5 if tick else x) + slip
    def sell(x):
        return (math.floor(x/5)*5 if tick else x) - slip
    entries = {bars[i+1]['time']+'00': setup for i, setup in setups.items()
               if i+1 < len(bars) and bars[i]['time']+'00' >= start}
    rows = [r for r in minutes if start <= r['time'] <= end]
    position, trades = None, []
    equity, peak, drawdown = 0., 0., 0.
    for m in rows:
        t = m['time']
        if position is None and t in entries and t < end:
            setup = entries[t]
            entry = buy(m['open'])
            threshold = setup['stop'] if stop == 'pivot' else entry-stop
            if tick:
                threshold = math.floor(threshold/5)*5
            if entry > threshold:
                position = dict(entry_time=t, entry=entry, stop=threshold,
                                target=entry+target, signal=setup['signal'])
        if position:
            reason, fill = None, None
            if m['low'] <= position['stop']:
                reason, fill = 'STOP', sell(min(m['open'], position['stop']))
            elif m['high'] >= position['target']:
                # Target trigger followed by adverse market execution assumption.
                reason, fill = 'TARGET', sell(position['target'])
            elif t == end:
                reason, fill = 'SESSION_END', sell(m['close'])
            if reason:
                gross = (fill-position['entry'])*QTY
                fees = (fill+position['entry'])*QTY*FEE
                trades.append(dict(**position, exit_time=t, exit=fill, reason=reason,
                                   gross=gross, fees=fees, net=gross-fees))
                equity += gross-fees
                position = None
        marked = equity
        if position:
            marked += ((m['close']-position['entry'])*QTY
                       -(m['close']+position['entry'])*QTY*FEE)
        peak = max(peak, marked)
        drawdown = max(drawdown, peak-marked)
    assert position is None
    return dict(target=target, stop=stop, slip_per_side=slip,
                adverse_tick_rounding=tick, net=round(equity, 4),
                max_minute_close_drawdown=round(drawdown, 4),
                trade_count=len(trades), trades=trades)


def main():
    OUT.mkdir(exist_ok=True)
    minutes = json.loads((SOURCE/'today_minutes.json').read_text())
    bars = json.loads((SOURCE/'five_minutes.json').read_text())
    setups = signals(bars)
    # Causality audit: truncating future bars must preserve every existing signal.
    for n in range(1, len(bars)+1):
        assert signals(bars[:n]) == {i:s for i,s in setups.items() if i<n}
    trials = []
    for target in TARGETS:
        for stop in STOPS:
            full = simulate(bars, minutes, setups, target, stop)
            morning = simulate(bars, minutes, setups, target, stop, end='115900')
            trials.append(dict(target=target, stop=stop, full=full, morning=morning))
    # Deterministic ties: lower drawdown, smaller target, then enumeration order.
    def rank(row, key):
        r = row[key]
        return (r['net'], -r['max_minute_close_drawdown'], -row['target'])
    best = max(trials, key=lambda r: rank(r, 'full'))
    chosen_am = max(trials, key=lambda r: rank(r, 'morning'))
    afternoon = simulate(bars, minutes, setups, chosen_am['target'], chosen_am['stop'],
                         start='120000')
    stress = [simulate(bars, minutes, setups, best['target'], best['stop'], slip=s)
              for s in (0, 5, 10)]
    original = simulate(bars, minutes, setups, 130, 'pivot', slip=0, tick=False)
    assert abs(original['net'] - (-4114.105)) < .001
    for row in trials:
        for key in ('full', 'morning'):
            r = row[key]
            assert abs(sum(t['net'] for t in r['trades'])-r['net']) < .001
            assert all(t['entry']%5 == 0 and t['exit']%5 == 0 for t in r['trades'])
    report = dict(status='IN_SAMPLE_SEARCH_ON_UNVERIFIED_QUOTES',
        input_sha256=hashlib.sha256((SOURCE/'today_minutes.json').read_bytes()).hexdigest(),
        warning='No source correction. Tick rounding is an execution sensitivity scenario only. '
                'Full-day winner was selected after seeing the day. Afternoon is an illustrative '
                'chronological split, not untouched out-of-sample data: the day was already inspected.',
        trial_count=len(trials), positive_full_day=sum(r['full']['net']>0 for r in trials),
        fixed_rules='Original confirmed higher-low breakout; long 100 shares; no averaging; '
                    'next open; 0.015% fee each side; taxes excluded; stop first within minute.',
        signals=setups, original=original, best_full_day=best,
        baseline_same_execution=simulate(bars, minutes, setups, 130, 'pivot'),
        morning_selected=chosen_am, afternoon_with_morning_choice=afternoon,
        full_day_winner_slippage_stress=stress, trials=trials)
    (OUT/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (OUT/'trials.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer=csv.writer(handle)
        writer.writerow(['target','stop','full_net','morning_net','full_drawdown','trades'])
        for r in trials:
            writer.writerow([r['target'], r['stop'], r['full']['net'],
                             r['morning']['net'],r['full']['max_minute_close_drawdown'],
                             r['full']['trade_count']])
    print(json.dumps({k:v for k,v in report.items() if k!='trials'}, indent=2))


if __name__ == '__main__':
    main()
