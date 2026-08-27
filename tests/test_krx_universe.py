import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from domain.enums import MarketType
from universe_history.krx import (
    KrxRawRepository,
    KrxUniverseClient,
    KrxUniverseCollector,
)
from universe_history.krx_normalizer import KrxSnapshotNormalizer
from universe_history.model import UniverseHistoryRecord


class _Client:
    def __init__(self):
        self.calls = []

    def fetch(self, market, base_date):
        self.calls.append((market, base_date))
        return {
            "OutBlock_1": [{
                "ISU_SRT_CD": "123456",
                "ISU_ABBRV": "Fixture",
                "LIST_DD": "20200101",
                "SECUGRP_NM": "주권",
                "KIND_STKCERT_TP_NM": "보통주",
            }]
        }


class KrxUniverseTest(unittest.TestCase):
    def test_client_explains_missing_service_approval(self):
        class Response:
            status_code = 401

        class HttpClient:
            def get(self, *args, **kwargs):
                return Response()

        client = KrxUniverseClient("key", HttpClient())

        with self.assertRaisesRegex(ValueError, "approved access"):
            client.fetch("KOSPI", date(2025, 12, 30))

    def test_collector_stops_at_budget_and_resumes_from_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = KrxRawRepository(Path(temporary))
            client = _Client()
            collector = KrxUniverseCollector(client, repository)

            first = collector.collect(
                date(2026, 7, 27),
                date(2026, 7, 28),
                max_requests=2,
            )
            second = collector.collect(
                date(2026, 7, 27),
                date(2026, 7, 28),
                max_requests=2,
            )

            self.assertFalse(first.completed)
            self.assertTrue(second.completed)
            self.assertEqual(4, len(client.calls))
            self.assertEqual(2, second.skipped_cached)
            self.assertTrue(repository.content_sha256())

    def test_normalizer_reconstructs_market_transfer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = KrxRawRepository(root)
            self._save(repository, date(2023, 6, 28), "KOSDAQ", True)
            self._save(repository, date(2023, 6, 28), "KOSPI", False)
            self._save(repository, date(2023, 6, 29), "KOSDAQ", True)
            self._save(repository, date(2023, 6, 29), "KOSPI", False)
            self._save(repository, date(2023, 6, 30), "KOSDAQ", False)
            self._save(repository, date(2023, 6, 30), "KOSPI", True)

            records = KrxSnapshotNormalizer().normalize(root)

        kosdaq = next(
            item for item in records if item.market is MarketType.KOSDAQ
        )
        kospi = next(
            item for item in records if item.market is MarketType.KOSPI
        )
        self.assertEqual(date(2023, 6, 29), kosdaq.effective_to)
        self.assertEqual(date(2023, 6, 30), kospi.effective_from)
        self.assertIsNone(kospi.effective_to)

    def test_normalizer_excludes_non_common_stock(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = KrxRawRepository(Path(temporary))
            repository.save(date(2023, 6, 30), "KOSPI", {
                "OutBlock_1": [{
                    "ISU_SRT_CD": "123455",
                    "ISU_ABBRV": "Fixture Preferred",
                    "LIST_DD": "20200101",
                    "SECUGRP_NM": "주권",
                    "KIND_STKCERT_TP_NM": "우선주",
                }]
            })
            repository.save(date(2023, 6, 30), "KOSDAQ", {
                "OutBlock_1": [{
                    "ISU_SRT_CD": "123456",
                    "ISU_ABBRV": "Fixture",
                    "LIST_DD": "20200101",
                    "SECUGRP_NM": "주권",
                    "KIND_STKCERT_TP_NM": "보통주",
                }]
            })

            records = KrxSnapshotNormalizer().normalize(Path(temporary))

        self.assertEqual(["123456"], [item.code for item in records])

    def test_incremental_normalizer_reads_only_new_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = KrxRawRepository(root)
            self._save(repository, date(2026, 8, 25), "KOSDAQ", True)
            self._save(repository, date(2026, 8, 25), "KOSPI", False)
            self._save(repository, date(2026, 8, 26), "KOSDAQ", False)
            self._save(repository, date(2026, 8, 26), "KOSPI", True)
            base = [UniverseHistoryRecord(
                code="123456",
                name="Fixture",
                market=MarketType.KOSDAQ,
                effective_from=date(2020, 1, 1),
                effective_to=None,
                source_id="KRX_OPEN_API_ISSUE_BASE_INFO",
            )]

            records = KrxSnapshotNormalizer().normalize_incremental(
                root, base, date(2026, 8, 24)
            )

        kosdaq = next(item for item in records if item.market is MarketType.KOSDAQ)
        kospi = next(item for item in records if item.market is MarketType.KOSPI)
        self.assertEqual(date(2020, 1, 1), kosdaq.effective_from)
        self.assertEqual(date(2026, 8, 25), kosdaq.effective_to)
        self.assertEqual(date(2026, 8, 26), kospi.effective_from)
        self.assertIsNone(kospi.effective_to)

    def test_incremental_hash_ignores_files_before_delta_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = KrxRawRepository(root)
            self._save(repository, date(2026, 8, 24), "KOSPI", True)
            self._save(repository, date(2026, 8, 25), "KOSPI", True)
            first = repository.content_sha256(
                start=date(2026, 8, 25), seed="a" * 64
            )
            repository.path_for(date(2026, 8, 24), "KOSPI").write_text(
                "changed historical file", encoding="utf-8"
            )

            second = repository.content_sha256(
                start=date(2026, 8, 25), seed="a" * 64
            )

        self.assertEqual(first, second)

    @staticmethod
    def _save(repository, value, market, present):
        rows = []
        if present:
            rows.append({
                "ISU_SRT_CD": "123456",
                "ISU_ABBRV": "Fixture",
                "LIST_DD": "20200101",
                "SECUGRP_NM": "주권",
                "KIND_STKCERT_TP_NM": "보통주",
            })
        repository.save(value, market, {"OutBlock_1": rows})


if __name__ == "__main__":
    unittest.main()
