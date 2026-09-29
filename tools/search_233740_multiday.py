"""Bounded retrospective search; September 8 never participates in selection."""
import csv
import hashlib
import itertools
import json
from pathlib import Path

from tools.compare_233740_timeframes import aggregate
from tools.search_233740_mixed import schedule
from tools.search_233740_patterns import replay

ROOT = Path('output/paper_grid')
OUT = ROOT / 'multiday_search_20260901_07'
DAYS = ('20260901', '20260902', '20260903', '20260904', '20260907')


def load(day):
    path = (ROOT / 'replay_20260907/today_minutes.json' if day == '20260907'
            else ROOT / f'frozen_validation_{day}/minutes.json')
    minutes = json.loads(path.read_text())
    required = {f'{m//60:02d}{m%60:02d}00' for m in range(540, 920)} | {'153000'}
    assert required <= {r['time'] for r in minutes}
    assert len({r['time'] for r in minutes}) == len(minutes)
    assert all(r['date'] == day for r in minutes)
    assert minutes == sorted(minutes, key=lambda r: r['time'])
    assert all(0 < r['low'] <= min(r['open'], r['close']) <=
               max(r['open'], r['close']) <= r['high'] for r in minutes)
    return minutes, {tf: aggregate(minutes, tf) for tf in (1, 3, 5)}, dict(
        path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        minute_count=len(minutes), invalid_tick_count=sum(
            any(r[k] % 5 for k in ('open', 'high', 'low', 'close')) for r in minutes))


def run(data, params, slip=5):
    minutes, bars, _ = data
    sig = schedule(bars, params['entry_tf'], params['family'], params['volume_ratio'],
                   params['filters'], params['filter_mode'])
    result = replay(bars[1], minutes, sig, params['stop'], params['exit_kind'],
                    params['distance'], slip, bar_minutes=1)
    assert abs(sum(t['net'] for t in result['trades']) - result['net']) < .001
    return result


def main():
    OUT.mkdir(exist_ok=True)
    data = {d: load(d) for d in DAYS}
    rows = []
    best = None
    for tf, family, ratio in itertools.product((1, 3, 5),
            ('rebound_break', 'higher_low', 'ma_3', 'ma_5', 'ma_10'), (0, 1, 1.3)):
        others = [f for f in (1, 3, 5) if f != tf]
        filters = [([], 'none')] + [(fs, mode) for fs in ([others[0]], [others[1]], others)
                                    for mode in ('rising_close', 'ma3', 'ma5')]
        for fs, mode in filters:
            signals = {d: schedule(v[1], tf, family, ratio, fs, mode) for d, v in data.items()}
            for stop, kind, distance in itertools.product((30, 50, 80), ('fixed', 'trailing'), (30, 50, 80, 130)):
                params = dict(entry_tf=tf, family=family, volume_ratio=ratio, filters=fs,
                              filter_mode=mode, stop=stop, exit_kind=kind, distance=distance)
                results = {d: replay(v[1][1], v[0], signals[d], stop, kind, distance, 5, bar_minutes=1)
                           for d, v in data.items()}
                nets = [r['net'] for r in results.values()]
                positive = sum(n > 0 for n in nets)
                # Predetermined objective: profitable days, then worst day, then total.
                score = (positive, min(nets), sum(nets), -max(r['drawdown'] for r in results.values()))
                row = dict(params=json.dumps(params), positive_days=positive, worst_day=min(nets),
                           net=sum(nets), trades=sum(r['count'] for r in results.values()),
                           wins=sum(r['wins'] for r in results.values()),
                           **{d: results[d]['net'] for d in DAYS})
                rows.append(row)
                if best is None or score > best[0]:
                    best = score, params
        print(f'Completed {tf}m {family} volume={ratio}: {len(rows)} candidates', flush=True)
    # Persist the selection BEFORE reading September 8 data.
    selected = dict(params=best[1], score=best[0], selection_days=DAYS,
                    selection_rule='positive_days, worst_day_net, total_net, negative_max_daily_drawdown')
    (OUT / 'selected_parameters.json').write_text(json.dumps(selected, indent=2))
    with (OUT / 'trials.csv').open('w', newline='', encoding='utf-8-sig') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    holdout = load('20260908')
    details = {d: {str(s): run(v, best[1], s) for s in (0, 5, 10)}
               for d, v in {**data, '20260908': holdout}.items()}
    report = dict(status='RETROSPECTIVE_UNVERIFIED_VIRTUAL_DATA', tested=len(rows),
                  all_days_positive=sum(r['positive_days'] == 5 for r in rows),
                  all_trades_profitable=sum(r['trades'] > 0 and r['wins'] == r['trades']
                                           and r['positive_days'] == 5 for r in rows),
                  selected=selected, results=details,
                  inputs={d: v[2] for d, v in {**data, '20260908': holdout}.items()},
                  caveat='September 8 is excluded from this selection, but its results were already viewed in earlier research; not a pristine holdout. No live strategy changes.')
    (OUT / 'results.json').write_text(json.dumps(report, indent=2))
    lines = ['# 233740 다섯 거래일 공통 조건 탐색', '',
             '9월 1·2·3·4·7일에 동일한 규칙을 적용. 10,800개 조합 중 수익 날짜 수, 최악 날짜 손익, 합계 손익 순으로 선정.',
             f"다섯 날짜 모두 양수인 조합: {report['all_days_positive']}개. 모든 거래까지 수익인 조합: {report['all_trades_profitable']}개.",
             '', '선정 조건: `' + json.dumps(best[1]) + '`', '',
             '| 날짜 | 거래 | 승 | 순손익(원) | 체결 불이익 10원 손익 |', '|---|---:|---:|---:|---:|']
    for d, result in details.items():
        r = result['5']
        lines.append(f"| {d} | {r['count']} | {r['wins']} | {r['net']:,.3f} | {result['10']['net']:,.3f} |")
    lines += ['', '100주 단일 보유, 추가 매수 없음. 매수·매도 각각 수수료 0.015%, 불리한 호가 정렬 및 5원 체결 불이익, 세금 제외. 동일 분 목표·손절 동시 접촉은 손절 우선. 15:20 이후 진입 금지, 15:30 청산. 추적 손절은 +40원부터 활성화하고 완성된 1분봉 고가로 다음 분부터 갱신.', '',
              '모의환경 원본의 호가 단위 이상을 보존한 조건부 사후 최적화. 실제 시세 검증 및 수익 보장이 아니다. 9월 8일은 이번 선정에서 제외했으나 이전 연구에서 이미 본 날짜라 완전히 새로운 독립 검증은 아니다. 운영 규칙은 변경하지 않았다.', '',
              '재현: `python -m tools.search_233740_multiday`']
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(tested=len(rows), all_days_positive=report['all_days_positive'],
                         all_trades_profitable=report['all_trades_profitable'], selected=selected,
                         daily={d: {k: r['5'][k] for k in ('net', 'count', 'wins')} for d, r in details.items()}), indent=2))


if __name__ == '__main__':
    main()
