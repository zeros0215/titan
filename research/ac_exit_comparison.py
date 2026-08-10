"""Compare alternative exits on the frozen A4/C3 entry stream."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data
from research.portfolio_evaluation import _replay


@dataclass(frozen=True)
class ExitResult:
    date: datetime
    price: float
    reason: str
    net_return: float


def target_stop_exit(candles, entry_price, target, stop, maximum_days, costs):
    """Daily-bar simulation; entry day is excluded and ambiguous bars stop first."""
    rows = list(candles[1:maximum_days + 1])
    target_price, stop_price = entry_price * (1 + target), entry_price * (1 - stop)
    for row in rows:
        if row.open <= stop_price:
            return ExitResult(row.date, row.open, "STOP_GAP", costs.net_return(entry_price, row.open))
        if row.low <= stop_price and row.high >= target_price:
            return ExitResult(row.date, stop_price, "STOP_AMBIGUOUS", costs.net_return(entry_price, stop_price))
        if row.low <= stop_price:
            return ExitResult(row.date, stop_price, "STOP", costs.net_return(entry_price, stop_price))
        if row.open >= target_price:
            return ExitResult(row.date, row.open, "TARGET_GAP", costs.net_return(entry_price, row.open))
        if row.high >= target_price:
            return ExitResult(row.date, target_price, "TARGET", costs.net_return(entry_price, target_price))
    if not rows:
        return None
    row = rows[-1]
    return ExitResult(row.date, row.close, "TIME", costs.net_return(entry_price, row.close))


def trend_exit(candles, entry_price, costs):
    """-7% initial stop, +10% half take-profit, then 10-day MA exit, max 40 days."""
    rows = list(candles[:41])
    if len(rows) < 2:
        return None
    stop_price, target_price = entry_price * .93, entry_price * 1.10
    half_exit = None
    pending_ma_exit = False
    for index, row in enumerate(rows[1:], start=1):
        if pending_ma_exit:
            second = costs.net_return(entry_price, row.open)
            net = second if half_exit is None else (half_exit + second) / 2
            return ExitResult(row.date, row.open, "MA10_NEXT_OPEN", net)
        if half_exit is None:
            if row.open <= stop_price:
                return ExitResult(row.date, row.open, "STOP_GAP", costs.net_return(entry_price, row.open))
            if row.low <= stop_price and row.high >= target_price:
                return ExitResult(row.date, stop_price, "STOP_AMBIGUOUS", costs.net_return(entry_price, stop_price))
            if row.low <= stop_price:
                return ExitResult(row.date, stop_price, "STOP", costs.net_return(entry_price, stop_price))
            if row.open >= target_price:
                half_exit = costs.net_return(entry_price, row.open)
            elif row.high >= target_price:
                half_exit = costs.net_return(entry_price, target_price)
        if half_exit is not None and index >= 9:
            ma10 = sum(item.close for item in rows[index - 9:index + 1]) / 10
            pending_ma_exit = row.close < ma10
    row = rows[-1]
    second = costs.net_return(entry_price, row.close)
    net = second if half_exit is None else (half_exit + second) / 2
    return ExitResult(row.date, row.close, "MAX_40", net)


def save_ac_exit_comparison(active_data_path: Path, artifact_dirs: dict[str, Path], output: Path) -> dict:
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    provider = HistoricalFileMarketProvider(price_dir)
    costs = transaction_cost_policy_from_env()
    rules = {
        "baseline_40d": None,
        "short_tp5_sl10_20d": (.05, .10, 20),
        "balanced_tp10_sl7_20d": (.10, .07, 20),
        "trend_half_tp10_sl7_ma10_40d": "trend",
    }
    signals = {name: [] for name in rules}
    price_maps = {}
    exit_reasons = {name: {} for name in rules}
    for source, directory in artifact_dirs.items():
        for path in sorted((directory / "validations").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry_date = datetime.fromisoformat(payload["selected_at"])
            baseline_exit = datetime.fromisoformat(payload["evaluation_date"])
            for trade in payload.get("trades", []):
                code = str(trade["code"]).zfill(6)
                try:
                    history = provider._candles(code)
                except FileNotFoundError:
                    continue
                start = next((i for i, row in enumerate(history) if row.date == entry_date), None)
                if start is None:
                    continue
                entry_price = float(trade["selection_price"])
                common = {"source": source, "entry": entry_date, "code": code,
                          "rank": int(trade["rank"]), "selection_price": entry_price}
                signals["baseline_40d"].append({**common, "exit": baseline_exit,
                    "net_return": float(trade["net_return"])})
                for name, rule in rules.items():
                    if rule is None:
                        continue
                    result = (trend_exit(history[start:], entry_price, costs) if rule == "trend"
                              else target_stop_exit(history[start:], entry_price, *rule, costs))
                    if result is None:
                        continue
                    signals[name].append({**common, "exit": result.date, "net_return": result.net_return})
                    exit_reasons[name][result.reason] = exit_reasons[name].get(result.reason, 0) + 1
                if code not in price_maps:
                    price_maps[code] = {row.date: row.close for row in history}
    rows = []
    for name, items in signals.items():
        replay = _replay(items, price_maps, 7, {"A": 4, "C": 3})
        returns = [row["net_return"] for row in items]
        rows.append({"rule": name, **replay, "candidate_trades": len(items),
                     "win_rate": sum(x > 0 for x in returns) / len(returns),
                     "average_net_return": sum(returns) / len(returns),
                     "exit_reasons": exit_reasons[name]})
    result = {"schema_version": 1, "assumptions": {
        "entry_day_exit": "excluded", "same_bar_target_and_stop": "stop_first",
        "stop_gap": "actual_open", "costs": "configured round-trip costs included",
    }, "rows": rows, "operational_orders": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# A4/C3 매도 규칙 비교", "", "> 동일한 A4/C3 진입 후보와 고정 슬롯을 사용한 연구용 일봉 검증입니다. 실제 주문은 없습니다.", "",
             "|매도 규칙|후보|수용 거래|승률(후보)|평균 순수익(후보)|누적수익|MDD|", "|---|---:|---:|---:|---:|---:|---:|"]
    labels = {"baseline_40d": "기준 40일", "short_tp5_sl10_20d": "+5%/-10%/20일",
              "balanced_tp10_sl7_20d": "+10%/-7%/20일", "trend_half_tp10_sl7_ma10_40d": "+10% 절반/-7%/10일선/40일"}
    for row in rows:
        lines.append(f"|{labels[row['rule']]}|{row['candidate_trades']}|{row['accepted_trades']}|{row['win_rate']:.2%}|{row['average_net_return']:.2%}|{row['cumulative_return']:.2%}|{row['maximum_drawdown']:.2%}|")
    lines += ["", "## 보수적 체결 가정", "", "- 진입 당일 매도 판정 제외", "- 한 일봉에서 목표·손절 동시 도달 시 손절 우선", "- 손절가 아래 갭은 실제 시가 체결", "- 거래비용과 진입·청산 슬리피지 포함", ""]
    output.write_text("\n".join(lines), encoding="utf-8")
    result.update(markdown_path=str(output), json_path=str(output.with_suffix('.json')))
    return result
