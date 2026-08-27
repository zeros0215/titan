import json
import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx


@dataclass(slots=True, frozen=True)
class KrxCollectionResult:
    requested_dates: int
    api_calls: int
    saved_responses: int
    skipped_cached: int
    completed: bool
    last_date: date | None


class KrxUniverseClient:
    BASE_URL = "https://data-dbg.krx.co.kr/svc/apis/sto"
    ENDPOINTS = {
        "KOSPI": "stk_isu_base_info",
        "KOSDAQ": "ksq_isu_base_info",
    }

    def __init__(
        self,
        auth_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not auth_key.strip():
            raise ValueError("KRX_AUTH_KEY is required")
        self.auth_key = auth_key.strip()
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self, market: str, base_date: date) -> dict:
        market = market.upper()
        if market not in self.ENDPOINTS:
            raise ValueError(f"unsupported KRX market: {market}")
        response = self.client.get(
            f"{self.BASE_URL}/{self.ENDPOINTS[market]}",
            headers={"AUTH_KEY": self.auth_key, "Accept": "application/json"},
            params={"basDd": base_date.strftime("%Y%m%d")},
        )
        if response.status_code == 401:
            raise ValueError(
                "KRX API returned 401 Unauthorized. Verify that this "
                "authentication key has approved access to both "
                "'유가증권 종목기본정보' and '코스닥 종목기본정보'."
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("KRX response must be a JSON object")
        rows = payload.get("OutBlock_1")
        if rows is None or not isinstance(rows, list):
            raise ValueError("KRX response has no OutBlock_1 list")
        return payload


class KrxRawRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path_for(self, base_date: date, market: str) -> Path:
        return self.directory / f"{base_date:%Y%m%d}_{market.upper()}.json"

    def exists(self, base_date: date, market: str) -> bool:
        return self.path_for(base_date, market).exists()

    def save(self, base_date: date, market: str, payload: dict) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(base_date, market)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def content_sha256(
        self,
        start: date | None = None,
        seed: str | None = None,
    ) -> str:
        digest = hashlib.sha256()
        if seed is not None:
            digest.update(b"incremental-v1\0")
            digest.update(seed.encode("ascii"))
        for path in sorted(self.directory.glob("????????_*.json")):
            if start is not None and path.name[:8] < start.strftime("%Y%m%d"):
                continue
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def save_collection_manifest(self, payload: dict) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "collection_manifest.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


class KrxUniverseCollector:
    MARKETS = ("KOSPI", "KOSDAQ")

    def __init__(self, client: KrxUniverseClient, repository: KrxRawRepository):
        self.client = client
        self.repository = repository

    def collect(
        self,
        start: date,
        end: date,
        max_requests: int = 5000,
    ) -> KrxCollectionResult:
        if end < start:
            raise ValueError("end must be on or after start")
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero")
        requested_dates = api_calls = saved = skipped = 0
        last_date = None
        current = start
        exhausted = False
        while current <= end:
            if current.weekday() < 5:
                requested_dates += 1
                for market in self.MARKETS:
                    if self.repository.exists(current, market):
                        skipped += 1
                        continue
                    if api_calls >= max_requests:
                        exhausted = True
                        break
                    payload = self.client.fetch(market, current)
                    api_calls += 1
                    self.repository.save(current, market, payload)
                    saved += 1
                if exhausted:
                    break
                last_date = current
            current += timedelta(days=1)
        return KrxCollectionResult(
            requested_dates=requested_dates,
            api_calls=api_calls,
            saved_responses=saved,
            skipped_cached=skipped,
            completed=not exhausted and current > end,
            last_date=last_date,
        )
