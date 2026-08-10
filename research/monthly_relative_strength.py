"""Point-in-time monthly relative-strength and low-volatility research."""

from __future__ import annotations

import json
import math
import statistics
from datetime import date
from functools import lru_cache
from pathlib import Path

from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


def select_low_volatility(
    rows: list[dict], top_fraction: float = 0.20, limit: int = 5,
) -> list[dict]:
    """Keep the strongest momentum quintile, then prefer lower volatility."""
    if not 0 < top_fraction <= 1:
        raise ValueError("top_fraction must be between zero and one")
    if limit <= 0:
        raise ValueError("limit must be positive")
    momentum_pool = sorted(
        rows, key=lambda row: (-row["momentum"], row["code"]),
    )[:max(1, math.ceil(len(rows) * top_fraction))]
    return sorted(
        momentum_pool,
        key=lambda row: (row["volatility"], -row["momentum"], row["code"]),
    )[:limit]


def run_monthly_relative_strength(
    active_data_path: Path,
    output_dir: Path,
    start_year: int = 2021,
    end_date: date | None = None,
    defensive: bool = False,
) -> dict:
    """Backtest research strategy I with next-session, open-to-open execution."""
    _, price_dir, data_manifest = load_active_backtest_data(active_data_path)
    ranking = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    session_keys = sorted(ranking)
    session_dates = [date.fromisoformat(key[:10]) for key in session_keys]
    index_by_date = {value: index for index, value in enumerate(session_dates)}
    requested_end = end_date or session_dates[-1]

    month_ends: list[date] = []
    for value in session_dates:
        if value.year < start_year or value > requested_end:
            continue
        if not month_ends or (month_ends[-1].year, month_ends[-1].month) != (
            value.year, value.month,
        ):
            month_ends.append(value)
        else:
            month_ends[-1] = value

    @lru_cache(maxsize=None)
    def history(code: str) -> dict[date, dict]:
        path = price_dir / f"{code}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            date.fromisoformat(str(row["date"])[:10]): row
            for row in payload.get("candles", [])
        }

    def row(code: str, session: date) -> dict | None:
        return history(str(code).zfill(6)).get(session)

    costs = transaction_cost_policy_from_env()
    periods: list[dict] = []
    all_trades: list[dict] = []
    equity = 1.0
    equity_curve = [equity]
    for position in range(len(month_ends) - 1):
        signal = month_ends[position]
        next_signal = month_ends[position + 1]
        signal_index = index_by_date[signal]
        next_signal_index = index_by_date[next_signal]
        if signal_index < 200 or next_signal_index + 1 >= len(session_dates):
            continue
        entry_date = session_dates[signal_index + 1]
        exit_date = session_dates[next_signal_index + 1]
        codes = [str(code).zfill(6) for code in ranking[session_keys[signal_index]]]

        market_returns = []
        market_returns_60 = []
        for code in codes[:100]:
            current, old = row(code, signal), row(code, session_dates[signal_index - 200])
            if current and old and float(old["close"]) > 0:
                market_returns.append(float(current["close"]) / float(old["close"]) - 1)
            short_old = row(code, session_dates[signal_index - 60])
            if current and short_old and float(short_old["close"]) > 0:
                market_returns_60.append(
                    float(current["close"]) / float(short_old["close"]) - 1
                )
        market_trend = (
            sum(market_returns) / len(market_returns) if market_returns else -1.0
        )
        market_trend_60 = (
            sum(market_returns_60) / len(market_returns_60)
            if market_returns_60 else -1.0
        )
        market_breadth_200 = (
            sum(value > 0 for value in market_returns) / len(market_returns)
            if market_returns else 0.0
        )

        scored = []
        for code in codes:
            recent = row(code, session_dates[signal_index - 21])
            old = row(code, session_dates[signal_index - 126])
            vol_rows = [
                row(code, session_dates[offset])
                for offset in range(signal_index - 60, signal_index + 1)
            ]
            if not recent or not old or any(item is None for item in vol_rows):
                continue
            old_close = float(old["close"])
            closes = [float(item["close"]) for item in vol_rows if item]
            if old_close <= 0 or any(value <= 0 for value in closes):
                continue
            returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
            scored.append({
                "code": code,
                "momentum": float(recent["close"]) / old_close - 1,
                "volatility": statistics.pstdev(returns),
            })

        gate_open = market_trend > 0
        if defensive:
            gate_open = (
                gate_open and market_trend_60 > 0 and market_breadth_200 >= 0.55
            )
        selected = select_low_volatility(scored) if gate_open and scored else []
        trades = []
        benchmark_returns = []
        for code in codes[:100]:
            entry, exit_ = row(code, entry_date), row(code, exit_date)
            if entry and exit_ and float(entry["open"]) > 0:
                benchmark_returns.append(float(exit_["open"]) / float(entry["open"]) - 1)
        for candidate in selected:
            entry, exit_ = row(candidate["code"], entry_date), row(candidate["code"], exit_date)
            if not entry or not exit_ or float(entry["open"]) <= 0:
                continue
            actual_exit_date = exit_date
            actual_exit = exit_
            exit_reason = "MONTHLY_REBALANCE"
            if defensive:
                for session_index in range(signal_index + 1, next_signal_index + 1):
                    check_date = session_dates[session_index]
                    check = row(candidate["code"], check_date)
                    if (
                        check
                        and float(check["close"]) / float(entry["open"]) - 1 <= -0.10
                        and session_index + 1 < len(session_dates)
                    ):
                        next_open_date = session_dates[session_index + 1]
                        next_open = row(candidate["code"], next_open_date)
                        if next_open:
                            actual_exit_date = next_open_date
                            actual_exit = next_open
                            exit_reason = "CLOSE_STOP_NEXT_OPEN"
                            break
            net_return = costs.net_return(
                float(entry["open"]), float(actual_exit["open"]),
            )
            trade = {
                **candidate,
                "signal_date": signal.isoformat(),
                "entry_date": entry_date.isoformat(),
                "exit_date": actual_exit_date.isoformat(),
                "entry_price": float(entry["open"]),
                "exit_price": float(actual_exit["open"]),
                "exit_reason": exit_reason,
                "net_return": net_return,
            }
            trades.append(trade)
            all_trades.append(trade)
        portfolio_return = (
            sum(item["net_return"] for item in trades) / len(trades) if trades else 0.0
        )
        benchmark_return = (
            sum(benchmark_returns) / len(benchmark_returns)
            if benchmark_returns else 0.0
        )
        equity *= 1 + portfolio_return
        equity_curve.append(equity)
        periods.append({
            "month": signal.strftime("%Y-%m"),
            "signal_date": signal.isoformat(),
            "entry_date": entry_date.isoformat(),
            "exit_date": exit_date.isoformat(),
            "market_200d_return": market_trend,
            "market_60d_return": market_trend_60,
            "market_200d_breadth": market_breadth_200,
            "state": "INVESTED" if trades else "CASH",
            "eligible_count": len(scored),
            "selected_codes": [item["code"] for item in trades],
            "portfolio_net_return": portfolio_return,
            "benchmark_return": benchmark_return,
            "excess_return": portfolio_return - benchmark_return,
            "equity": equity,
        })

    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1 - value / peak)
    annual = {}
    for year in sorted({item["entry_date"][:4] for item in periods}):
        value = 1.0
        for item in periods:
            if item["entry_date"].startswith(year):
                value *= 1 + item["portfolio_net_return"]
        annual[year] = value - 1
    positives = [max(0.0, item["net_return"]) for item in all_trades]
    positive_total = sum(positives)
    top3_contribution = (
        sum(sorted(positives, reverse=True)[:3]) / positive_total
        if positive_total else 0.0
    )
    summary = {
        "research_id": (
            "research-i2-monthly-rs-defensive-v1"
            if defensive else "research-i-monthly-rs-low-vol-v1"
        ),
        "data_status": data_manifest.get("status"),
        "formal_backtest_ready": data_manifest.get("formal_backtest_ready"),
        "start_year": start_year,
        "coverage_end": requested_end.isoformat(),
        "completed_months": len(periods),
        "invested_months": sum(item["state"] == "INVESTED" for item in periods),
        "cash_months": sum(item["state"] == "CASH" for item in periods),
        "trade_count": len(all_trades),
        "cumulative_net_return": equity - 1,
        "monthly_endpoint_max_drawdown": max_drawdown,
        "average_monthly_net_return": (
            sum(item["portfolio_net_return"] for item in periods) / len(periods)
            if periods else 0.0
        ),
        "average_monthly_excess_return": (
            sum(item["excess_return"] for item in periods) / len(periods)
            if periods else 0.0
        ),
        "positive_month_rate": (
            sum(item["portfolio_net_return"] > 0 for item in periods) / len(periods)
            if periods else 0.0
        ),
        "top3_positive_trade_contribution": top3_contribution,
        "stop_exit_count": sum(
            item.get("exit_reason") == "CLOSE_STOP_NEXT_OPEN" for item in all_trades
        ),
        "annual_returns": annual,
        "specification": {
            "universe": "point-in-time market-cap Top 500",
            "momentum": "126-session return excluding latest 21 sessions",
            "selection": "momentum top 20%, then lowest 60-session volatility 5",
            "market_gate": (
                "top-100 60d and 200d mean returns > 0; 200d breadth >= 55%"
                if defensive else "top-100 equal-weight 200-session return > 0"
            ),
            "risk_exit": (
                "close <= -10% from entry; sell next-session open"
                if defensive else "monthly rebalance only"
            ),
            "execution": "next-session open; next monthly rebalance open exit",
            "weighting": "equal weight",
            "industry_cap": "not applied because complete point-in-time industry data is unavailable",
        },
    }
    result = {"summary": summary, "periods": periods, "trades": all_trades}
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = "monthly_rs_defensive_i2" if defensive else "monthly_rs_low_vol"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    result["json_path"] = str(json_path)
    result["markdown_path"] = str(markdown_path)
    return result


