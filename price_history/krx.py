import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx


@dataclass(slots=True, frozen=True)
class KrxPriceCollectionResult:
    requested_dates: int
    api_calls: int
    saved_responses: int
    skipped_cached: int
    completed: bool
    last_date: date | None


class KrxPriceClient:
    BASE_URL = "https://data-dbg.krx.co.kr/svc/apis/sto"
    ENDPOINTS = {
        "KOSPI": "stk_bydd_trd",
        "KOSDAQ": "ksq_bydd_trd",
    }

    def __init__(self, auth_key: str, client: httpx.Client | None = None):
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
                "KRX API returned 401 Unauthorized. Verify approved access "
                "to both daily trading information APIs."
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("OutBlock_1"), list):
            raise ValueError("KRX response has no OutBlock_1 list")
        return payload


class KrxPriceRawRepository:
    def __init__(self, directory: Path):
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
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()


class KrxPriceCollector:
    MARKETS = ("KOSPI", "KOSDAQ")

    def __init__(self, client: KrxPriceClient, repository: KrxPriceRawRepository):
        self.client = client
        self.repository = repository

    def collect(self, start: date, end: date, max_requests=5000):
        if end < start:
            raise ValueError("end must be on or after start")
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero")
        requested = calls = saved = skipped = 0
        last_date = None
        current = start
        exhausted = False
        while current <= end:
            if current.weekday() < 5:
                requested += 1
                for market in self.MARKETS:
                    if self.repository.exists(current, market):
                        skipped += 1
                        continue
                    if calls >= max_requests:
                        exhausted = True
                        break
                    payload = self.client.fetch(market, current)
                    calls += 1
                    self.repository.save(current, market, payload)
                    saved += 1
                if exhausted:
                    break
                last_date = current
            current += timedelta(days=1)
        return KrxPriceCollectionResult(
            requested, calls, saved, skipped,
            not exhausted and current > end, last_date,
        )
