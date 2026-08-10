"""Unified decision table for the currently frozen research portfolio."""

from __future__ import annotations

import json
from pathlib import Path


def save_research_scorecard(research_dir: Path) -> Path:
    i = _summary(research_dir / "monthly_rs_low_vol.json")
    i2 = _summary(research_dir / "monthly_rs_defensive_i2.json")
    j = _summary(research_dir / "adaptive_momentum_j.json")
    rows = [
        {"strategy": "A breakout", "trades": 31, "cumulative": None, "drawdown": None,
         "excess": 0.0461, "positive_years": "4/6", "concentration": 0.3839,
         "decision": "OBSERVE", "reason": "positive excess, but only 31 trades and two negative years"},
        {"strategy": "C pullback", "trades": 48, "cumulative": None, "drawdown": None,
         "excess": 0.0560, "positive_years": "5/6", "concentration": 0.5778,
         "decision": "OBSERVE-HIGH-RISK", "reason": "positive excess, but best-trade dependence is material"},
        {"strategy": "A4/C3 fixed slots", "trades": 61, "cumulative": 0.9069, "drawdown": 0.1133,
         "excess": None, "positive_years": "5/6", "concentration": None,
         "decision": "KEEP-SHADOW", "reason": "best portfolio balance; forward sample remains insufficient"},
        {"strategy": "G first breakout", "trades": 60, "cumulative": 0.2682, "drawdown": 0.1759,
         "excess": -0.0231, "positive_years": "1 year", "concentration": 0.7453,
         "decision": "STOP", "reason": "negative excess and 74.53% top-three concentration"},
        _json_row("I monthly RS", i, "STOP", "negative excess and 61.94% drawdown"),
        _json_row("I-2 defensive", i2, "STOP", "negative excess; defensive rules did not control drawdown"),
        _json_row("J adaptive momentum", j, "STOP", "negative cumulative and excess returns with adequate sample"),
    ]
    lines = ["# TITAN 연구 전략 통합 판정표", "",
             "> 서로 다른 실행 주기의 결과이므로 수익률 순위표가 아니라 증거·위험 판정표입니다.", "",
             "|전략|거래|누적|MDD|평균 초과|양의 연도|상위3 기여|판정|",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    pct = lambda value: "—" if value is None else f"{value * 100:.2f}%"
    for row in rows:
        lines.append(
            f"|{row['strategy']}|{row['trades']}|{pct(row['cumulative'])}|"
            f"{pct(row['drawdown'])}|{pct(row['excess'])}|{row['positive_years']}|"
            f"{pct(row['concentration'])}|{row['decision']}|"
        )
    lines.extend(["", "## 판정 근거", ""])
    lines.extend(f"- {row['strategy']}: {row['reason']}" for row in rows)
    lines.extend(["", "## 현재 행동", "", "- A4/C3만 무주문 전진 추적을 유지합니다.",
                  "- A와 C는 독립 전략으로 승격하지 않고 A4/C3의 구성 신호로만 관찰합니다.",
                  "- G, I, I-2, J는 추가 튜닝을 중단하고 비교 기준선으로 보존합니다.",
                  "- 운영 S80과 실주문은 변경하지 않습니다.", ""])
    path = research_dir / "unified_scorecard.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["summary"]


def _json_row(name: str, summary: dict, decision: str, reason: str) -> dict:
    annual = summary["annual_returns"]
    excess = summary.get("average_monthly_excess_return", summary.get("average_period_excess_return"))
    return {
        "strategy": name, "trades": summary["trade_count"],
        "cumulative": summary["cumulative_net_return"],
        "drawdown": summary.get("monthly_endpoint_max_drawdown", summary.get("period_endpoint_max_drawdown")),
        "excess": excess,
        "positive_years": f"{sum(value > 0 for value in annual.values())}/{len(annual)}",
        "concentration": summary.get("top3_positive_trade_contribution", summary.get("top3_positive_contribution")),
        "decision": decision, "reason": reason,
    }
