"""Frozen selected signals, independent 100-share lots, 500 shares bought per day."""
import hashlib
import json
from pathlib import Path
from tools.search_233740_multiday import DAYS, OUT as SEARCH, load
from tools.search_233740_mixed import schedule
from tools.search_233740_patterns import replay

OUT = Path('output/paper_grid/daily500_selected_rule')


def replay_lots(bars, minutes, signals, stop=50, target=50, slip=5):
    # Each signal is evaluated independently, including while earlier lots remain open.
    eligible = [(i, s) for i, s in sorted(signals.items())
                if i+1 < len(bars) and bars[i+1]['time'] < '1520']
    trades = []
    for i, signal in eligible[:5]:
        result = replay(bars, minutes, {i: signal}, stop, 'fixed', target, slip, bar_minutes=1)
        assert result['count'] == 1
        trades.extend(dict(t, quantity=100) for t in result['trades'])
    return dict(eligible_signals=len(eligible), skipped_daily_limit=max(0, len(eligible)-5),
                bought_quantity=100*len(trades), count=len(trades),
                wins=sum(t['net'] > 0 for t in trades),
                net=round(sum(t['net'] for t in trades), 3), trades=trades)


def main():
    OUT.mkdir(exist_ok=True)
    source = SEARCH / 'selected_parameters.json'
    p = json.loads(source.read_text())['params']
    assert p['exit_kind'] == 'fixed'
    days = {}
    for day in (*DAYS, '20260908'):
        minutes, bars, audit = load(day)
        signals = schedule(bars, p['entry_tf'], p['family'], p['volume_ratio'],
                           p['filters'], p['filter_mode'])
        days[day] = dict(input=audit, **replay_lots(bars[1], minutes, signals, p['stop'], p['distance']))
    report = dict(params=p, parameter_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  daily_buy_limit=500, lot_quantity=100, independent_lot_exits=True,
                  daily_limit_restored_on_sale=False, days=days,
                  assumptions='Same frozen signals; completed MA10 CROSS above, not continuously above. '
                  'Each signal buys one lot even when holding. Fee .015% each side, adverse tick rounding '
                  'and 5 won slippage each side. Tax excluded. Unverified virtual source. No live changes.')
    (OUT / 'results.json').write_text(json.dumps(report, indent=2))
    lines = ['# 고정 전략 하루 누적 500주 매수 재생', '',
             '조건 재탐색 없음. 신호마다 100주, 보유 중에도 추가 매수, 하루 누적 500주 한도. 매도해도 한도 복원 없음. 각 매수분별 목표 +50원/손절 -50원.', '',
             '| 날짜 | 신호 수 | 매수 주수 | 승/거래 | 비용 후 손익 |', '|---|---:|---:|---:|---:|']
    for day, r in days.items():
        lines.append(f"| {day} | {r['eligible_signals']} | {r['bought_quantity']} | {r['wins']}/{r['count']} | {r['net']:,.3f} |")
    lines += ['', '각 날짜 신호가 1개뿐이므로 추가 매수가 발생하지 않았고 기존 결과와 같다. MA10 위에 계속 머무르는 매 분을 새 신호로 간주하지 않는다. 그런 방식은 기존 돌파 조건을 바꾸는 별도 전략이다.', '',
              '수수료 각 0.015%, 불리한 호가 정렬과 체결 각 5원, 세금 제외. 모의환경 원본 가격 이상을 포함한 조건부 결과. 실제 주문/운영 변경 없음.']
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({day: {k: r[k] for k in ('eligible_signals', 'bought_quantity', 'count', 'wins', 'net')}
                      for day, r in days.items()}, indent=2))


if __name__ == '__main__':
    main()
