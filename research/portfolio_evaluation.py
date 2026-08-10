"""Research-only fixed-slot portfolio replay for walk-forward artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path


@dataclass
class _Position:
    source: str
    code: str
    entry: datetime
    exit: datetime
    entry_price: float
    allocation: float
    net_return: float


def evaluate_fixed_slot_portfolio(
    artifact_dir: Path,
    max_positions: int = 7,
    exclude_years: tuple[int, ...] = (),
    exclude_top_trades: int = 0,
) -> dict:
    """Replay non-overlapping positions; only free slots accept new signals."""
    if max_positions <= 0:
        raise ValueError("max_positions must be positive")
    signals = _load_signals(artifact_dir / "validations", artifact_dir.name)
    signals = [
        row for row in signals if row["entry"].year not in exclude_years
    ]
    if exclude_top_trades:
        excluded = {
            id(row) for row in sorted(
                signals, key=lambda row: row["net_return"], reverse=True,
            )[:exclude_top_trades]
        }
        signals = [row for row in signals if id(row) not in excluded]
    prices = _load_prices(artifact_dir / "market_data")
    return _replay(signals, prices, max_positions)


def evaluate_mixed_fixed_slot_portfolio(
    artifact_dirs: dict[str, Path],
    slot_limits: dict[str, int],
    cost_multiplier: float = 1.0,
    exclude_top_trades: int = 0,
) -> dict:
    """Replay multiple frozen strategies with fixed per-strategy slots."""
    if set(artifact_dirs) != set(slot_limits):
        raise ValueError("artifact_dirs and slot_limits must have identical keys")
    if any(value <= 0 for value in slot_limits.values()):
        raise ValueError("every strategy must have at least one slot")
    signals = []
    prices = {}
    for source, artifact_dir in artifact_dirs.items():
        signals.extend(_load_signals(
            artifact_dir / "validations", source, cost_multiplier,
        ))
        for code, rows in _load_prices(artifact_dir / "market_data").items():
            prices.setdefault(code, {}).update(rows)
    if exclude_top_trades:
        excluded = {
            id(row) for row in sorted(
                signals, key=lambda row: row["net_return"], reverse=True,
            )[:exclude_top_trades]
        }
        signals = [row for row in signals if id(row) not in excluded]
    result = _replay(signals, prices, sum(slot_limits.values()), slot_limits)
    result["slot_limits"] = dict(slot_limits)
    return result


def _replay(signals, prices, max_positions, slot_limits=None) -> dict:
    if not signals:
        raise ValueError("no trade-level validation data found")

    by_date: dict[datetime, list[dict]] = {}
    for signal in signals:
        by_date.setdefault(signal["entry"], []).append(signal)
    first_entry = min(row["entry"] for row in signals)
    last_exit = max(row["exit"] for row in signals)
    dates = sorted({
        date for rows in prices.values() for date in rows
        if first_entry <= date <= last_exit
    })
    cash = equity = peak = 1.0
    maximum_drawdown = 0.0
    active: list[_Position] = []
    curve = []
    accepted = duplicate_skips = capacity_skips = 0

    for current in dates:
        remaining = []
        for position in active:
            if position.exit <= current:
                cash += position.allocation * (1.0 + position.net_return)
            else:
                remaining.append(position)
        active = remaining

        for signal in sorted(by_date.get(current, []), key=lambda row: row["rank"]):
            if any(item.code == signal["code"] for item in active):
                duplicate_skips += 1
                continue
            if len(active) >= max_positions:
                capacity_skips += 1
                continue
            if slot_limits is not None and sum(
                item.source == signal["source"] for item in active
            ) >= slot_limits[signal["source"]]:
                capacity_skips += 1
                continue
            free_slots = max_positions - len(active)
            allocation = min(cash / free_slots, 1.0 / max_positions)
            if allocation <= 0:
                capacity_skips += 1
                continue
            cash -= allocation
            active.append(_Position(
                source=signal["source"], code=signal["code"],
                entry=current, exit=signal["exit"],
                entry_price=signal["selection_price"], allocation=allocation,
                net_return=signal["net_return"],
            ))
            accepted += 1

        marked = cash
        for position in active:
            close = _price_on_or_before(prices.get(position.code, {}), current)
            marked += position.allocation * (
                close / position.entry_price if close is not None else 1.0
            )
        equity = marked
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, 1.0 - equity / peak)
        curve.append((current, equity))

    annual = {}
    prior = 1.0
    for year in sorted({date.year for date, _ in curve}):
        ending = [value for date, value in curve if date.year == year][-1]
        annual[str(year)] = ending / prior - 1.0
        prior = ending
    return {
        "initial_equity": 1.0,
        "final_equity": equity,
        "cumulative_return": equity - 1.0,
        "maximum_drawdown": maximum_drawdown,
        "annual_returns": annual,
        "accepted_trades": accepted,
        "duplicate_skips": duplicate_skips,
        "capacity_skips": capacity_skips,
        "max_positions": max_positions,
        "policy": "fixed slots; no duplicate code; enter only when a slot is free",
    }


def save_portfolio_report(artifact_dirs: list[Path], output: Path) -> Path:
    rows = []
    for artifact_dir in artifact_dirs:
        try:
            result = evaluate_fixed_slot_portfolio(artifact_dir)
        except ValueError:
            result = None
        rows.append((artifact_dir.name, result))
    lines = [
        "# TITAN Research Fixed-Slot Portfolio", "",
        "> Research only. Seven equal-capital slots; no overlapping position in the same code.",
        "", "| Strategy | Accepted | Duplicate skips | Capacity skips | Cumulative | Max drawdown | Annual returns |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in rows:
        if row is None:
            lines.append(f"| {name} | 0 | 0 | 0 | — | — | no trades |")
            continue
        annual = ", ".join(
            f"{year} {value:.2%}" for year, value in row["annual_returns"].items()
        )
        lines.append(
            f"| {name} | {row['accepted_trades']} | {row['duplicate_skips']} | "
            f"{row['capacity_skips']} | {row['cumulative_return']:.2%} | "
            f"{row['maximum_drawdown']:.2%} | {annual} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def save_challenger_robustness_report(
    a_dir: Path,
    c_dir: Path,
    output: Path,
) -> Path:
    """Compare the frozen A/C mix and adverse attribution scenarios."""
    mixed = evaluate_mixed_fixed_slot_portfolio(
        {"A": a_dir, "C": c_dir}, {"A": 4, "C": 3},
    )
    scenarios = [
        ("A full", evaluate_fixed_slot_portfolio(a_dir)),
        ("C full", evaluate_fixed_slot_portfolio(c_dir)),
        ("C excluding 2026", evaluate_fixed_slot_portfolio(
            c_dir, exclude_years=(2026,),
        )),
        ("C excluding best trade", evaluate_fixed_slot_portfolio(
            c_dir, exclude_top_trades=1,
        )),
        ("C excluding best 3 trades", evaluate_fixed_slot_portfolio(
            c_dir, exclude_top_trades=3,
        )),
    ]
    lines = [
        "# TITAN Challenger Robustness", "",
        "> Research only. Exclusion scenarios are diagnostics, not investable strategies.",
        "", "## Fixed A/C mix", "",
        "| Allocation | Accepted | Cumulative | Max drawdown | Annual returns |",
        "|---|---:|---:|---:|---|",
    ]
    annual = ", ".join(
        f"{year} {value:.2%}"
        for year, value in mixed["annual_returns"].items()
    )
    lines.append(
        f"| A 4 slots / C 3 slots | {mixed['accepted_trades']} | "
        f"{mixed['cumulative_return']:.2%} | "
        f"{mixed['maximum_drawdown']:.2%} | {annual} |"
    )
    lines += [
        "", "## Sensitivity", "",
        "| Scenario | Accepted | Cumulative | Max drawdown |",
        "|---|---:|---:|---:|",
    ]
    for label, row in scenarios:
        lines.append(
            f"| {label} | {row['accepted_trades']} | "
            f"{row['cumulative_return']:.2%} | "
            f"{row['maximum_drawdown']:.2%} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _load_signals(
    directory: Path, source: str = "strategy", cost_multiplier: float = 1.0,
) -> list[dict]:
    if cost_multiplier <= 0:
        raise ValueError("cost_multiplier must be positive")
    signals = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry = datetime.fromisoformat(payload["selected_at"])
        exit_at = datetime.fromisoformat(payload["evaluation_date"])
        for trade in payload.get("trades", []):
            gross_return = float(trade.get("gross_return", trade["net_return"]))
            if cost_multiplier == 1.0:
                net_return = float(trade["net_return"])
            else:
                buy_cost = cost_multiplier * 0.00115
                sell_cost = cost_multiplier * 0.00265
                net_return = (
                    (1.0 + gross_return) * (1.0 - sell_cost)
                    / (1.0 + buy_cost) - 1.0
                )
            signals.append({
                "source": source,
                "entry": entry, "exit": exit_at, "code": trade["code"],
                "rank": int(trade["rank"]),
                "selection_price": float(trade["selection_price"]),
                "gross_return": gross_return,
                "net_return": net_return,
            })
    return signals


def _load_prices(directory: Path) -> dict[str, dict[datetime, float]]:
    result = {}
    for path in directory.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        result[payload["code"]] = {
            datetime.fromisoformat(row["date"]): float(row["close"])
            for row in payload["candles"]
        }
    return result


def _price_on_or_before(rows: dict[datetime, float], date: datetime) -> float | None:
    eligible = [key for key in rows if key <= date]
    return rows[max(eligible)] if eligible else None
