"""KOSPI/KOSDAQ-only monthly dual-momentum research."""

from __future__ import annotations

import csv
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


def choose_market(momentum: dict[str, float], cash_return: float = 0.0) -> str:
    """Return the strongest market only when it beats the cash hurdle."""
    if not momentum:
        return "CASH"
    market, value = max(momentum.items(), key=lambda item: (item[1], item[0]))
    return market if value > cash_return else "CASH"


def run_dual_market_momentum(
    active_data_path: Path,
    output_dir: Path,
    start_year: int = 2022,
    momentum_sessions: int = 252,
    market_cohort_limit: int = 50,
) -> dict:
    """Backtest monthly relative plus absolute momentum with next-open trades."""
    universe_dir, price_dir, active = load_active_backtest_data(active_data_path)
    ranking = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    session_keys = sorted(ranking)
    session_dates = [date.fromisoformat(key[:10]) for key in session_keys]
    index_by_date = {value: index for index, value in enumerate(session_dates)}
    market_history = _load_market_history(universe_dir)

    @lru_cache(maxsize=None)
    def stock_payload(code: str) -> dict:
        try:
            return json.loads(
                (price_dir / f"{code}.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {}

    @lru_cache(maxsize=None)
    def history(code: str) -> dict[date, dict]:
        payload = stock_payload(code)
        return {
            date.fromisoformat(str(row["date"])[:10]): row
            for row in payload.get("candles", [])
        }

    def price(code: str, value: date) -> dict | None:
        return history(str(code).zfill(6)).get(value)

    def market(code: str, value: date) -> str | None:
        for effective_from, effective_to, name in market_history.get(code, ()):
            if effective_from <= value and (
                effective_to is None or value <= effective_to
            ):
                return name
        return None

    # The final observed calendar month can be incomplete.  It is never used
    # as a completed rebalance endpoint.
    month_ends: list[date] = []
    for value in session_dates:
        if value.year < start_year:
            continue
        if not month_ends or (month_ends[-1].year, month_ends[-1].month) != (
            value.year, value.month,
        ):
            month_ends.append(value)
        else:
            month_ends[-1] = value
    if month_ends and (month_ends[-1].year, month_ends[-1].month) == (
        session_dates[-1].year, session_dates[-1].month,
    ):
        month_ends.pop()

    costs = transaction_cost_policy_from_env()

    def cohort(value: date, market_name: str, limit: int) -> list[str]:
        key = session_keys[index_by_date[value]]
        selected = []
        for raw_code in ranking[key]:
            code = str(raw_code).zfill(6)
            if market(code, value) == market_name:
                selected.append(code)
                if len(selected) >= limit:
                    break
        return selected

    def momentum_at(signal: date) -> tuple[dict[str, float], dict[str, int]]:
        signal_index = index_by_date[signal]
        if signal_index < momentum_sessions:
            return {}, {}
        old_date = session_dates[signal_index - momentum_sessions]
        old_key = session_keys[signal_index - momentum_sessions]
        values = {"KOSPI": [], "KOSDAQ": []}
        for raw_code in ranking[old_key]:
            code = str(raw_code).zfill(6)
            market_name = market(code, old_date)
            if market_name not in values:
                continue
            old, current = price(code, old_date), price(code, signal)
            if old and current and float(old["close"]) > 0:
                values[market_name].append(
                    float(current["close"]) / float(old["close"]) - 1
                )
        return (
            {
                name: sum(rows) / len(rows)
                for name, rows in values.items() if len(rows) >= 10
            },
            {name: len(rows) for name, rows in values.items()},
        )

    def portfolio_return(
        codes: list[str], entry_date: date, exit_date: date,
    ) -> tuple[float, list[dict]]:
        trades = []
        for code in codes:
            entry, exit_ = price(code, entry_date), price(code, exit_date)
            if entry and exit_ and float(entry["open"]) > 0:
                net_return = costs.net_return(
                    float(entry["open"]), float(exit_["open"])
                )
                payload = stock_payload(code)
                trades.append({
                    "code": code,
                    "name": payload.get("name", ""),
                    "entry_price": float(entry["open"]),
                    "exit_price": float(exit_["open"]),
                    "net_return": net_return,
                    "data_flags": _data_flags(payload, entry_date, exit_date),
                })
        return (
            sum(row["net_return"] for row in trades) / len(trades), trades
        ) if trades else (0.0, [])

    periods = []
    strategy_equity = benchmark_equity = 1.0
    strategy_curve = [strategy_equity]
    benchmark_curve = [benchmark_equity]
    for position in range(len(month_ends) - 1):
        signal, next_signal = month_ends[position], month_ends[position + 1]
        signal_index = index_by_date[signal]
        next_index = index_by_date[next_signal]
        if signal_index < momentum_sessions or next_index + 1 >= len(session_dates):
            continue
        entry_date = session_dates[signal_index + 1]
        exit_date = session_dates[next_index + 1]
        momentum, samples = momentum_at(signal)
        choice = choose_market(momentum)
        selected = (
            cohort(signal, choice, market_cohort_limit)
            if choice != "CASH" else []
        )
        strategy_return, holdings = portfolio_return(selected, entry_date, exit_date)
        kospi_return, benchmark_holdings = portfolio_return(
            cohort(signal, "KOSPI", market_cohort_limit), entry_date, exit_date
        )
        strategy_equity *= 1 + strategy_return
        benchmark_equity *= 1 + kospi_return
        strategy_curve.append(strategy_equity)
        benchmark_curve.append(benchmark_equity)
        periods.append({
            "signal_month": signal.strftime("%Y-%m"),
            "signal_date": signal.isoformat(),
            "entry_date": entry_date.isoformat(),
            "exit_date": exit_date.isoformat(),
            "kospi_momentum": momentum.get("KOSPI"),
            "kosdaq_momentum": momentum.get("KOSDAQ"),
            "momentum_samples": samples,
            "choice": choice,
            "held_count": len(holdings),
            "benchmark_held_count": len(benchmark_holdings),
            "holdings": holdings,
            "strategy_net_return": strategy_return,
            "kospi_benchmark_net_return": kospi_return,
            "excess_return": strategy_return - kospi_return,
            "strategy_equity": strategy_equity,
            "kospi_benchmark_equity": benchmark_equity,
        })

    def maximum_drawdown(curve):
        peak = curve[0]
        drawdown = 0.0
        for value in curve:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        return drawdown

    max_drawdown = maximum_drawdown(strategy_curve)
    benchmark_max_drawdown = maximum_drawdown(benchmark_curve)
    annual = {}
    benchmark_annual = {}
    for year in sorted({row["entry_date"][:4] for row in periods}):
        value = 1.0
        for row in periods:
            if row["entry_date"].startswith(year):
                value *= 1 + row["strategy_net_return"]
        annual[year] = value - 1
        benchmark_value = 1.0
        for row in periods:
            if row["entry_date"].startswith(year):
                benchmark_value *= 1 + row["kospi_benchmark_net_return"]
        benchmark_annual[year] = benchmark_value - 1
    summary = {
        "research_id": "kospi-kosdaq-dual-momentum-v1",
        "status": "RESEARCH_ONLY",
        "decision": "EXCLUDE_FROM_OPERATION_PENDING_OFFICIAL_INDEX_AUDIT",
        "data_status": active.get("status"),
        "formal_backtest_ready": active.get("formal_backtest_ready", False),
        "completed_months": len(periods),
        "invested_months": sum(row["choice"] != "CASH" for row in periods),
        "cash_months": sum(row["choice"] == "CASH" for row in periods),
        "kospi_months": sum(row["choice"] == "KOSPI" for row in periods),
        "kosdaq_months": sum(row["choice"] == "KOSDAQ" for row in periods),
        "cumulative_net_return": strategy_equity - 1,
        "kospi_benchmark_cumulative_net_return": benchmark_equity - 1,
        "excess_cumulative_return": strategy_equity - benchmark_equity,
        "monthly_endpoint_max_drawdown": max_drawdown,
        "kospi_benchmark_monthly_endpoint_max_drawdown": benchmark_max_drawdown,
        "positive_month_rate": (
            sum(row["strategy_net_return"] > 0 for row in periods) / len(periods)
            if periods else 0.0
        ),
        "positive_invested_month_rate": (
            sum(
                row["strategy_net_return"] > 0
                for row in periods if row["choice"] != "CASH"
            ) / sum(row["choice"] != "CASH" for row in periods)
            if any(row["choice"] != "CASH" for row in periods) else 0.0
        ),
        "annual_returns": annual,
        "kospi_benchmark_annual_returns": benchmark_annual,
        "specification": {
            "assets": "KOSPI, KOSDAQ, CASH only",
            "signal": f"{momentum_sessions}-session point-in-time equal-weight return",
            "relative_rule": "choose the stronger of KOSPI and KOSDAQ",
            "absolute_rule": "hold cash when both momentum values are <= 0",
            "cash_return": "0% (no interest credited)",
            "execution": "month-end signal; next-session open entry; next rebalance open exit",
            "portfolio": f"point-in-time top {market_cohort_limit} per chosen market, equal weight",
            "costs": "fees, tax, and entry/exit slippage included",
        },
    }
    audit = _audit_extreme_months(periods)
    result = {"summary": summary, "audit": audit, "periods": periods}
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "dual_market_momentum.json"
    markdown_path = output_dir / "dual_market_momentum.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    (output_dir / "dual_market_momentum_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "dual_market_momentum_audit.md").write_text(
        _audit_markdown(audit), encoding="utf-8"
    )
    return result


def _data_flags(payload: dict, entry_date: date, exit_date: date) -> list[dict]:
    flags = []
    for event in payload.get("adjustment_events", []):
        event_date = date.fromisoformat(str(event["date"])[:10])
        if entry_date <= event_date <= exit_date:
            flags.append({"type": "ADJUSTMENT_EVENT", "date": event_date.isoformat()})
    for event in payload.get("unresolved_large_jumps", []):
        raw_date = event.get("date") or event.get("start")
        if raw_date:
            event_date = date.fromisoformat(str(raw_date)[:10])
            if entry_date <= event_date <= exit_date:
                flags.append({"type": "UNRESOLVED_LARGE_JUMP", "date": event_date.isoformat()})
    for event in payload.get("quality_quarantines", []):
        start = date.fromisoformat(str(event.get("start", event.get("date")))[:10])
        end_raw = event.get("end", event.get("start", event.get("date")))
        end = date.fromisoformat(str(end_raw)[:10])
        if start <= exit_date and end >= entry_date:
            flags.append({"type": "QUALITY_QUARANTINE", "date": start.isoformat()})
    return flags


def _audit_extreme_months(periods: list[dict], threshold: float = .10) -> dict:
    months = []
    for period in periods:
        if abs(period["strategy_net_return"]) < threshold:
            continue
        holdings = period.get("holdings", [])
        ordered = sorted(holdings, key=lambda row: row["net_return"], reverse=True)
        absolute_total = sum(abs(row["net_return"]) for row in holdings)
        flagged = [row for row in holdings if row.get("data_flags")]
        months.append({
            "signal_month": period["signal_month"],
            "choice": period["choice"],
            "entry_date": period["entry_date"],
            "exit_date": period["exit_date"],
            "portfolio_net_return": period["strategy_net_return"],
            "holding_count": len(holdings),
            "best": ordered[:5],
            "worst": list(reversed(ordered[-5:])),
            "flagged_holdings": flagged,
            "top3_absolute_contribution_share": (
                sum(abs(row["net_return"]) for row in sorted(
                    holdings, key=lambda row: abs(row["net_return"]), reverse=True
                )[:3]) / absolute_total if absolute_total else 0.0
            ),
        })
    return {
        "status": "DATA_REVIEW_REQUIRED" if any(
            month["flagged_holdings"] for month in months
        ) else "NO_STORED_DATA_FLAGS_IN_EXTREME_MONTHS",
        "threshold": threshold,
        "extreme_month_count": len(months),
        "flagged_holding_count": sum(
            len(month["flagged_holdings"]) for month in months
        ),
        "months": months,
    }


def _audit_markdown(audit: dict) -> str:
    pct = lambda value: f"{value:.2%}"
    lines = [
        "# 코스피·코스닥 듀얼 모멘텀 극단 월 감사", "",
        "> 매개변수는 변경하지 않고 월 순수익 절대값 10% 이상인 기간의 종목 기여도와 저장된 데이터 경고만 검사했습니다.", "",
        f"- 극단 월: {audit['extreme_month_count']}개",
        f"- 데이터 경고 보유 건: {audit['flagged_holding_count']}건",
        f"- 상태: {audit['status']}", "",
    ]
    for month in audit["months"]:
        lines += [
            f"## {month['signal_month']} · {month['choice']} · {pct(month['portfolio_net_return'])}", "",
            f"- 기간: {month['entry_date']} ~ {month['exit_date']}",
            f"- 상위 3개 절대 기여 집중도: {pct(month['top3_absolute_contribution_share'])}",
            f"- 데이터 경고: {len(month['flagged_holdings'])}건", "",
            "|구분|코드|종목|순수익|경고|", "|---|---:|---|---:|---|",
        ]
        for label, rows in (("상위", month["best"]), ("하위", month["worst"])):
            for row in rows:
                flags = ", ".join(flag["type"] for flag in row["data_flags"]) or "—"
                lines.append(
                    f"|{label}|{row['code']}|{row['name']}|{pct(row['net_return'])}|{flags}|"
                )
        lines.append("")
    lines += [
        "## 해석 제한", "",
        "- 저장된 경고가 없다는 사실은 공식 수정주가 검증이 끝났다는 의미가 아닙니다.",
        "- 종목 50개의 동일가중 평균이므로 개별 종목의 포트폴리오 기여도는 종목 순수익의 1/50입니다.",
        "- 공식 지수와 비교하기 전까지 현재 구현은 운영 후보에서 제외합니다.", "",
    ]
    return "\n".join(lines)


def _load_market_history(universe_dir: Path) -> dict[str, list[tuple]]:
    result: dict[str, list[tuple]] = {}
    for market_name, filename in (("KOSPI", "kospi.csv"), ("KOSDAQ", "kosdaq.csv")):
        with (universe_dir / filename).open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = str(row["code"]).zfill(6)
                start = date.fromisoformat(row["effective_from"])
                end = date.fromisoformat(row["effective_to"]) if row["effective_to"] else None
                result.setdefault(code, []).append((start, end, market_name))
    return result


def _markdown(result: dict) -> str:
    summary = result["summary"]
    pct = lambda value: "—" if value is None else f"{value:.2%}"
    lines = [
        "# 코스피·코스닥 월간 듀얼 모멘텀 연구", "",
        "> 연구 전용이며 S80, A4/C3 및 실제 주문은 변경하지 않습니다.", "",
        f"- 판정: {summary['decision']}",
        f"- 완료 월: {summary['completed_months']}",
        f"- 코스피 / 코스닥 / 현금 선택: {summary['kospi_months']} / {summary['kosdaq_months']} / {summary['cash_months']}",
        f"- 누적 순수익: {pct(summary['cumulative_net_return'])}",
        f"- 코스피 대용 기준선 누적: {pct(summary['kospi_benchmark_cumulative_net_return'])}",
        f"- 월말 기준 최대 낙폭: {pct(summary['monthly_endpoint_max_drawdown'])}",
        f"- 코스피 대용 기준선 최대 낙폭: {pct(summary['kospi_benchmark_monthly_endpoint_max_drawdown'])}",
        f"- 전체 / 투자 월 양(+) 비율: {pct(summary['positive_month_rate'])} / {pct(summary['positive_invested_month_rate'])}", "",
        "## 연도별 순수익", "",
    ]
    lines.extend(
        f"- {year}: 전략 {pct(value)} / 코스피 기준선 {pct(summary['kospi_benchmark_annual_returns'][year])}"
        for year, value in summary["annual_returns"].items()
    )
    lines += [
        "", "## 월별 결과", "",
        "|신호월|선택|코스피 모멘텀|코스닥 모멘텀|순수익|코스피 기준선|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["periods"]:
        lines.append(
            f"|{row['signal_month']}|{row['choice']}|{pct(row['kospi_momentum'])}|"
            f"{pct(row['kosdaq_momentum'])}|{pct(row['strategy_net_return'])}|"
            f"{pct(row['kospi_benchmark_net_return'])}|"
        )
    lines += [
        "", "## 제한", "",
        "- 공식 코스피·코스닥 지수가 아니라 당시 시가총액 상위 구성 종목의 동일가중 대용치입니다.",
        "- 현금 이자는 0%로 계산했습니다.",
        "- 월중 낙폭이 아닌 월말 평가금액 기준 낙폭입니다.",
        "- 원천 가격의 공식 수정주가가 없어 현재 데이터는 정식 백테스트 승인 전 상태입니다.", "",
    ]
    return "\n".join(lines)
