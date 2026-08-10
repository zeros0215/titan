"""Research J: semi-monthly adaptive momentum with volatility sizing."""

from __future__ import annotations

import json
import statistics
from datetime import date
from functools import lru_cache
from pathlib import Path

from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


def inverse_volatility_weights(rows: list[dict]) -> dict[str, float]:
    values = {row["code"]: 1 / row["volatility"] for row in rows if row["volatility"] > 0}
    total = sum(values.values())
    return {code: value / total for code, value in values.items()} if total else {}


def run_adaptive_momentum(
    active_data_path: Path,
    output_dir: Path,
    start_year: int = 2021,
    end_date: date | None = None,
) -> dict:
    _, price_dir, manifest = load_active_backtest_data(active_data_path)
    ranking = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    keys = sorted(ranking)
    sessions = [date.fromisoformat(key[:10]) for key in keys]
    indexes = {value: index for index, value in enumerate(sessions)}
    requested_end = end_date or sessions[-1]

    signals = []
    month_sessions: dict[tuple[int, int], list[date]] = {}
    for session in sessions:
        if session.year >= start_year and session <= requested_end:
            month_sessions.setdefault((session.year, session.month), []).append(session)
    for values in month_sessions.values():
        signals.extend((values[min(9, len(values) - 1)], values[-1]))
    signals = sorted(set(signals))

    @lru_cache(maxsize=None)
    def history(code: str) -> dict[date, dict]:
        try:
            payload = json.loads(
                (price_dir / f"{code}.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            date.fromisoformat(str(item["date"])[:10]): item
            for item in payload.get("candles", [])
        }

    def candle(code: str, when: date) -> dict | None:
        return history(str(code).zfill(6)).get(when)

    costs = transaction_cost_policy_from_env()
    periods = []
    trades = []
    equity = 1.0
    curve = [equity]
    for position in range(len(signals) - 1):
        signal, next_signal = signals[position], signals[position + 1]
        index, next_index = indexes[signal], indexes[next_signal]
        if index < 252 or next_index + 1 >= len(sessions):
            continue
        entry_date, exit_date = sessions[index + 1], sessions[next_index + 1]
        codes = [str(code).zfill(6) for code in ranking[keys[index]][:300]]

        market_returns = []
        for code in codes[:100]:
            now, old = candle(code, signal), candle(code, sessions[index - 200])
            if now and old and float(old["close"]) > 0:
                market_returns.append(float(now["close"]) / float(old["close"]) - 1)
        market_mean = sum(market_returns) / len(market_returns) if market_returns else -1
        breadth = (
            sum(value > 0 for value in market_returns) / len(market_returns)
            if market_returns else 0
        )
        exposure = 1.0 if market_mean > 0 and breadth >= 0.50 else (
            0.5 if market_mean > 0 and breadth >= 0.40 else 0.0
        )

        candidates = []
        for code in codes:
            now = candle(code, signal)
            points = [candle(code, sessions[index - lag]) for lag in (63, 126, 252)]
            ma_rows = [candle(code, sessions[offset]) for offset in range(index - 119, index + 1)]
            vol_rows = [candle(code, sessions[offset]) for offset in range(index - 60, index + 1)]
            if not now or any(item is None for item in points + ma_rows + vol_rows):
                continue
            close = float(now["close"])
            historical = [float(item["close"]) for item in points if item]
            ma120 = sum(float(item["close"]) for item in ma_rows if item) / 120
            closes = [float(item["close"]) for item in vol_rows if item]
            if close <= ma120 or any(value <= 0 for value in historical + closes):
                continue
            daily = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
            volatility = statistics.pstdev(daily)
            if volatility <= 0:
                continue
            composite = (
                0.5 * (close / historical[0] - 1)
                + 0.3 * (close / historical[1] - 1)
                + 0.2 * (close / historical[2] - 1)
            )
            candidates.append({"code": code, "score": composite, "volatility": volatility})
        selected = sorted(candidates, key=lambda item: (-item["score"], item["code"]))[:10]
        weights = inverse_volatility_weights(selected) if exposure else {}
        period_trades = []
        for item in selected if exposure else []:
            entry, exit_ = candle(item["code"], entry_date), candle(item["code"], exit_date)
            if not entry or not exit_ or float(entry["open"]) <= 0:
                continue
            trade = {
                **item,
                "signal_date": signal.isoformat(),
                "entry_date": entry_date.isoformat(),
                "exit_date": exit_date.isoformat(),
                "weight": weights.get(item["code"], 0) * exposure,
                "net_return": costs.net_return(float(entry["open"]), float(exit_["open"])),
            }
            period_trades.append(trade)
            trades.append(trade)
        portfolio_return = sum(item["weight"] * item["net_return"] for item in period_trades)
        benchmark_values = []
        for code in codes[:100]:
            entry, exit_ = candle(code, entry_date), candle(code, exit_date)
            if entry and exit_ and float(entry["open"]) > 0:
                benchmark_values.append(float(exit_["open"]) / float(entry["open"]) - 1)
        benchmark_return = sum(benchmark_values) / len(benchmark_values) if benchmark_values else 0
        equity *= 1 + portfolio_return
        curve.append(equity)
        periods.append({
            "signal_date": signal.isoformat(), "entry_date": entry_date.isoformat(),
            "exit_date": exit_date.isoformat(), "exposure": exposure,
            "market_200d_return": market_mean, "market_200d_breadth": breadth,
            "selected_codes": [item["code"] for item in period_trades],
            "portfolio_net_return": portfolio_return,
            "benchmark_return": benchmark_return,
            "excess_return": portfolio_return - benchmark_return, "equity": equity,
        })

    peak, max_drawdown = curve[0], 0.0
    for value in curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1 - value / peak)
    annual = {}
    for year in sorted({item["entry_date"][:4] for item in periods}):
        value = 1.0
        for item in periods:
            if item["entry_date"].startswith(year):
                value *= 1 + item["portfolio_net_return"]
        annual[year] = value - 1
    positive_values = [max(0, item["weight"] * item["net_return"]) for item in trades]
    positive_total = sum(positive_values)
    summary = {
        "research_id": "research-j-adaptive-momentum-v1",
        "data_status": manifest.get("status"),
        "formal_backtest_ready": manifest.get("formal_backtest_ready"),
        "completed_periods": len(periods), "trade_count": len(trades),
        "full_exposure_periods": sum(item["exposure"] == 1 for item in periods),
        "half_exposure_periods": sum(item["exposure"] == 0.5 for item in periods),
        "cash_periods": sum(item["exposure"] == 0 for item in periods),
        "cumulative_net_return": equity - 1,
        "period_endpoint_max_drawdown": max_drawdown,
        "average_period_net_return": sum(item["portfolio_net_return"] for item in periods) / len(periods),
        "average_period_excess_return": sum(item["excess_return"] for item in periods) / len(periods),
        "positive_period_rate": sum(item["portfolio_net_return"] > 0 for item in periods) / len(periods),
        "top3_positive_contribution": (
            sum(sorted(positive_values, reverse=True)[:3]) / positive_total if positive_total else 0
        ),
        "annual_returns": annual,
        "specification": {
            "rebalance": "10th trading session and month-end; next-session open",
            "universe": "point-in-time market-cap Top 300",
            "score": "50% 3m + 30% 6m + 20% 12m return; require close > MA120",
            "portfolio": "top 10, inverse 60-session volatility weights",
            "exposure": "100% if 200d breadth >=50%; 50% if >=40%; otherwise cash; mean return must be positive",
            "risk_exit": "none; rebalance and exposure control only",
        },
    }
    result = {"summary": summary, "periods": periods, "trades": trades}
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = output_dir / "adaptive_momentum_j.json", output_dir / "adaptive_momentum_j.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    result.update(json_path=str(json_path), markdown_path=str(markdown_path))
    return result


