"""Concentration and market-regime diagnostics for frozen challengers."""

import json
from collections import defaultdict
from pathlib import Path


def save_stress_diagnostics(
    artifact_dirs: dict[str, Path], output: Path,
) -> Path:
    sections = [
        "# TITAN Frozen Challenger Stress Diagnostics", "",
        "> Research only. Returns below are trade-level cost-adjusted averages.",
    ]
    for label, artifact_dir in artifact_dirs.items():
        trades = []
        regimes = defaultdict(lambda: [0, 0.0, 0.0])
        for path in sorted((artifact_dir / "validations").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            year = payload["selected_at"][:4]
            for trade in payload.get("trades", []):
                trades.append({**trade, "year": year})
            for context in payload.get("result", {}).get("contexts", []):
                count = int(context.get("total_count") or 0)
                if not count:
                    continue
                row = regimes[context.get("regime") or "UNKNOWN"]
                row[0] += count
                row[1] += count * float(context.get("average_return") or 0)
                row[2] += count * float(context.get("average_excess_return") or 0)
        sections += ["", f"## {label}", ""]
        by_year = defaultdict(list)
        by_code = defaultdict(list)
        for trade in trades:
            by_year[trade["year"]].append(float(trade["net_return"]))
            by_code[(trade["code"], trade.get("name") or "")].append(
                float(trade["net_return"])
            )
        sections += [
            "### Years", "",
            "| Year | Trades | Average net |", "|---|---:|---:|",
        ]
        for year, values in sorted(by_year.items()):
            sections.append(
                f"| {year} | {len(values)} | {sum(values) / len(values):.2%} |"
            )
        sections += [
            "", "### Market regimes", "",
            "| Regime | Trades | Average net | Average excess |",
            "|---|---:|---:|---:|",
        ]
        for regime, (count, net, excess) in sorted(regimes.items()):
            sections.append(
                f"| {regime} | {count} | {net / count:.2%} | {excess / count:.2%} |"
            )
        contributions = sorted(
            ((sum(values), code, name, len(values))
             for (code, name), values in by_code.items()),
            reverse=True,
        )
        positive_total = sum(max(0.0, row[0]) for row in contributions)
        top3 = sum(max(0.0, row[0]) for row in contributions[:3])
        concentration = top3 / positive_total if positive_total else 0.0
        sections += [
            "", "### Stock concentration", "",
            f"Top-3 share of positive trade-return contribution: {concentration:.2%}",
            "", "| Code | Name | Trades | Sum of net returns |",
            "|---|---|---:|---:|",
        ]
        for total, code, name, count in contributions[:10]:
            sections.append(f"| {code} | {name} | {count} | {total:.2%} |")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return output
