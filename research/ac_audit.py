"""Evidence-oriented audit package for the frozen A4/C3 research portfolio."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from research.portfolio_evaluation import evaluate_mixed_fixed_slot_portfolio
from release.backtest_data import load_active_backtest_data


def save_ac_audit(
    active_data_path: Path,
    artifact_dirs: dict[str, Path],
    shadow_state_path: Path,
    weekday_summary_path: Path,
    output_dir: Path,
) -> dict:
    _, price_dir, active = load_active_backtest_data(active_data_path)
    price_manifest = _json(price_dir / "price_history_manifest.json")
    rankings = _json(price_dir / "market_cap_top500.json")["sessions"]
    quarantines = _json(price_dir / "quality_quarantines.json")
    freeze_path = output_dir / "research_ac43_portfolio_v1.json"
    freeze = _json(freeze_path)

    base = evaluate_mixed_fixed_slot_portfolio(artifact_dirs, {"A": 4, "C": 3})
    slots = {
        f"A{a}/C{7-a}": evaluate_mixed_fixed_slot_portfolio(
            artifact_dirs, {"A": a, "C": 7 - a},
        )
        for a in (3, 4, 5)
    }
    costs = {
        f"{multiple:.1f}x": evaluate_mixed_fixed_slot_portfolio(
            artifact_dirs, {"A": 4, "C": 3}, cost_multiplier=multiple,
        )
        for multiple in (1.0, 1.5, 2.0)
    }
    exclusions = {
        f"top{count}": evaluate_mixed_fixed_slot_portfolio(
            artifact_dirs, {"A": 4, "C": 3}, exclude_top_trades=count,
        )
        for count in (1, 3, 5)
    }
    mechanics = _mechanics_audit(artifact_dirs, rankings, quarantines, price_dir)
    weekday = _json(weekday_summary_path) if weekday_summary_path.exists() else {"rows": []}
    shadow = _json(shadow_state_path) if shadow_state_path.exists() else {"summary": {}}
    closed_forward = int(shadow.get("summary", {}).get("closed", 0))

    checks = [
        _check("Frozen specification", bool(freeze.get("specification_sha256")), "PASS", "freeze hash exists"),
        _check(
            "Official adjusted prices",
            price_manifest.get("formal_backtest_ready") is True,
            "FAIL",
            price_manifest.get("formal_blocker") or "formal data approval missing",
        ),
        _check("Point-in-time membership", mechanics["membership_violations"] == 0, "FAIL",
               f"violations={mechanics['membership_violations']}"),
        _check("Forward-date ordering", mechanics["date_order_violations"] == 0, "FAIL",
               f"violations={mechanics['date_order_violations']}"),
        _check("Next-session entry price", mechanics["entry_price_mismatches"] == 0, "FAIL",
               f"mismatches={mechanics['entry_price_mismatches']}"),
        _check("Quarantine overlap", mechanics["quarantine_overlaps"] == 0, "FAIL",
               f"overlaps={mechanics['quarantine_overlaps']}"),
        _check("2x cost survival", costs["2.0x"]["cumulative_return"] > 0, "FAIL",
               f"cumulative={costs['2.0x']['cumulative_return']:.2%}"),
        _check("Slot sensitivity", all(row["cumulative_return"] > 0 for row in slots.values()), "FAIL",
               "all A3/C4, A4/C3, A5/C2 positive"),
        _check("Top-5 exclusion", exclusions["top5"]["cumulative_return"] > 0, "FAIL",
               f"cumulative={exclusions['top5']['cumulative_return']:.2%}"),
        _check("Weekday robustness", _weekday_pass(weekday), "FAIL",
               "requires at least 4 weekdays positive after excluding best trade"),
        _check("Forward sample 30", closed_forward >= 30, "WATCH",
               f"closed={closed_forward}/30"),
        _check("Promotion sample 100", closed_forward >= 100, "FAIL",
               f"closed={closed_forward}/100"),
        _check("Historical MDD under 15%", base["maximum_drawdown"] < 0.15, "FAIL",
               f"MDD={base['maximum_drawdown']:.2%}"),
    ]
    fail_count = sum(item["status"] == "FAIL" for item in checks)
    watch_count = sum(item["status"] == "WATCH" for item in checks)
    result = {
        "schema_version": 1,
        "program_version": freeze.get("program_version"),
        "data_status": active.get("status"),
        "verdict": "NOT_ELIGIBLE" if fail_count else ("WATCH" if watch_count else "PASS"),
        "checks": checks,
        "base": base,
        "slot_sensitivity": slots,
        "cost_sensitivity": costs,
        "exclusion_sensitivity": exclusions,
        "mechanics": mechanics,
        "forward_closed": closed_forward,
        "operational_orders": 0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = output_dir / "ac43_audit.json", output_dir / "ac43_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    result.update(json_path=str(json_path), markdown_path=str(markdown_path))
    return result


def _mechanics_audit(artifact_dirs, rankings, quarantines, price_dir):
    ranking_keys = sorted(rankings)
    membership = ordering = mismatch = overlaps = trades = 0
    quarantine_by_code = {}
    for item in quarantines:
        quarantine_by_code.setdefault(str(item["code"]).zfill(6), []).append(item)
    for artifact_dir in artifact_dirs.values():
        market_data = {}
        for path in (artifact_dir / "validations").glob("*.json"):
            payload = _json(path)
            selected = datetime.fromisoformat(payload["selected_at"])
            evaluated = datetime.fromisoformat(payload["evaluation_date"])
            if evaluated <= selected or int(payload.get("holding_days", 0)) != 40:
                ordering += 1
            eligible_keys = [key for key in ranking_keys if key[:10] <= selected.date().isoformat()]
            cohort = set(rankings[eligible_keys[-1]]) if eligible_keys else set()
            for trade in payload.get("trades", []):
                trades += 1
                code = str(trade["code"]).zfill(6)
                if code not in market_data:
                    price_payload = _json(price_dir / f"{code}.json")
                    market_data[code] = {
                        str(row["date"])[:10]: row
                        for row in price_payload.get("candles", [])
                    }
                if code not in cohort:
                    membership += 1
                future_dates = sorted(
                    value for value in market_data[code]
                    if value > selected.date().isoformat()
                )
                candle = market_data[code].get(future_dates[0], {}) if future_dates else {}
                if not candle or abs(float(candle.get("open", -1)) - float(trade["selection_price"])) > 1e-6:
                    mismatch += 1
                for interval in quarantine_by_code.get(code, []):
                    if interval["start"][:10] <= evaluated.date().isoformat() and interval["end"][:10] >= selected.date().isoformat():
                        overlaps += 1
                        break
    return {
        "trade_count": trades, "membership_violations": membership,
        "date_order_violations": ordering, "entry_price_mismatches": mismatch,
        "quarantine_overlaps": overlaps,
    }


def _weekday_pass(payload):
    values = [row.get("average_without_best") for row in payload.get("rows", [])]
    return sum(value is not None and value > 0 for value in values) >= 4


def _check(name, passed, failure_status, evidence):
    return {"name": name, "status": "PASS" if passed else failure_status, "evidence": evidence}


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _markdown(result):
    pct = lambda value: f"{value * 100:.2f}%"
    lines = ["# A4/C3 검증 감사 패키지", "",
             f"> 최종 판정: **{result['verdict']}** · 운영 변경 없음 · 실주문 0", "",
             "## 감사 게이트", "", "|항목|판정|근거|", "|---|---:|---|"]
    lines.extend(f"|{row['name']}|{row['status']}|{row['evidence']}|" for row in result["checks"])
    lines.extend(["", "## 슬롯 민감도", "", "|배분|누적|MDD|거래|", "|---|---:|---:|---:|"])
    for name, row in result["slot_sensitivity"].items():
        lines.append(f"|{name}|{pct(row['cumulative_return'])}|{pct(row['maximum_drawdown'])}|{row['accepted_trades']}|")
    lines.extend(["", "## 비용 스트레스", "", "|비용|누적|MDD|", "|---|---:|---:|"])
    for name, row in result["cost_sensitivity"].items():
        lines.append(f"|{name}|{pct(row['cumulative_return'])}|{pct(row['maximum_drawdown'])}|")
    lines.extend(["", "## 최고 수익 거래 제외", "", "|제외|누적|MDD|", "|---|---:|---:|"])
    for name, row in result["exclusion_sensitivity"].items():
        lines.append(f"|{name}|{pct(row['cumulative_return'])}|{pct(row['maximum_drawdown'])}|")
    lines.extend(["", "## 결론", "",
                  "- FAIL 항목이 하나라도 있으면 실전 승격 불가입니다.",
                  "- 최소 30건은 중간 검토 기준이고 100건이 정식 승격 심사 기준입니다.",
                  "- 결과를 본 뒤 이 게이트의 임계값을 변경하지 않습니다.", ""])
    return "\n".join(lines)