def _markdown(result: dict) -> str:
    s = result["summary"]
    pct = lambda value: f"{value * 100:.2f}%"
    lines = ["# J 중기추세·상대강도·변동성 조절 연구", "",
             "> 연구 전용이며 운영 전략과 주문을 변경하지 않습니다.", "",
             f"- 평가 구간 / 거래: {s['completed_periods']} / {s['trade_count']}",
             f"- 100%·50%·현금 구간: {s['full_exposure_periods']}·{s['half_exposure_periods']}·{s['cash_periods']}",
             f"- 누적 순수익: {pct(s['cumulative_net_return'])}",
             f"- 구간말 최대 낙폭: {pct(s['period_endpoint_max_drawdown'])}",
             f"- 평균 순수익 / 초과수익: {pct(s['average_period_net_return'])} / {pct(s['average_period_excess_return'])}",
             f"- 양(+) 구간 비율: {pct(s['positive_period_rate'])}",
             f"- 상위 3개 가중 수익 기여도: {pct(s['top3_positive_contribution'])}", "", "## 연도별 순수익", ""]
    lines.extend(f"- {year}: {pct(value)}" for year, value in s["annual_returns"].items())
    lines.extend(["", "## 제한", "", "- 월중이 아닌 반월 리밸런싱 평가금액 기준 낙폭입니다.",
                  "- 동일 종목을 계속 보유해도 매 구간 왕복비용을 적용한 보수적 계산입니다.",
                  "- 원천 자료는 정식 백테스트 승인 전의 PROVISIONAL 조정가격입니다.", ""])
    return "\n".join(lines)