def _markdown(result: dict) -> str:
    summary = result["summary"]
    pct = lambda value: f"{value * 100:.2f}%"
    lines = [
        (
            "# I-2 월간 상대강도·저변동 방어형 연구"
            if summary["research_id"].startswith("research-i2")
            else "# I 월간 상대강도·저변동 연구"
        ), "",
        "> 연구 전용 결과이며 운영 전략과 실주문은 변경하지 않습니다.", "",
        f"- 완료 월: {summary['completed_months']} (투자 {summary['invested_months']}, 현금 {summary['cash_months']})",
        f"- 거래 수: {summary['trade_count']}",
        f"- 누적 순수익: {pct(summary['cumulative_net_return'])}",
        f"- 월말 기준 최대 낙폭: {pct(summary['monthly_endpoint_max_drawdown'])}",
        f"- 월평균 순수익 / 초과수익: {pct(summary['average_monthly_net_return'])} / {pct(summary['average_monthly_excess_return'])}",
        f"- 양(+)의 월 비율: {pct(summary['positive_month_rate'])}",
        f"- 상위 3개 수익 거래 기여도: {pct(summary['top3_positive_trade_contribution'])}", "",
        f"- 손절 매도: {summary['stop_exit_count']}건", "",
        "## 연도별 순수익", "",
    ]
    lines.extend(f"- {year}: {pct(value)}" for year, value in summary["annual_returns"].items())
    lines.extend(["", "## 월별 결과", "", "|월|상태|종목 수|순수익|초과수익|", "|---|---:|---:|---:|---:|"])
    for item in result["periods"]:
        lines.append(
            f"|{item['month']}|{item['state']}|{len(item['selected_codes'])}|"
            f"{pct(item['portfolio_net_return'])}|{pct(item['excess_return'])}|"
        )
    lines.extend(["", "## 제한", "", "- 업종의 시점별 전체 이력이 없어 업종당 1종목 제한은 적용하지 않았습니다.", "- 월중 낙폭이 아닌 월말 평가금액 기준 낙폭입니다.", "- 원천 가격은 조정가격 추론 자료이므로 정식 백테스트 승인 전 검토가 필요합니다.", ""])
    return "\n".join(lines)
