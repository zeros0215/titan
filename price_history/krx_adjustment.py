import hashlib
import json
import math
import os
import shutil
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
        base_price_dir: Path | None = None,
    ) -> dict:
        if base_price_dir is not None:
            return self._compile_incremental(
                universe_raw_dir, price_raw_dir, output_dir, base_price_dir
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        database = output_dir / "price_build_index.sqlite"
        connection = sqlite3.connect(database)
        try:
            self._create_schema(connection)
            inserted, rejected_rows, _ = self._load(
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

    def _compile_incremental(
        self, universe_raw_dir, price_raw_dir, output_dir, base_price_dir
    ):
        base_price_dir = base_price_dir.resolve()
        output_dir = output_dir.resolve()
        if base_price_dir == output_dir:
            raise ValueError("incremental staging must differ from active data")
        base_manifest = json.loads(
            (base_price_dir / "price_history_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        source_manifest = self._source_manifest(price_raw_dir)
        previous_end = str(base_manifest["coverage_end"])
        coverage_end = str(source_manifest["coverage_end"])
        if coverage_end < previous_end:
            raise ValueError("raw price coverage is older than active data")
        self._clone_staging(base_price_dir, output_dir)
        if coverage_end == previous_end:
            return base_manifest

        database = output_dir / "price_build_index.sqlite"
        connection = sqlite3.connect(database)
        try:
            # This is an isolated staging copy. A failed build is discarded, so
            # a disk-backed rollback journal only adds several minutes of I/O.
            connection.execute("PRAGMA journal_mode=MEMORY")
            connection.execute("PRAGMA synchronous=OFF")
            inserted, rejected_rows, affected_codes = self._load(
                connection,
                universe_raw_dir,
                price_raw_dir,
                start_after=previous_end,
            )
            if not affected_codes:
                raise ValueError("new coverage contains no eligible price rows")
            old_counts = self._payload_counts(output_dir, affected_codes)
            new_counts = self._export_incremental_codes(
                connection, output_dir, sorted(affected_codes), previous_end
            )
            market_cap_sessions = self._append_market_cap_universe(
                connection, output_dir, previous_end
            )
            row_count = connection.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
            stock_count = connection.execute(
                "SELECT COUNT(DISTINCT code) FROM prices"
            ).fetchone()[0]
        finally:
            connection.close()

        existing_rejected = json.loads(
            (output_dir / "rejected_price_rows.json").read_text(encoding="utf-8")
        )
        existing_rejected.extend(rejected_rows)
        self._write_json(
            output_dir / "rejected_price_rows.json", existing_rejected, indent=2
        )
        self._merge_quarantines(output_dir, affected_codes, new_counts[3])
        manifest = dict(base_manifest)
        manifest.update({
            "coverage_end": coverage_end,
            "stock_count": stock_count,
            "row_count": row_count,
            "rejected_row_count": len(existing_rejected),
            "adjustment_event_count": (
                int(base_manifest["adjustment_event_count"])
                - old_counts[0] + new_counts[0]
            ),
            "unresolved_large_jump_count": (
                int(base_manifest["unresolved_large_jump_count"])
                - old_counts[1] + new_counts[1]
            ),
            "quality_quarantine_count": (
                int(base_manifest["quality_quarantine_count"])
                - old_counts[2] + new_counts[2]
            ),
            "market_cap_universe": {
                **base_manifest["market_cap_universe"],
                "session_count": market_cap_sessions,
            },
            "universe_raw_sha256": self._source_manifest(universe_raw_dir)["raw_sha256"],
            "price_raw_sha256": source_manifest["raw_sha256"],
            "compiled_at": datetime.now().astimezone().isoformat(),
            "incremental_from": previous_end,
            "incremental_rows": inserted,
            "incremental_stock_count": len(affected_codes),
        })
        self._write_json(
            output_dir / "price_history_manifest.json", manifest, indent=2
        )
        return manifest

    @staticmethod
    def _clone_staging(source, destination):
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("incremental staging directory must be empty")
        destination.mkdir(parents=True, exist_ok=True)
        for source_path in source.iterdir():
            target = destination / source_path.name
            if source_path.name == "price_build_index.sqlite":
                shutil.copy2(source_path, target)
                continue
            try:
                os.link(source_path, target)
            except OSError:
                shutil.copy2(source_path, target)

    @staticmethod
    def _payload_counts(output_dir, codes):
        actions = unresolved = quarantines = 0
        for code in codes:
            path = output_dir / f"{code}.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            actions += len(payload.get("adjustment_events", []))
            unresolved += len(payload.get("unresolved_large_jumps", []))
            quarantines += len(payload.get("quality_quarantines", []))
        return actions, unresolved, quarantines

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

    def _load(self, connection, universe_dir, price_dir, start_after=None):
        inserted = 0
        rejected = []
        affected_codes = set()
        batch = []
        for price_path in sorted(price_dir.glob("????????_*.json")):
            snapshot_date = (
                f"{price_path.name[:4]}-{price_path.name[4:6]}-"
                f"{price_path.name[6:8]}"
            )
            if start_after is not None and snapshot_date <= start_after:
                continue
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
                    affected_codes.add(code)
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
        return inserted, rejected, affected_codes

    def _export_codes(self, connection, output_dir, codes):
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
            quarantine_records.extend({"code": code, **item} for item in quarantines)
            factors = self._backward_factors(rows, actions)
            candles = [{
                "date": row[2],
                "open": row[3] * price_factor,
                "high": row[4] * price_factor,
                "low": row[5] * price_factor,
                "close": row[6] * price_factor,
                "volume": int(round(row[7] * volume_factor)),
            } for row, (price_factor, volume_factor) in zip(rows, factors)]
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
            self._write_json(output_dir / f"{code}.json", payload, indent=2)
        return action_count, unresolved_count, quarantine_count, quarantine_records

    def _export_incremental_codes(
        self, connection, output_dir, codes, previous_end
    ):
        rebuild = []
        for code in codes:
            path = output_dir / f"{code}.json"
            if not path.exists():
                rebuild.append(code)
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            candles = payload.get("candles", [])
            if not candles:
                rebuild.append(code)
                continue
            # An unresolved event near the old boundary may have a quarantine
            # whose 61-session end moves forward as sessions are appended.
            quarantines = payload.get("quality_quarantines", [])
            if quarantines and quarantines[-1].get("end") == candles[-1].get("date"):
                rebuild.append(code)
                continue
            boundary_rows = list(connection.execute(
                """
                SELECT name, market, trade_date, open, high, low, close,
                       volume, listed_shares
                FROM prices WHERE code=? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1
                """,
                (code, previous_end + "T99:99:99"),
            ))
            new_rows = list(connection.execute(
                """
                SELECT name, market, trade_date, open, high, low, close,
                       volume, listed_shares
                FROM prices WHERE code=? AND trade_date > ? ORDER BY trade_date
                """,
                (code, previous_end + "T99:99:99"),
            ))
            if not boundary_rows or not new_rows:
                rebuild.append(code)
                continue
            actions, unresolved = self._events(boundary_rows + new_rows)
            if actions or unresolved:
                rebuild.append(code)
                continue
            payload["name"] = new_rows[-1][0]
            payload["market"] = new_rows[-1][1]
            payload["candles"].extend({
                "date": row[2], "open": row[3], "high": row[4],
                "low": row[5], "close": row[6], "volume": row[7],
            } for row in new_rows)
            self._write_json(path, payload, separators=(",", ":"))
        if rebuild:
            self._export_codes(connection, output_dir, rebuild)
        actions = unresolved = quarantines = 0
        quarantine_records = []
        for code in codes:
            payload = json.loads(
                (output_dir / f"{code}.json").read_text(encoding="utf-8")
            )
            actions += len(payload.get("adjustment_events", []))
            unresolved += len(payload.get("unresolved_large_jumps", []))
            rows = payload.get("quality_quarantines", [])
            quarantines += len(rows)
            quarantine_records.extend({"code": code, **row} for row in rows)
        return actions, unresolved, quarantines, quarantine_records

    def _append_market_cap_universe(self, connection, output_dir, previous_end):
        path = output_dir / "market_cap_top500.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        dates = [row[0] for row in connection.execute(
            "SELECT DISTINCT trade_date FROM prices WHERE trade_date > ? ORDER BY trade_date",
            (previous_end,),
        )]
        for trade_date in dates:
            ranked = connection.execute(
                """
                SELECT code, close * volume AS trading_value
                FROM prices WHERE trade_date=?
                ORDER BY (close * listed_shares) DESC, code ASC LIMIT ?
                """,
                (trade_date, int(payload.get("limit", 500))),
            )
            minimum = int(payload.get("minimum_trading_value", 5_000_000_000))
            payload["sessions"][trade_date] = [
                code for code, trading_value in ranked if trading_value >= minimum
            ]
        self._write_json(path, payload, separators=(",", ":"))
        return len(payload["sessions"])

    def _merge_quarantines(self, output_dir, affected_codes, replacements):
        path = output_dir / "quality_quarantines.json"
        existing = json.loads(path.read_text(encoding="utf-8"))
        merged = [row for row in existing if row.get("code") not in affected_codes]
        merged.extend(replacements)
        merged.sort(key=lambda row: (row.get("code", ""), row.get("start", "")))
        self._write_json(path, merged, indent=2)

    @staticmethod
    def _write_json(path, payload, **kwargs):
        # Incremental staging may hard-link unchanged active files. Unlink first
        # so replacing a changed file can never mutate the active release.
        if path.exists():
            path.unlink()
        path.write_text(
            json.dumps(payload, ensure_ascii=False, **kwargs), encoding="utf-8"
        )

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
