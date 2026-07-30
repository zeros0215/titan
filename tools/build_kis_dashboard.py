import json
from datetime import datetime
from pathlib import Path

from pilot.history import PilotHistoryRepository, PilotReadinessEvaluator


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "kis_v1_1"
MANUAL_OUTPUT = ROOT / "output" / "kis_manual_tests"
SECTOR_LAGGARD_OUTPUT = ROOT / "output" / "sector_laggard"
TEMPLATE = ROOT / "dashboard" / "index.template.html"
SITE_INDEX = ROOT / "dashboard" / "index.html"
LOCAL_INDEX = OUTPUT / "dashboard.html"


def main() -> None:
    official_runs = PilotHistoryRepository(OUTPUT / "runs").load_all()
    manual_runs = PilotHistoryRepository(MANUAL_OUTPUT / "runs").load_all()
    readiness = PilotReadinessEvaluator(5).evaluate(official_runs)
    for item in official_runs:
        item.pop("_file_mtime", None)
        item["run_type"] = "OFFICIAL"
    for item in manual_runs:
        item.pop("_file_mtime", None)
        item["run_type"] = "MANUAL"
    runs = sorted(
        official_runs + manual_runs,
        key=lambda item: (item.get("as_of", ""), item.get("run_type", "")),
    )
    historical_trades = [
        trade
        for run in runs
        if run.get("source") == "LOCAL_KRX"
        for trade in run.get("trades", [])
    ]
    completed_trades = len(historical_trades)
    winning_trades = sum(bool(trade.get("win")) for trade in historical_trades)
    baseline_runs = [
        run
        for run in runs
        if run.get("strategy_version", "V1.1") == "V1.1"
    ]
    sector_path = SECTOR_LAGGARD_OUTPUT / "sector_laggard_backtest.json"
    sector_laggard = (
        json.loads(sector_path.read_text(encoding="utf-8"))
        if sector_path.exists()
        else None
    )
    if sector_laggard is not None:
        sector_laggard.pop("trades", None)
    data = {
        "generated_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "readiness": {
            "status": readiness.status,
            "observed_days": readiness.observed_days,
            "passing_days": readiness.passing_days,
            "consecutive_passing_days": readiness.consecutive_passing_days,
            "reasons": readiness.reasons,
        },
        "latest": baseline_runs[-1] if baseline_runs else None,
        "runs": runs,
        "historical": {
            "trades": historical_trades,
            "total": completed_trades,
            "wins": winning_trades,
            "win_rate": (
                winning_trades / completed_trades
                if completed_trades
                else None
            ),
            "average_net_return": (
                sum(
                    float(trade["net_return"])
                    for trade in historical_trades
                ) / completed_trades
                if completed_trades
                else None
            ),
            "holding_sessions": 1,
        },
        "sector_laggard": sector_laggard,
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "__TITAN_DATA__",
        json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    )
    SITE_INDEX.write_text(html, encoding="utf-8")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    LOCAL_INDEX.write_text(html, encoding="utf-8")
    print(LOCAL_INDEX)


if __name__ == "__main__":
    main()
