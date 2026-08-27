import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from domain.enums import MarketType
from universe_history.model import UniverseHistoryRecord


@dataclass(slots=True)
class _Segment:
    first_observed: date
    last_observed: date
    first_index: int
    last_index: int
    name: str
    listed: date


class KrxSnapshotNormalizer:
    """Stream daily snapshots into listing intervals with bounded memory."""

    MARKET_BY_FILE = {
        "KOSPI": MarketType.KOSPI,
        "KOSDAQ": MarketType.KOSDAQ,
    }
    COMMON_STOCK_NAMES = {"보통주", "COMMON STOCK"}
    STOCK_GROUP_NAMES = {"주권", "STOCK"}

    def normalize(self, raw_directory: Path) -> list[UniverseHistoryRecord]:
        paths = sorted(raw_directory.glob("????????_*.json"))
        if not paths:
            raise ValueError("no KRX raw snapshots found")

        available_dates = self._available_dates(paths)
        if not available_dates:
            raise ValueError("KRX raw snapshots contain no listed stocks")
        date_position = {
            value: index for index, value in enumerate(available_dates)
        }

        active: dict[tuple[str, str], _Segment] = {}
        records = []
        for path in paths:
            base_date, market_name = self._identity(path)
            if base_date not in date_position:
                continue
            index = date_position[base_date]
            rows = self._rows(path)
            for row in rows:
                if not self._eligible(row):
                    continue
                code = str(row.get("ISU_SRT_CD", "")).strip()
                if not code:
                    continue
                name = str(
                    row.get("ISU_ABBRV") or row.get("ISU_NM") or code
                ).strip()
                listed = self._date(row.get("LIST_DD")) or base_date
                key = (code, market_name)
                segment = active.get(key)
                if segment is not None and index != segment.last_index + 1:
                    records.append(self._record(
                        key, segment, available_dates[-1]
                    ))
                    segment = None
                if segment is None:
                    active[key] = _Segment(
                        first_observed=base_date,
                        last_observed=base_date,
                        first_index=index,
                        last_index=index,
                        name=name,
                        listed=listed,
                    )
                else:
                    segment.last_observed = base_date
                    segment.last_index = index
                    segment.name = name

        for key, segment in sorted(active.items()):
            records.append(self._record(key, segment, available_dates[-1]))
        return sorted(
            records,
            key=lambda item: (
                item.code, item.market.value, item.effective_from
            ),
        )

    def normalize_incremental(
        self,
        raw_directory: Path,
        base_records: list[UniverseHistoryRecord],
        base_coverage_end: date,
    ) -> list[UniverseHistoryRecord]:
        """Extend compiled history by reading only snapshots after the base."""
        paths = [
            path
            for path in sorted(raw_directory.glob("????????_*.json"))
            if self._identity(path)[0] > base_coverage_end
        ]
        if not paths:
            raise ValueError("no new KRX raw snapshots found")
        available_dates = self._available_dates(paths)
        if not available_dates:
            raise ValueError("new KRX raw snapshots contain no listed stocks")
        date_position = {
            value: index for index, value in enumerate(available_dates)
        }

        records = [item for item in base_records if item.effective_to is not None]
        active = {}
        for item in base_records:
            if item.effective_to is None:
                active[(item.code, item.market.value)] = _Segment(
                    first_observed=item.effective_from,
                    last_observed=base_coverage_end,
                    first_index=-1,
                    last_index=-1,
                    name=item.name,
                    listed=item.effective_from,
                )

        for path in paths:
            base_date, market_name = self._identity(path)
            if base_date not in date_position:
                continue
            index = date_position[base_date]
            for row in self._rows(path):
                if not self._eligible(row):
                    continue
                code = str(row.get("ISU_SRT_CD", "")).strip()
                if not code:
                    continue
                name = str(
                    row.get("ISU_ABBRV") or row.get("ISU_NM") or code
                ).strip()
                listed = self._date(row.get("LIST_DD")) or base_date
                key = (code, market_name)
                segment = active.get(key)
                if segment is not None and index != segment.last_index + 1:
                    records.append(self._incremental_record(key, segment))
                    segment = None
                if segment is None:
                    active[key] = _Segment(
                        first_observed=base_date,
                        last_observed=base_date,
                        first_index=index,
                        last_index=index,
                        name=name,
                        listed=listed,
                    )
                else:
                    segment.last_observed = base_date
                    segment.last_index = index
                    segment.name = name

        latest_date = available_dates[-1]
        for key, segment in sorted(active.items()):
            records.append(UniverseHistoryRecord(
                code=key[0],
                name=segment.name,
                market=self.MARKET_BY_FILE[key[1]],
                effective_from=(
                    segment.listed
                    if segment.first_index == -1
                    else segment.first_observed
                ),
                effective_to=(
                    None
                    if segment.last_observed == latest_date
                    else segment.last_observed
                ),
                source_id="KRX_OPEN_API_ISSUE_BASE_INFO",
            ))
        return sorted(
            records,
            key=lambda item: (item.code, item.market.value, item.effective_from),
        )

    def _incremental_record(self, key, segment):
        return UniverseHistoryRecord(
            code=key[0],
            name=segment.name,
            market=self.MARKET_BY_FILE[key[1]],
            effective_from=(
                segment.listed
                if segment.first_index == -1
                else segment.first_observed
            ),
            effective_to=segment.last_observed,
            source_id="KRX_OPEN_API_ISSUE_BASE_INFO",
        )

    def _available_dates(self, paths):
        values = set()
        for path in paths:
            base_date, _ = self._identity(path)
            if self._rows(path):
                values.add(base_date)
        return sorted(values)

    @staticmethod
    def _rows(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("OutBlock_1")
        if not isinstance(rows, list):
            raise ValueError(f"invalid KRX snapshot schema: {path.name}")
        return rows

    def _record(self, key, segment, latest_date):
        code, market_name = key
        effective_from = (
            segment.listed
            if segment.first_index == 0
            else segment.first_observed
        )
        return UniverseHistoryRecord(
            code=code,
            name=segment.name,
            market=self.MARKET_BY_FILE[market_name],
            effective_from=effective_from,
            effective_to=(
                None
                if segment.last_observed == latest_date
                else segment.last_observed
            ),
            source_id="KRX_OPEN_API_ISSUE_BASE_INFO",
        )

    @staticmethod
    def _identity(path: Path):
        stem = path.stem
        raw_date, market = stem.split("_", 1)
        if market not in KrxSnapshotNormalizer.MARKET_BY_FILE:
            raise ValueError(f"unsupported raw snapshot name: {path.name}")
        return date.fromisoformat(
            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        ), market

    @staticmethod
    def _date(value):
        text = str(value or "").strip()
        if not text:
            return None
        return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:]}")

    @classmethod
    def _eligible(cls, row) -> bool:
        group = str(row.get("SECUGRP_NM", "")).strip().upper()
        kind = str(row.get("KIND_STKCERT_TP_NM", "")).strip().upper()
        name = str(row.get("ISU_ABBRV") or row.get("ISU_NM") or "").upper()
        section = str(row.get("SECT_TP_NM", "")).strip().upper()
        return (
            group in cls.STOCK_GROUP_NAMES
            and kind in cls.COMMON_STOCK_NAMES
            and "스팩" not in name
            and "SPAC" not in name
            and "관리" not in section
            and "MANAGED" not in section
        )
