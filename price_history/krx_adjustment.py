import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from universe_history.krx_normalizer import KrxSnapshotNormalizer


@dataclass(slots=True, frozen=True)
class AdjustmentPolicy:
    minimum_share_change: float = 0.20
    continuity_lower: float = 0.75
    continuity_upper: float = 1.25


class KrxAdjustedPriceCompiler:
    """Build per-stock candles with conservative split/merge adjustments."""

    def __init__(self, policy: AdjustmentPolicy | None = None):
        self.policy = policy or AdjustmentPolicy()

    def compile(
        self,
        universe_raw_dir: Path,
        price_raw_dir: Path,
        output_dir: Path,
    ) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        database = output_dir / "price_build_index.sqlite"
        connection = sqlite3.connect(database)
        try:
            self._create_schema(connection)
            inserted, rejected_rows = self._load(
                connection, universe_raw_dir, price_raw_dir
            )
            (
                stock_count,
                action_count,
                unresolved,
                quarantine_count,
            ) = self._export(
                connection, output_dir
            )
            market_cap_sessions = self._export_market_cap_universe(
                connection, output_dir
            )
        finally:
            connection.close()
        manifest = {
            "schema_version": 1,
            "source_name": "KRX Data Marketplace OPEN API",
            "coverage_start": self._source_manifest(
                price_raw_dir
            )["coverage_start"],
            "coverage_end": self._source_manifest(
                price_raw_dir
            )["coverage_end"],
            "price_history_complete": True,
            "adjusted_prices": True,
            "official_adjusted_prices": False,
            "adjustment_method": (
                "listed-share inverse factor when share change >=20% and "
                "price/share continuity is within 0.75..1.25"
            ),
            "stock_count": stock_count,
            "row_count": inserted,
            "rejected_row_count": len(rejected_rows),
            "adjustment_event_count": action_count,
            "unresolved_large_jump_count": unresolved,
            "quality_quarantine_count": quarantine_count,
            "quality_quarantine_sessions": 61,
            "market_cap_universe": {
                "method": "unadjusted close multiplied by listed shares",
                "limit": 500,
                "minimum_trading_value": 5_000_000_000,
                "excluded": [
                    "managed issues",
                    "SPACs",
                    "preferred shares",
                ],
                "session_count": market_cap_sessions,
                "file": "market_cap_top500.json",
            },
            "provisional_backtest_ready": True,
            "formal_backtest_ready": False,
            "formal_blocker": (
                "KRX source does not provide an official adjusted-price "
                "field; inferred actions and quarantines require review"
            ),
            "universe_raw_sha256": self._source_manifest(
                universe_raw_dir
            )["raw_sha256"],
            "price_raw_sha256": self._source_manifest(
                price_raw_dir
            )["raw_sha256"],
            "compiled_at": datetime.now().astimezone().isoformat(),
        }
        (output_dir / "price_history_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "rejected_price_rows.json").write_text(
            json.dumps(rejected_rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def _export_market_cap_universe(
        connection,
        output_dir,
        limit=500,
        minimum_trading_value=5_000_000_000,
    ):
        """Persist point-in-time rankings without carrying future constituents."""
        connection.execute(
            "CREATE INDEX IF NOT EXISTS prices_trade_date ON prices(trade_date)"
        )
        sessions = {}
        trade_dates = (
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT trade_date FROM prices ORDER BY trade_date"
            )
        )
        for trade_date in trade_dates:
            ranked = connection.execute(
                """
                SELECT code, close * volume AS trading_value
                FROM prices
                WHERE trade_date=?
                ORDER BY (close * listed_shares) DESC, code ASC
                LIMIT ?
                """,
                (trade_date, limit),
            )
            sessions[trade_date] = [
                code
                for code, trading_value in ranked
                if trading_value >= minimum_trading_value
            ]
        payload = {
            "schema_version": 1,
            "method": "unadjusted close multiplied by listed shares",
            "limit": limit,
            "minimum_trading_value": minimum_trading_value,
            "excluded": [
                "managed issues",
                "SPACs",
                "preferred shares",
            ],
            "sessions": sessions,
        }
        (output_dir / "market_cap_top500.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return len(sessions)

    @staticmethod
    def _create_schema(connection):
        connection.execute("DROP TABLE IF EXISTS prices")
        connection.execute(
            """
            CREATE TABLE prices (
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                market TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                listed_shares INTEGER NOT NULL,
                PRIMARY KEY (code, trade_date)
            )
            """
        )

    def _load(self, connection, universe_dir, price_dir):
        inserted = 0
        rejected = []
        batch = []
        for price_path in sorted(price_dir.glob("????????_*.json")):
            universe_path = universe_dir / price_path.name
            if not universe_path.exists():
                raise ValueError(
                    f"matching universe snapshot is missing: {price_path.name}"
                )
            universe_rows = self._rows(universe_path)
            eligible = {
                str(row.get("ISU_SRT_CD", "")).strip(): row
                for row in universe_rows
                if KrxSnapshotNormalizer._eligible(row)
            }
            for row in self._rows(price_path):
                code = str(row.get("ISU_CD", "")).strip()
                issue = eligible.get(code)
                if issue is None:
                    continue
                try:
                    values = (
                        code,
                        str(
                            issue.get("ISU_ABBRV")
                            or row.get("ISU_NM")
                            or code
                        ).strip(),
                        "KOSPI" if price_path.stem.endswith("KOSPI") else "KOSDAQ",
                        self._date(row["BAS_DD"]),
                        self._number(row["TDD_OPNPRC"]),
                        self._number(row["TDD_HGPRC"]),
                        self._number(row["TDD_LWPRC"]),
                        self._number(row["TDD_CLSPRC"]),
                        int(self._number(row["ACC_TRDVOL"])),
                        int(self._number(row["LIST_SHRS"])),
                    )
                    values = self._normalize_no_trade(values)
                    self._validate_values(values)
                    batch.append(values)
                except (KeyError, TypeError, ValueError) as error:
                    rejected.append({
                        "snapshot": price_path.name,
                        "code": code,
                        "date": str(row.get("BAS_DD", "")),
                        "reason": str(error),
                    })
                    continue
                if len(batch) >= 10_000:
                    connection.executemany(
                        "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                        batch,
                    )
                    inserted += len(batch)
                    batch.clear()
        if batch:
            connection.executemany(
                "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            inserted += len(batch)
        connection.commit()
        return inserted, rejected

    def _export(self, connection, output_dir):
        codes = [
            row[0] for row in connection.execute(
                "SELECT DISTINCT code FROM prices ORDER BY code"
            )
        ]
        expected_paths = {output_dir / f"{code}.json" for code in codes}
        for path in output_dir.glob("*.json"):
            if (
                len(path.stem) == 6
                and path.stem.isalnum()
                and path not in expected_paths
            ):
                path.unlink()
        action_count = unresolved_count = quarantine_count = 0
        quarantine_records = []
        for code in codes:
            rows = list(connection.execute(
                """
                SELECT name, market, trade_date, open, high, low, close,
                       volume, listed_shares
                FROM prices WHERE code=? ORDER BY trade_date
                """,
                (code,),
            ))
            actions, unresolved = self._events(rows)
            quarantines = self._quarantines(rows, unresolved)
            action_count += len(actions)
            unresolved_count += len(unresolved)
            quarantine_count += len(quarantines)
            quarantine_records.extend(
                {"code": code, **item} for item in quarantines
            )
            factors = self._backward_factors(rows, actions)
            candles = []
            for row, (price_factor, volume_factor) in zip(rows, factors):
                candles.append({
                    "date": row[2],
                    "open": row[3] * price_factor,
                    "high": row[4] * price_factor,
                    "low": row[5] * price_factor,
                    "close": row[6] * price_factor,
                    "volume": int(round(row[7] * volume_factor)),
                })
            payload = {
                "code": code,
                "name": rows[-1][0],
                "market": rows[-1][1],
                "adjusted_prices": True,
                "official_adjusted_prices": False,
                "adjustment_events": actions,
                "unresolved_large_jumps": unresolved,
                "quality_quarantines": quarantines,
                "candles": candles,
            }
            (output_dir / f"{code}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (output_dir / "quality_quarantines.json").write_text(
            json.dumps(quarantine_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return (
            len(codes),
            action_count,
            unresolved_count,
            quarantine_count,
        )

    def _events(self, rows):
        actions = []
        unresolved = []
        for index in range(1, len(rows)):
            previous, current = rows[index - 1], rows[index]
            share_ratio = current[8] / previous[8]
            price_ratio = current[6] / previous[6]
            continuity = share_ratio * price_ratio
            share_change = abs(share_ratio - 1.0)
            if (
                share_change >= self.policy.minimum_share_change
                and self.policy.continuity_lower
                <= continuity
                <= self.policy.continuity_upper
            ):
                actions.append({
                    "index": index,
                    "date": current[2],
                    "share_ratio": share_ratio,
                    "backward_price_factor": 1.0 / share_ratio,
                    "continuity": continuity,
                })
            elif price_ratio < 0.55 or price_ratio > 1.80:
                gap_days = (
                    datetime.fromisoformat(current[2])
                    - datetime.fromisoformat(previous[2])
                ).days
                if gap_days > 10:
                    classification = "POST_SUSPENSION_DISCONTINUITY"
                elif share_change >= self.policy.minimum_share_change:
                    classification = "UNRESOLVED_CORPORATE_ACTION"
                else:
                    classification = "UNEXPLAINED_PRICE_DISCONTINUITY"
                unresolved.append({
                    "index": index,
                    "previous_date": previous[2],
                    "date": current[2],
                    "calendar_gap_days": gap_days,
                    "classification": classification,
                    "price_ratio": price_ratio,
                    "share_ratio": share_ratio,
                    "continuity": continuity,
                })
        return actions, unresolved

    @staticmethod
    def _quarantines(rows, unresolved, sessions=61):
        intervals = []
        for event in unresolved:
            start = event["index"]
            end = min(start + sessions - 1, len(rows) - 1)
            item = {
                "start": rows[start][2],
                "end": rows[end][2],
                "classification": event["classification"],
                "event_count": 1,
            }
            if intervals and item["start"] <= intervals[-1]["end"]:
                intervals[-1]["end"] = max(intervals[-1]["end"], item["end"])
                intervals[-1]["event_count"] += 1
                labels = set(intervals[-1]["classification"].split("+"))
                labels.add(item["classification"])
                intervals[-1]["classification"] = "+".join(sorted(labels))
            else:
                intervals.append(item)
        return intervals

    @staticmethod
    def _backward_factors(rows, actions):
        by_index = {item["index"]: item for item in actions}
        factors = [(1.0, 1.0)] * len(rows)
        price_factor = volume_factor = 1.0
        for index in range(len(rows) - 1, -1, -1):
            factors[index] = (price_factor, volume_factor)
            action = by_index.get(index)
            if action is not None:
                ratio = action["share_ratio"]
                price_factor *= 1.0 / ratio
                volume_factor *= ratio
                factors[index - 1 if index else 0] = (
                    price_factor, volume_factor
                )
        return factors

    @staticmethod
    def _rows(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("OutBlock_1")
        if not isinstance(rows, list):
            raise ValueError(f"invalid KRX snapshot schema: {path.name}")
        return rows

    @staticmethod
    def _number(value):
        return float(str(value).replace(",", "").strip())

    @staticmethod
    def _date(value):
        text = str(value).strip()
        return f"{text[:4]}-{text[4:6]}-{text[6:]}T00:00:00"

    @staticmethod
    def _validate_values(values):
        _, _, _, _, open_, high, low, close, volume, shares = values
        if min(open_, high, low, close) <= 0:
            raise ValueError("OHLC must be positive")
        if high < max(open_, low, close) or low > min(open_, high, close):
            raise ValueError("invalid OHLC relationship")
        if volume < 0 or shares <= 0:
            raise ValueError("invalid volume or listed shares")

    @staticmethod
    def _normalize_no_trade(values):
        (
            code, name, market, trade_date, open_, high, low, close,
            volume, shares,
        ) = values
        if volume == 0 and close > 0 and min(open_, high, low) == 0:
            open_ = high = low = close
        return (
            code, name, market, trade_date, open_, high, low, close,
            volume, shares,
        )

    @staticmethod
    def _source_manifest(directory):
        return json.loads(
            (directory / "collection_manifest.json").read_text(
                encoding="utf-8"
            )
        )
