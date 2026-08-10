"""Compare frozen A/C signals at several holding horizons."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


def save_holding_horizon_report(
    active_data_path: Path,
    artifact_dirs: dict[str, Path],
    output_path: Path,
) -> dict:
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    provider = HistoricalFileMarketProvider(price_dir)
    session_values = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    session_keys = sorted(session_values)
    sessions = [datetime.fromisoformat(value) for value in session_keys]
    costs = transaction_cost_policy_from_env()
    raw = {source: {str(h): [] for h in (10, 20, 40, 60)} for source in artifact_dirs}
    price_maps = {}
    benchmark_cache = {}

    def prices(code):
        if code not in price_maps:
            price_maps[code] = {item.date: item for item in provider._candles(code)}
        return price_maps[code]

    def benchmark_return(selected_at, evaluation_date):
        cache_key = (selected_at, evaluation_date)
        if cache_key in benchmark_cache:
            return benchmark_cache[cache_key]
        eligible = [key for key in session_keys if key[:10] <= selected_at.date().isoformat()]
        cohort_key = eligible[-1] if eligible else session_keys[0]
        entry_date = next(value for value in sessions if value > selected_at)
        values = []
        for raw_code in session_values[cohort_key][:100]:
            history = prices(str(raw_code).zfill(6))
            entry, exit_ = history.get(entry_date), history.get(evaluation_date)
            if entry and exit_ and entry.close > 0:
                values.append(exit_.close / entry.close - 1)
        result = sum(values) / len(values) if values else 0.0
        benchmark_cache[cache_key] = result
        return result

    for source, artifact_dir in artifact_dirs.items():
        for path in sorted((artifact_dir / "selections").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            selected_at = datetime.fromisoformat(payload["selected_at"])
            future = [value for value in sessions if value > selected_at]
            for selection in payload.get("selections", []):
                code = str(selection["code"]).zfill(6)
                market_raw = selection.get("market")
                if not market_raw:
                    continue
                history = prices(code)
                entry_date = next((value for value in sessions if value > selected_at), None)
                entry = history.get(entry_date) if entry_date else None
                if not entry:
                    continue
                for horizon in (10, 20, 40, 60):
                    if len(future) < horizon:
                        continue
                    evaluation_date = future[horizon - 1]
                    exit_ = history.get(evaluation_date)
                    if not exit_:
                        continue
                    net = costs.net_return(entry.open, exit_.close)
                    market_return = benchmark_return(selected_at, evaluation_date)
                    raw[source][str(horizon)].append({
                        "code": code, "selected_at": selected_at.isoformat(),
                        "net_return": net, "excess_return": net - market_return,
                    })

    rows = []
    for source, horizons in raw.items():
        for horizon, trades in horizons.items():
            net = [item["net_return"] for item in trades]
            excess = [item["excess_return"] for item in trades]
            rows.append({
                "source": source, "horizon": int(horizon), "count": len(trades),
                "win_rate": sum(value > 0 for value in net) / len(net) if net else None,
                "average_net_return": sum(net) / len(net) if net else None,
                "average_excess_return": sum(excess) / len(excess) if excess else None,
                "average_without_best": (
                    sum(sorted(net, reverse=True)[1:]) / (len(net) - 1)
                    if len(net) > 1 else None
                ),
            })
    result = {"schema_version": 1, "rows": rows, "operational_orders": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.write_text(_markdown(rows), encoding="utf-8")
    result.update(markdown_path=str(output_path), json_path=str(json_path))
    return result


def _markdown(rows: list[dict]) -> str:
    pct = lambda value: "—" if value is None else f"{value * 100:.2f}%"
    lines = ["# A/C 보유기간 경로 비교", "",
             "> 동일한 선택 신호를 다음 거래일 시가에 매수하고 각 거래일 종가에 평가했습니다. 거래비용 포함, 실주문 없음.", "",
             "|전략|보유 거래일|표본|승률|평균 순수익|평균 초과수익|최고 거래 제외|",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"|{row['source']}|{row['horizon']}|{row['count']}|{pct(row['win_rate'])}|"
            f"{pct(row['average_net_return'])}|{pct(row['average_excess_return'])}|"
            f"{pct(row['average_without_best'])}|"
        )
    lines.extend(["", "- 이 표는 개별 신호의 경로 비교이며 A4/C3 슬롯 포트폴리오 누적수익과는 다릅니다.",
                  "- 60일 표본은 데이터 종료일 때문에 40일 표본보다 적을 수 있습니다.", ""])
    return "\n".join(lines)
