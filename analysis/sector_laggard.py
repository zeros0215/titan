"""Point-in-time backtest for laggards inside rising peer groups."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.sector_groups import SECTOR_GROUPS
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


@dataclass(frozen=True)
class SectorLaggardTrade:
    signal_date: str
    group: str
    code: str
    name: str
    group_return: float
    stock_return: float
    lag_gap: float
    positive_ratio: float
    volume_ratio: float
    confirmed: bool
    entry_date: str
    exit_date: str
    exit_reason: str
    holding_sessions: int
    gross_return: float
    net_return: float
    win: bool


def run_sector_laggard_backtest(
    active_data_path: Path,
    output_dir: Path,
    start_date: str = "2022-04-01",
    end_date: str = "2023-09-01",
    lookback_sessions: int = 5,
    holding_sessions: int = 5,
    group_return_threshold: float = 0.03,
    lag_gap_threshold: float = 0.03,
    convergence_gap: float = 0.01,
) -> tuple[dict, dict[str, Path]]:
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if lookback_sessions < 2 or holding_sessions < 1:
        raise ValueError("session counts are invalid")
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    ranking = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )
    eligible = {
        datetime.fromisoformat(key): set(value)
        for key, value in ranking["sessions"].items()
    }
    sessions = sorted(eligible)
    provider = HistoricalFileMarketProvider(price_dir)
    candles = {}
    for members in SECTOR_GROUPS.values():
        for code in members:
            try:
                candles[code] = {c.date: c for c in provider._candles(code)}
            except FileNotFoundError:
                candles[code] = {}
    costs = transaction_cost_policy_from_env()
    trades: list[SectorLaggardTrade] = []
    busy_until: dict[str, datetime] = {}
    latest_candidates = []

    for index in range(lookback_sessions, len(sessions) - 1):
        signal = sessions[index]
        if signal < start or signal > end:
            continue
        prior = sessions[index - lookback_sessions]
        candidates = _signals(signal, prior, eligible[signal], candles)
        latest_candidates = candidates
        for item in candidates:
            code = item["code"]
            if busy_until.get(code, datetime.min) >= signal:
                continue
            if item["group_return"] < group_return_threshold:
                continue
            if item["lag_gap"] < lag_gap_threshold or item["stock_return"] < -0.03:
                continue
            entry_index = index + 1
            if entry_index + holding_sessions - 1 >= len(sessions):
                continue
            entry_date = sessions[entry_index]
            entry = candles[code].get(entry_date)
            if entry is None or entry.open <= 0:
                continue
            exit_index = entry_index + holding_sessions - 1
            exit_reason = "5거래일 종가"
            for probe in range(entry_index, exit_index + 1):
                date = sessions[probe]
                spread = _spread_on(date, prior, item["group"], code, candles)
                if spread is not None and spread <= convergence_gap:
                    exit_index, exit_reason = probe, "격차 수렴"
                    break
            exit_date = sessions[exit_index]
            exit_candle = candles[code].get(exit_date)
            if exit_candle is None:
                continue
            gross = exit_candle.close / entry.open - 1
            net = costs.net_return(entry.open, exit_candle.close)
            trades.append(SectorLaggardTrade(
                signal_date=signal.date().isoformat(),
                group=item["group"], code=code, name=item["name"],
                group_return=item["group_return"],
                stock_return=item["stock_return"], lag_gap=item["lag_gap"],
                positive_ratio=item["positive_ratio"],
                volume_ratio=item["volume_ratio"],
                confirmed=item["confirmed"],
                entry_date=entry_date.date().isoformat(),
                exit_date=exit_date.date().isoformat(),
                exit_reason=exit_reason,
                holding_sessions=exit_index - entry_index + 1,
                gross_return=gross, net_return=net, win=net > 0,
            ))
            busy_until[code] = exit_date

    raw = trades
    confirmed = [trade for trade in trades if trade.confirmed]
    by_group = {
        group: _summary([trade for trade in trades if trade.group == group])
        for group in SECTOR_GROUPS
    }
    result = {
        "schema_version": 1,
        "strategy": "상승 업종 내 5일 수익률 후발주를 익일 시가 매수",
        "period": {"start": start_date, "end": end_date},
        "rules": {
            "lookback_sessions": lookback_sessions,
            "holding_sessions": holding_sessions,
            "group_return_threshold": group_return_threshold,
            "positive_member_ratio": 0.60,
            "lag_gap_threshold": lag_gap_threshold,
            "minimum_stock_return": -0.03,
            "confirmation": "신호일 상승 및 20일 평균 대비 거래량 1배 이상",
            "exit": "격차 1%p 이내 수렴 또는 5거래일 종가",
        },
        "groups": SECTOR_GROUPS,
        "summaries": {"RAW": _summary(raw), "CONFIRMED": _summary(confirmed)},
        "group_summaries": by_group,
        "latest_candidates": latest_candidates,
        "trades": [asdict(trade) for trade in trades],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "sector_laggard_backtest.json"
    csv_path = output_dir / "sector_laggard_trades.csv"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(trades[0]).keys()) if trades else ["signal_date"])
        writer.writeheader()
        writer.writerows(asdict(trade) for trade in trades)
    return result, {"json": json_path, "csv": csv_path}


def _signals(signal, prior, eligible, candles):
    output = []
    for group, members in SECTOR_GROUPS.items():
        rows = []
        for code, name in members.items():
            start, end = candles[code].get(prior), candles[code].get(signal)
            if code not in eligible or start is None or end is None or start.close <= 0:
                continue
            history = [c.volume for date, c in candles[code].items() if date < signal][-20:]
            volume_ratio = end.volume / statistics.mean(history) if history and statistics.mean(history) else 0
            rows.append((code, name, end.close / start.close - 1, volume_ratio, end.close > end.open))
        if len(rows) < 3:
            continue
        median = statistics.median(row[2] for row in rows)
        positive = sum(row[2] > 0 for row in rows) / len(rows)
        if positive < 0.60:
            continue
        for code, name, stock_return, volume_ratio, up_day in rows:
            output.append({
                "signal_date": signal.date().isoformat(), "group": group,
                "code": code, "name": name, "group_return": median,
                "stock_return": stock_return, "lag_gap": median - stock_return,
                "positive_ratio": positive, "volume_ratio": volume_ratio,
                "confirmed": up_day and volume_ratio >= 1.0,
            })
    return sorted(output, key=lambda row: (-row["lag_gap"], row["code"]))


def _spread_on(date, start, group, code, candles):
    target_start, target = candles[code].get(start), candles[code].get(date)
    if target_start is None or target is None:
        return None
    peers = []
    for peer in SECTOR_GROUPS[group]:
        a, b = candles[peer].get(start), candles[peer].get(date)
        if a is not None and b is not None and a.close > 0:
            peers.append(b.close / a.close - 1)
    return statistics.median(peers) - (target.close / target_start.close - 1) if peers else None


def _summary(trades):
    returns = [trade.net_return for trade in trades]
    return {
        "trades": len(trades),
        "wins": sum(trade.win for trade in trades),
        "win_rate": sum(trade.win for trade in trades) / len(trades) if trades else None,
        "average_net_return": statistics.mean(returns) if returns else None,
        "median_net_return": statistics.median(returns) if returns else None,
        "total_compound_return": _compound(returns),
    }


def _compound(values):
    capital = 1.0
    for value in values:
        capital *= 1 + value
    return capital - 1
