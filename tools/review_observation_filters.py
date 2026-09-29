"""Offline descriptive audit of stored July--September 2026 observations.

No strategy changes, market requests, or refitting of historical trades.
"""
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'reports' / 'observation_filters_202607_09'
MONTHS = ['2026-07', '2026-08', '2026-09']
VERSION = 'V1_3-S80-N7-TP5-SL10-CANDIDATE'


def metrics(rows):
    values = [r['net_return'] for r in rows]
    losses = -sum(v for v in values if v < 0)
    return dict(n=len(rows), wins=sum(v >= 0 for v in values),
                losses=sum(v < 0 for v in values),
                win_rate=mean(v >= 0 for v in values) if values else None,
                average_net_return=mean(values) if values else None,
                profit_factor=sum(v for v in values if v > 0)/losses if losses else None,
                unique_codes=len({r['code'] for r in rows}),
                selection_days=len({r['selection_date'] for r in rows}))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, unmatched, coverage = [], [], []
    files = sorted((ROOT/'output/kis_manual_tests/runs').glob(
        'LOCAL_2026*_H20_V1_3_S80_N7_TP5_SL10_CANDIDATE_TP5_SL10.json'))
    for path in files:
        run = json.loads(path.read_text(encoding='utf-8'))
        date = run['as_of'][:10]
        if date[:7] not in MONTHS:
            continue
        assert run['entry_mode'] == 'OPEN'
        assert run['profit_target'] == .05 and run['stop_loss'] == .1
        snap = ROOT/'output/kis_manual_tests/artifacts'/VERSION/date[:7]/'observations'/f'{date.replace("-", "")}T000000.json'
        snapshots = {r['code']: r for r in json.loads(snap.read_text(encoding='utf-8'))['selections']} if snap.exists() else {}
        trades = {t['code']: t for t in run['trades'] if t['cohort'] == 'OBSERVATION'}
        coverage.append(dict(date=date, candidates=len(run['observation_candidates']),
                             completed=len(trades), snapshot_present=snap.exists()))
        for candidate in run['observation_candidates']:
            code = candidate['code']
            if code not in trades:
                unmatched.append(dict(date=date, code=code, name=candidate['name']))
                continue
            snapshot = snapshots.get(code, {})
            context = snapshot.get('market_context', {})
            row = {**candidate, **trades[code], 'month': date[:7],
                   'market_regime': run.get('market_regime'),
                   'market': snapshot.get('market'),
                   'short_strength': context.get('short_market_strength'),
                   'kosdaq_short_trend': context.get('kosdaq_short_trend'),
                   'features': snapshot.get('enabled_features', []),
                   'feature_available': code in snapshots}
            rows.append(row)
    assert len(rows) == len({(r['selection_date'], r['code']) for r in rows})
    # Fixed interpretable cuts; descriptive comparisons, not an optimization grid.
    rules = {
        'risk_le_7': lambda r: r['risk_score'] <= 7,
        'risk_ge_11': lambda r: r['risk_score'] >= 11,
        'volume_le_9': lambda r: r['volume_score'] <= 9,
        'momentum_15': lambda r: r['momentum_score'] == 15,
        'price_action_le_5': lambda r: r['price_action_score'] <= 5,
        'score_lt_75': lambda r: r['total_score'] < 75,
        'score_ge_77': lambda r: r['total_score'] >= 77,
        'rank_ge_4': lambda r: r['rank'] >= 4,
        'market_strength_ge_70': lambda r: r['market_strength'] >= .7,
        'market_strength_lt_60': lambda r: r['market_strength'] < .6,
        'short_strength_lt_60': lambda r: r['short_strength'] is not None and r['short_strength'] < .6,
        'kosdaq_short_not_bull': lambda r: r['kosdaq_short_trend'] is not None and r['kosdaq_short_trend'] != 'BULL',
        'no_volume_surge': lambda r: r['feature_available'] and 'VOLUME_EXPLOSION' not in r['features'],
        'no_surge_or_acceleration': lambda r: r['feature_available'] and not {'VOLUME_EXPLOSION','ACCELERATION'}.intersection(r['features']),
        'combined_volatility_warning': lambda r: r['feature_available'] and not {'LOW_VOLATILITY','LOW_ATR'}.intersection(r['features']),
        'long_strong_short_weak': lambda r: r['market_strength'] >= .7 and r['short_strength'] is not None and r['short_strength'] < .6,
        'gap_positive': lambda r: r['opening_gap'] > 0,
        'gap_ge_1pct': lambda r: r['opening_gap'] >= .01,
        'risk7_volume9': lambda r: r['risk_score'] <= 7 and r['volume_score'] <= 9,
        'risk7_strong_market': lambda r: r['risk_score'] <= 7 and r['market_strength'] >= .7,
    }
    result = dict(scope='Selection month; completed observations only; exploratory, not holdout validation',
                  coverage=coverage, unmatched=unmatched, baseline=metrics(rows),
                  months={m: metrics([r for r in rows if r['month']==m]) for m in MONTHS}, rules={})
    for name, predicate in rules.items():
        result['rules'][name] = {
            period: dict(excluded=metrics([r for r in rows if (period=='ALL' or r['month']==period) and predicate(r)]),
                         retained=metrics([r for r in rows if (period=='ALL' or r['month']==period) and not predicate(r)]))
            for period in ['ALL', *MONTHS]}
    result['losing_names'] = [dict(code=code, name=next(r['name'] for r in rows if r['code']==code),
                                  **metrics([r for r in rows if r['code']==code]))
                              for code in sorted({r['code'] for r in rows if not r['win']})]
    # Classify candidates omitted from completed-trade summaries using the same
    # next-session calendar and opening-gap rule, without calling them losses.
    active=json.loads((ROOT/'output/release/backtest_data.json').read_text(encoding='utf-8'))
    price_dir=Path(active['price_dir'])
    sessions=sorted(json.loads((price_dir/'market_cap_top500.json').read_text(encoding='utf-8'))['sessions'])
    prices={}
    for item in unmatched:
        code=item['code']; date=item['date']
        if code not in prices:
            prices[code]={c['date'][:10]:c for c in json.loads((price_dir/f'{code}.json').read_text(encoding='utf-8'))['candles']}
        future=[d[:10] for d in sessions if d[:10]>date]
        before=prices[code].get(date); entry=prices[code].get(future[0]) if future else None
        if before is None or entry is None:
            item['classification']='NO_ENTRY_DATA'
            continue
        gap=entry['open']/before['close']-1
        item.update(opening_gap=gap, buy_date=future[0], buy_price=entry['open'])
        if abs(gap)>.03:
            item['classification']='GAP_EXCLUDED'
        else:
            item['classification']='PENDING_OR_UNRECORDED'
            candles=[prices[code][d] for d in future if d in prices[code]]
            item['latest_gross_mark']=candles[-1]['close']/entry['open']-1
    result['unmatched_counts']={m:dict(Counter(r['classification'] for r in unmatched if r['date'].startswith(m))) for m in MONTHS}
    (OUT/'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'joined_trades.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    keys = ['month','selection_date','code','name','total_score','risk_score','volume_score','momentum_score','price_action_score','market_strength','short_strength','opening_gap','buy_date','sell_date','net_return','win']
    with (OUT/'trades.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=keys, extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:result[k] for k in ['baseline','months']}, ensure_ascii=True))
    print('coverage',len(coverage),'candidates',sum(x['candidates'] for x in coverage),'unmatched',len(unmatched))
    print('unmatched_counts',result['unmatched_counts'])
    for name, periods in result['rules'].items():
        print(name, json.dumps({p:{side:{k:v[k] for k in ['n','wins','win_rate','average_net_return']} for side,v in groups.items()} for p,groups in periods.items()}))


if __name__ == '__main__':
    main()
